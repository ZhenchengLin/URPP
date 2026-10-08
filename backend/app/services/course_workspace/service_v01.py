"""Course Workspace service (docs/33): the single entry point for the API.

Documents reuse URPP's existing importers and digest-pinned Course Packs.
Practice observations steer the next step; they never write mastery evidence.
"""

from __future__ import annotations

import re
import secrets
import threading
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.knowledge_fetch_v01 import (
    canonical_pack_bytes_v01,
    course_pack_digest_v01,
)
from app.services.course_knowledge.local_learning_workspace_v01 import (
    REPO_ROOT,
    LocalLearningWorkspaceV01,
)
from app.services.course_knowledge.local_material_import_v01 import (
    build_local_material_pack_v01,
)
from app.services.course_knowledge.local_pdf_import_v01 import build_local_pdf_pack_v01
from app.services.course_workspace.lesson_v01 import generate_lesson_v01
from app.services.course_workspace.outline_v01 import propose_outline_v01
from app.services.course_workspace.preparation_v01 import PreparationWorkerV01
from app.services.course_workspace.practice_v01 import (
    generate_items_v01,
    public_item_v01,
    question_fingerprint_v01,
    score_answer_v01,
)
from app.services.course_workspace.progress_policy_v01 import (
    next_step_v01,
    recommended_topic_v01,
    summarize_topic_v01,
)
from app.services.course_workspace.store_v01 import CourseWorkspaceStoreV01

COURSE_OBJECTIVE_ID_V01 = "course-material"
MAX_DOCUMENTS_PER_COURSE_V01 = 6
_ID = re.compile(r"(?:course|doc|item)-[0-9a-f]{16}\Z")
_TOPIC_ID = re.compile(r"t[0-9]{1,2}\Z")


def locator_label_v01(filename: str, locator: str) -> str:
    query = parse_qs(urlsplit(locator).query)
    pages = query.get("pages", [""])[0]
    if pages:
        first, _, last = pages.partition("-")
        return f"{filename}, p. {first}" if first == last else f"{filename}, pp. {pages}"
    return f"{filename}, part {query.get('excerpt', ['?'])[0]}"


class CourseWorkspaceServiceV01:
    def __init__(self, *, data_root: Path, model, prepare_in_background: bool = True) -> None:
        supplied = Path(data_root).expanduser().absolute()
        if supplied.is_symlink():
            raise ValueError("Workspace path cannot be a symlink.")
        self.root = supplied.resolve()
        if self.root.is_relative_to(REPO_ROOT):
            raise ValueError("Workspace must be outside the Git repository.")
        for directory in (self.root, self.root / "uploads", self.root / "packs"):
            if directory.is_symlink():
                raise ValueError("Workspace directory cannot be a symlink.")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.stat().st_mode & 0o077:
                raise PermissionError("Workspace directory is not private (0700 required).")
        self.store = CourseWorkspaceStoreV01(self.root / "course-workspace.sqlite3")
        self.model = model
        # One local model call at a time keeps a 16 GB laptop responsive.
        self._generation_lock = threading.Lock()
        # Lessons and first questions are written ahead of the student (docs/35).
        self._preparer = PreparationWorkerV01(
            self._run_preparation_job, background=prepare_in_background)

    # Validation helpers ----------------------------------------------------

    def _course(self, course_id: str) -> dict:
        if type(course_id) is not str or not _ID.fullmatch(course_id) \
                or not course_id.startswith("course-"):
            raise ValueError("Invalid course ID.")
        course = self.store.get_course(course_id)
        if course is None:
            raise LookupError("Course not found.")
        return course

    def _outline(self, course_id: str) -> dict:
        self._course(course_id)
        outline = self.store.latest_outline(course_id)
        if outline is None:
            raise LookupError("This course has no course path yet.")
        return outline

    def _topic(self, outline: dict, topic_id: str) -> dict:
        if type(topic_id) is not str or not _TOPIC_ID.fullmatch(topic_id):
            raise ValueError("Invalid topic ID.")
        for topic in outline["topics"]:
            if topic["topic_id"] == topic_id:
                return topic
        raise LookupError("Topic not found in the current course path.")

    def _load_pack(self, pack_sha256: str) -> CoursePackV01:
        path = self.root / "packs" / f"{pack_sha256}.json"
        if path.is_symlink() or not path.is_file():
            raise LookupError("Saved Course Pack not found.")
        pack = CoursePackV01.model_validate_json(path.read_bytes())
        if course_pack_digest_v01(pack) != pack_sha256:
            raise ValueError("Stored Course Pack digest mismatch.")
        return pack

    def _sources(self, course_id: str) -> list[dict]:
        sources = []
        for document in self.store.list_documents(course_id):
            pack = self._load_pack(document["pack_sha256"])
            for source in pack.sources:
                sources.append({
                    "ref": f"{document['document_id']}:{source.source_id}",
                    "document_id": document["document_id"],
                    "document": document["filename"],
                    "locator_label": locator_label_v01(
                        document["filename"], source.source_locator
                    ),
                    "content": source.content,
                })
        return sources

    # Courses and documents -------------------------------------------------

    def create_course(self, title: str) -> dict:
        title = re.sub(r"\s+", " ", title if type(title) is str else "").strip()
        if not 1 <= len(title) <= 120:
            raise ValueError("Course title must be 1-120 characters.")
        course_id = "course-" + secrets.token_hex(8)
        self.store.add_course(course_id, title)
        return self.store.get_course(course_id)

    def list_courses(self) -> list[dict]:
        return self.store.list_courses()

    def add_document(self, course_id: str, *, filename: str, content: bytes,
                     allow_local_teaching: bool) -> dict:
        course = self._course(course_id)
        if len(self.store.list_documents(course_id)) >= MAX_DOCUMENTS_PER_COURSE_V01:
            raise ValueError("This course already has the maximum number of documents.")
        if type(filename) is not str or not filename.strip():
            raise ValueError("Material filename is required.")
        options = dict(
            filename=filename, course_id=course_id,
            objective_id=COURSE_OBJECTIVE_ID_V01,
            objective_description=f"Course material for {course['title']}",
            allow_local_teaching=allow_local_teaching,
        )
        if filename.lower().endswith(".pdf"):
            imported = build_local_pdf_pack_v01(pdf_bytes=content, **options)
            pack, blank_pages = imported.pack, list(imported.pages_without_text)
        else:
            pack, blank_pages = build_local_material_pack_v01(file_bytes=content, **options), []
        original_digest = sha256(content).hexdigest()
        if any(d["original_sha256"] == original_digest
               for d in self.store.list_documents(course_id)):
            raise ValueError("This document is already in the course.")
        pack_digest = course_pack_digest_v01(pack)
        LocalLearningWorkspaceV01._save_once(
            self.root / "uploads", f"{original_digest}.bin", content)
        LocalLearningWorkspaceV01._save_once(
            self.root / "packs", f"{pack_digest}.json", canonical_pack_bytes_v01(pack))
        record = {
            "document_id": "doc-" + secrets.token_hex(8),
            "course_id": course_id,
            "filename": filename,
            "original_sha256": original_digest,
            "pack_sha256": pack_digest,
            "source_count": len(pack.sources),
            "pages_without_text": blank_pages,
        }
        self.store.add_document(record)
        return record

    # Course path -----------------------------------------------------------

    def build_outline(self, course_id: str) -> dict:
        self._course(course_id)
        sources = self._sources(course_id)
        if not sources:
            raise ValueError("Add at least one document before building the course path.")
        with self._generation_lock:
            outline = propose_outline_v01(self.model, sources)
        self.store.add_outline(course_id, outline)
        self.schedule_preparation(course_id)
        return self.course_view(course_id)

    def _canonical_items(self, course_id: str, outline: dict) -> dict[str, str]:
        """Map each question to the first saved question with the same text in
        its topic. Earlier versions could save the same question twice (docs/35)."""
        first: dict[tuple[str, str], str] = {}
        canonical = {}
        for topic in outline["topics"]:
            for item in self.store.list_items(course_id, outline["revision"], topic["topic_id"]):
                key = (topic["topic_id"], question_fingerprint_v01(item["question"]))
                canonical[item["item_id"]] = first.setdefault(key, item["item_id"])
        return canonical

    def _observations(self, course_id: str, outline: dict):
        canonical = self._canonical_items(course_id, outline)
        attempts, answered = [], set()
        for attempt in self.store.attempts(course_id, outline["revision"]):
            item_id = canonical.get(attempt["item_id"], attempt["item_id"])
            attempt = {**attempt, "item_id": item_id}
            if item_id in answered:
                # The solution is shown after every submission, so a later
                # attempt on the same question (or a copy of it) had help.
                attempt["solution_shown"] = 1
            answered.add(item_id)
            attempts.append(attempt)
        events = [{**event, "item_id": canonical.get(event["item_id"], event["item_id"])}
                  for event in self.store.events(course_id, outline["revision"])]
        summaries = {
            topic["topic_id"]: summarize_topic_v01(topic["topic_id"], attempts, events)
            for topic in outline["topics"]
        }
        return attempts, events, summaries

    # Preparation ahead of the student ----------------------------------------

    def schedule_preparation(self, course_id: str) -> None:
        """Queue the lesson and first questions for the recommended topic and
        the topic after it, unless they already exist."""
        outline = self.store.latest_outline(course_id)
        if outline is None or self.model is None:
            return
        revision = outline["revision"]
        _, _, summaries = self._observations(course_id, outline)
        ordered = sorted(outline["topics"], key=lambda t: t["order"])
        first = recommended_topic_v01(outline, summaries)
        index = next(i for i, t in enumerate(ordered) if t["topic_id"] == first)
        targets = [first] + [
            t["topic_id"] for t in ordered[index + 1:]
            if summaries[t["topic_id"]]["status"] != "practiced"
        ][:1]
        for topic_id in targets:
            if self.store.get_lesson(course_id, revision, topic_id) is None:
                self._preparer.submit((course_id, revision, topic_id, "lesson"))
            if not self.store.list_items(course_id, revision, topic_id):
                self._preparer.submit((course_id, revision, topic_id, "questions"))

    def _run_preparation_job(self, key) -> None:
        course_id, revision, topic_id, kind = key
        outline = self.store.latest_outline(course_id)
        if outline is None or outline["revision"] != revision:
            return  # the course path was rebuilt; this work is no longer needed
        topic = self._topic(outline, topic_id)
        if kind == "lesson":
            self._ensure_lesson(course_id, outline, topic)
        else:
            self._generate_questions(course_id, outline, topic, only_if_empty=True)

    def _preparation(self, course_id: str, revision: int, topic_id: str,
                     has_lesson: bool, has_items: bool) -> dict:
        def state(kind: str, done: bool) -> dict:
            if done:
                return {"state": "ready"}
            status = self._preparer.status((course_id, revision, topic_id, kind))
            if status and status["state"] == "ready":
                # The job finished but nothing was saved: no question passed
                # the dual-solve check. The student can ask for a new set.
                return {**status, "state": "empty"}
            return status or {"state": "not_started"}
        return {"lesson": state("lesson", has_lesson),
                "questions": state("questions", has_items)}

    def course_view(self, course_id: str) -> dict:
        course = self._course(course_id)
        documents = self.store.list_documents(course_id)
        outline = self.store.latest_outline(course_id)
        view = {"course": course, "documents": documents, "outline": None,
                "recommended_topic_id": None}
        if outline is None:
            return view
        labels = {source["ref"]: source["locator_label"]
                  for source in self._sources(course_id)}
        _, _, summaries = self._observations(course_id, outline)
        view["outline"] = {
            **outline,
            "topics": [
                {**topic,
                 "source_labels": [labels.get(ref, ref) for ref in topic["source_refs"]],
                 "progress": summaries[topic["topic_id"]],
                 "preparation": self._preparation(
                     course_id, outline["revision"], topic["topic_id"],
                     self.store.get_lesson(course_id, outline["revision"],
                                           topic["topic_id"]) is not None,
                     bool(self.store.list_items(course_id, outline["revision"],
                                                topic["topic_id"])))}
                for topic in outline["topics"]
            ],
            "unassigned_source_labels": [
                labels.get(ref, ref) for ref in outline.get("unassigned_source_refs", [])
            ],
        }
        view["recommended_topic_id"] = recommended_topic_v01(outline, summaries)
        view["preparing"] = self._preparer.busy(course_id, outline["revision"])
        view["measured_seconds"] = self._preparer.last_seconds()
        return view

    # Topics ----------------------------------------------------------------

    def topic_view(self, course_id: str, topic_id: str) -> dict:
        outline = self._outline(course_id)
        topic = self._topic(outline, topic_id)
        attempts, _, summaries = self._observations(course_id, outline)
        labels = {s["ref"]: s["locator_label"] for s in self._sources(course_id)}
        lesson = self.store.get_lesson(course_id, outline["revision"], topic_id)
        canonical = self._canonical_items(course_id, outline)
        items = []
        for item in self.store.list_items(course_id, outline["revision"], topic_id):
            if canonical[item["item_id"]] != item["item_id"]:
                continue  # a saved copy of an earlier question
            mine = [a for a in attempts if a["item_id"] == item["item_id"]]
            items.append({
                **public_item_v01(item),
                "source_labels": [labels.get(r, r) for r in item["source_refs"]],
                "attempts": len(mine),
                "answered_correctly": any(a["correct"] for a in mine),
            })
        if lesson is not None:
            lesson = {**lesson,
                      "source_labels": [labels.get(r, r) for r in lesson["source_refs"]]}
        step = next_step_v01(outline, topic_id, summaries)
        titles = {t["topic_id"]: t["title"] for t in outline["topics"]}
        step["topic_title"] = titles.get(step["topic_id"])
        if step["step"] == "answer_check":
            fresh = [i for i in items if i["attempts"] == 0]
            unsolved = [i for i in items if not i["answered_correctly"]]
            choice = (fresh or unsolved or [None])[0]
            step["item_id"] = choice["item_id"] if choice else None
            step["needs_more_questions"] = choice is None
        return {
            "course_id": course_id,
            "revision": outline["revision"],
            "topic": {**topic,
                      "source_labels": [labels.get(r, r) for r in topic["source_refs"]],
                      "prerequisite_titles": [titles[p] for p in topic["prerequisite_topic_ids"]]},
            "lesson": lesson,
            "items": items,
            "progress": summaries[topic_id],
            "next_step": step,
            "preparation": self._preparation(
                course_id, outline["revision"], topic_id, lesson is not None, bool(items)),
        }

    def _topic_sources(self, course_id: str, topic: dict) -> list[dict]:
        wanted = set(topic["source_refs"])
        return [s for s in self._sources(course_id) if s["ref"] in wanted]

    def _ensure_lesson(self, course_id: str, outline: dict, topic: dict) -> None:
        revision, topic_id = outline["revision"], topic["topic_id"]
        if self.store.get_lesson(course_id, revision, topic_id) is not None:
            return
        with self._generation_lock:
            # Re-check: the background worker may have written it meanwhile.
            if self.store.get_lesson(course_id, revision, topic_id) is None:
                lesson = generate_lesson_v01(
                    self.model, topic, self._topic_sources(course_id, topic))
                self.store.add_lesson(course_id, revision, topic_id, lesson)

    def _generate_questions(self, course_id: str, outline: dict, topic: dict,
                            *, only_if_empty: bool) -> dict:
        revision, topic_id = outline["revision"], topic["topic_id"]
        with self._generation_lock:
            if only_if_empty and self.store.list_items(course_id, revision, topic_id):
                return {"added": 0, "rejected": {}, "skipped": "already_prepared"}
            existing = self.store.list_items(course_id, revision, topic_id)
            result = generate_items_v01(
                self.model, topic, self._topic_sources(course_id, topic),
                [item["question"] for item in existing])
            for item in result["items"]:
                self.store.add_item(course_id, revision, topic_id, item)
        return {"added": len(result["items"]), "rejected": result["rejected"]}

    def open_lesson(self, course_id: str, topic_id: str) -> dict:
        outline = self._outline(course_id)
        topic = self._topic(outline, topic_id)
        self._ensure_lesson(course_id, outline, topic)
        self.store.add_event(course_id, outline["revision"], topic_id, "lesson_opened")
        self.schedule_preparation(course_id)
        return self.topic_view(course_id, topic_id)

    def add_questions(self, course_id: str, topic_id: str, *, more: bool = True) -> dict:
        """Generate check questions. With more=False, only fill an empty topic,
        so a click never duplicates the set the background worker prepared."""
        outline = self._outline(course_id)
        topic = self._topic(outline, topic_id)
        generation = self._generate_questions(
            course_id, outline, topic, only_if_empty=not more)
        view = self.topic_view(course_id, topic_id)
        view["generation"] = generation
        return view

    # Practice --------------------------------------------------------------

    def _item(self, item_id: str) -> dict:
        if type(item_id) is not str or not _ID.fullmatch(item_id) \
                or not item_id.startswith("item-"):
            raise ValueError("Invalid question ID.")
        item = self.store.get_item(item_id)
        if item is None:
            raise LookupError("Question not found.")
        return item

    def reveal(self, item_id: str, kind: str) -> dict:
        if kind not in ("hint", "solution", "notes"):
            raise ValueError("Unknown help kind.")
        item = self._item(item_id)
        if kind == "notes":
            # Looking at the lesson while answering counts as help (docs/35).
            self.store.add_event(item["course_id"], item["revision"], item["topic_id"],
                                 "lesson_opened", item_id)
            return {"item_id": item_id, "kind": kind,
                    "text": "Looking at the notes now counts as help for this question."}
        self.store.add_event(item["course_id"], item["revision"], item["topic_id"],
                             f"{kind}_shown", item_id)
        text = item["hint"] if kind == "hint" else item["solution"]
        return {"item_id": item_id, "kind": kind,
                "text": text or "No " + kind + " was written for this question."}

    def submit(self, item_id: str, answer_text: str) -> dict:
        item = self._item(item_id)
        correct = score_answer_v01(item, answer_text)
        if correct is None:
            raise ValueError(
                "Answer with one number." if item["kind"] == "numeric"
                else "Answer with one letter: A, B, C, or D."
            )
        shown = {e["kind"] for e in self.store.events(item["course_id"], item["revision"])
                 if e["item_id"] == item_id}
        self.store.add_attempt(item, answer_text.strip(), correct,
                               "hint_shown" in shown, "solution_shown" in shown,
                               "lesson_opened" in shown)
        # The solution is displayed after every submission, so any later attempt
        # on this question is recorded as assisted.
        self.store.add_event(item["course_id"], item["revision"], item["topic_id"],
                             "solution_shown", item_id)
        expected = (
            str(item["answer_value"]).removesuffix(".0") if item["kind"] == "numeric"
            else item["answer_letter"]
        )
        view = self.topic_view(item["course_id"], item["topic_id"])
        self.schedule_preparation(item["course_id"])
        view["feedback"] = {
            "item_id": item_id,
            "correct": correct,
            "assisted": bool(shown),
            "help_used": sorted(
                {"hint_shown": "hint", "solution_shown": "solution",
                 "lesson_opened": "notes"}[kind] for kind in shown),
            "expected_answer": expected,
            "solution": item["solution"],
        }
        return view

"""docs/33 Course Workspace: offline tests with a scripted fake model."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.local_learning_web_v01 import create_local_learning_web_v01
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)
from app.services.course_workspace.llm_json_v01 import (
    CourseGenerationErrorV01,
    LocalJsonModelV01,
    decode_model_json_v01,
)
from app.services.course_workspace.outline_v01 import (
    build_outline_from_proposal_v01,
    propose_outline_v01,
)
from app.services.course_workspace.practice_v01 import (
    generate_items_v01,
    score_answer_v01,
)
from app.services.course_workspace.progress_policy_v01 import (
    next_step_v01,
    summarize_topic_v01,
)
from app.services.course_workspace.service_v01 import CourseWorkspaceServiceV01

DOC_A = b"# LU decomposition\nA = LU. The multiplier is m = c / a.\n"
DOC_B = b"# Solving systems with LU\nForward substitution then back substitution.\n"


class FakeModel:
    """Answers each generation step by recognising its system prompt."""

    model = "fake-model"

    def __init__(self, *, outline=None, solve_answers=None, fail_outline=False):
        self.calls = []
        self.outline = outline
        self.solve_answers = solve_answers
        self.fail_outline = fail_outline

    def generate(self, *, system, user, schema, max_tokens=2048):
        self.calls.append(system[:40])
        if "learning path" in system:
            if self.fail_outline:
                raise CourseGenerationErrorV01("bad outline")
            return self.outline or {"topics": [
                {"title": "LU decomposition", "summary": "Factor A into L and U.",
                 "key_concepts": ["multiplier", "elimination"], "source_ids": ["S1"],
                 "prerequisites": []},
                {"title": "Solving systems with LU", "summary": "Use L and U to solve.",
                 "key_concepts": ["substitution"], "source_ids": ["S2"],
                 "prerequisites": [1]},
            ]}
        if "professor teaching one topic" in system:
            return {"explanation": "LU writes $A = LU$ where $L$ stores multipliers. " * 2,
                    "worked_example": "For A = [[2,1],[6,8]], m = 3.",
                    "source_ids": ["S1"]}
        if "check questions" in system:
            return {"items": [
                {"kind": "numeric", "question": "For A=[[2,1],[6,8]], what is m?",
                 "choices": [], "answer": "3", "hint": "m = c / a.",
                 "solution": "m = 6 / 2 = 3.", "source_ids": ["S1"]},
                {"kind": "multiple_choice", "question": "What does L store in LU?",
                 "choices": ["Pivots", "Multipliers", "Eigenvalues", "Nothing"],
                 "answer": "B", "hint": "Think elimination.", "solution": "Multipliers.",
                 "source_ids": ["S1"]},
                {"kind": "numeric", "question": "What is U[2][2] for that A?",
                 "choices": [], "answer": "5", "hint": "8 - 3*1.",
                 "solution": "8 - 3 = 5.", "source_ids": ["S1"]},
            ]}
        if "checking questions" in system:
            return {"answers": self.solve_answers or [
                {"number": 1, "answer": "3"}, {"number": 2, "answer": "B"},
                {"number": 3, "answer": "5"}]}
        raise AssertionError("unexpected prompt " + system[:60])


def sources():
    return [
        {"ref": "doc-a:s1", "document": "a.md", "locator_label": "a.md, part 1",
         "content": "# LU decomposition\nA = LU."},
        {"ref": "doc-b:s1", "document": "b.md", "locator_label": "b.md, part 1",
         "content": "# Solving systems\nSubstitution."},
    ]


# ---------------------------------------------------------------- JSON repair

def test_json_repair_doubles_invalid_escapes_and_keeps_valid_pairs():
    raw = r'{"a": "\|v\| and \alpha", "b": "\\frac{1}{2}", "c": "line\nnext"}'
    parsed = decode_model_json_v01(raw)
    assert parsed["a"] == r"\|v\| and \alpha"
    assert parsed["b"] == r"\frac{1}{2}"
    assert parsed["c"] == "line\nnext"


def test_json_decoder_strips_code_fences_and_surrounding_text():
    assert decode_model_json_v01('```json\n{"a": 1}\n```') == {"a": 1}
    assert decode_model_json_v01('Here you go: {"a": [1, 2]} Hope it helps.') == {"a": [1, 2]}


def test_json_repair_restores_latex_damaged_by_valid_escapes():
    parsed = decode_model_json_v01('{"x": "\\frac{a}{b} and \\theta"}')
    assert parsed["x"] == r"\frac{a}{b} and \theta"


def test_local_model_retries_once_after_invalid_json():
    replies = iter(['{"topics": [', '{"ok": true}'])
    calls = []

    def transport(payload):
        calls.append(payload["messages"][0]["content"])
        return {"done": True, "done_reason": "stop",
                "message": {"content": next(replies)}}

    assert LocalJsonModelV01(transport=transport).generate(
        system="s", user="u", schema={}) == {"ok": True}
    assert len(calls) == 2 and "not valid JSON" in calls[1]


def test_local_model_rejects_incomplete_generation():
    model = LocalJsonModelV01(transport=lambda payload: {"done": True, "done_reason": "length",
                                                         "message": {"content": "{}"}})
    with pytest.raises(CourseGenerationErrorV01):
        model.generate(system="s", user="u", schema={})


# ---------------------------------------------------------------- outline

def test_outline_validates_aliases_titles_and_prerequisites():
    outline = build_outline_from_proposal_v01({"topics": [
        {"title": "Intro", "summary": "x", "key_concepts": [], "source_ids": ["S1", "S9"],
         "prerequisites": [3]},
        {"title": "No sources", "summary": "x", "key_concepts": [], "source_ids": ["S7"],
         "prerequisites": []},
        {"title": "Next", "summary": "y", "key_concepts": ["k"], "source_ids": ["S2"],
         "prerequisites": [1, 2]},
    ]}, sources())
    assert [t["title"] for t in outline["topics"]] == ["Intro", "Next"]
    assert outline["topics"][0]["source_refs"] == ["doc-a:s1"]
    assert outline["topics"][0]["prerequisite_topic_ids"] == []      # later topic ignored
    assert outline["topics"][1]["prerequisite_topic_ids"] == ["t1"]  # dropped topic ignored
    assert outline["unassigned_source_refs"] == []
    assert len(outline["warnings"]) == 1


def test_outline_falls_back_to_headings_when_model_output_is_unusable():
    outline = propose_outline_v01(FakeModel(fail_outline=True), sources())
    assert outline["generator"] == "heading_derived"
    assert [t["title"] for t in outline["topics"]] == ["LU decomposition", "Solving systems"]
    assert all(t["origin"] == "heading_derived" for t in outline["topics"])
    assert outline["warnings"]


# ---------------------------------------------------------------- practice

def test_dual_solve_keeps_only_agreeing_items():
    model = FakeModel(solve_answers=[{"number": 1, "answer": "3.0"},
                                     {"number": 2, "answer": "C"},
                                     {"number": 3, "answer": "5"}])
    topic = {"title": "LU", "summary": "s"}
    result = generate_items_v01(model, topic, sources()[:1])
    assert [i["question"][:12] for i in result["items"]] == ["For A=[[2,1]", "What is U[2]"]
    assert result["rejected"] == {"invalid": 0, "disagreed": 1}
    assert all(i["key_check"] == "dual_solve_agreed" for i in result["items"])


def test_scoring_is_deterministic_and_rejects_wrong_forms():
    numeric = {"kind": "numeric", "answer_value": 3.0}
    choice = {"kind": "multiple_choice", "answer_letter": "B"}
    assert score_answer_v01(numeric, "3") is True
    assert score_answer_v01(numeric, " 2.9 ") is False
    assert score_answer_v01(numeric, "three") is None
    assert score_answer_v01(choice, "b") is True
    assert score_answer_v01(choice, "A") is False
    assert score_answer_v01(choice, "Because") is None


# ---------------------------------------------------------------- policy

OUTLINE = {"topics": [
    {"topic_id": "t1", "order": 1, "title": "A", "prerequisite_topic_ids": []},
    {"topic_id": "t2", "order": 2, "title": "B", "prerequisite_topic_ids": ["t1"]},
]}


def attempt(item, correct, hint=False, at="2026-10-06T10:00:00", topic="t1"):
    return {"topic_id": topic, "item_id": item, "correct": int(correct),
            "hint_shown": int(hint), "solution_shown": 0, "submitted_at": at}


def step_for(attempts, events, topic="t1"):
    summaries = {t["topic_id"]: summarize_topic_v01(t["topic_id"], attempts, events)
                 for t in OUTLINE["topics"]}
    return next_step_v01(OUTLINE, topic, summaries)


OPENED = [{"topic_id": "t1", "kind": "lesson_opened", "occurred_at": "2026-10-06T09:00:00"}]


@pytest.mark.parametrize("attempts, events, code", [
    ([], [], "topic_not_started"),
    ([], OPENED, "no_practice_evidence"),
    ([attempt("i1", False)], OPENED, "recent_error"),
    ([attempt("i1", False), attempt("i2", False)], OPENED, "repeated_errors"),
    ([attempt("i1", True, hint=True)], OPENED, "assisted_success_needs_unassisted_check"),
    ([attempt("i1", True)], OPENED, "single_success_needs_confirmation"),
    ([attempt("i1", True), attempt("i1", True)], OPENED, "single_success_needs_confirmation"),
    ([attempt("i1", True), attempt("i2", True)], OPENED, "ready_for_next_topic"),
])
def test_next_step_policy_table(attempts, events, code):
    assert step_for(attempts, events)["reason_code"] == code


def test_restudy_after_repeated_errors_clears_the_restudy_step():
    misses = [attempt("i1", False, at="2026-10-06T10:00"), attempt("i2", False, at="2026-10-06T10:01")]
    reopened = OPENED + [{"topic_id": "t1", "kind": "lesson_opened",
                          "occurred_at": "2026-10-06T10:05"}]
    assert step_for(misses, reopened)["reason_code"] == "recent_error"


def test_unpracticed_prerequisite_comes_first():
    step = step_for([], OPENED, topic="t2")
    assert step["reason_code"] == "prerequisite_not_practiced"
    assert step["topic_id"] == "t1"


# ---------------------------------------------------------------- service

def make_service(tmp_path, model=None):
    # Preparation runs inline so tests are deterministic (docs/35).
    return CourseWorkspaceServiceV01(data_root=tmp_path / "ws", model=model or FakeModel(),
                                     prepare_in_background=False)


def test_end_to_end_course_path_lesson_practice_and_restart(tmp_path):
    service = make_service(tmp_path)
    course = service.create_course("Linear Algebra")
    cid = course["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    service.add_document(cid, filename="solve.md", content=DOC_B, allow_local_teaching=True)
    with pytest.raises(ValueError):
        service.add_document(cid, filename="again.md", content=DOC_A, allow_local_teaching=True)

    view = service.build_outline(cid)
    topics = view["outline"]["topics"]
    assert [t["title"] for t in topics] == ["LU decomposition", "Solving systems with LU"]
    assert topics[1]["prerequisite_topic_ids"] == ["t1"]
    assert topics[0]["source_labels"] == ["lu.md, part 1"]
    assert view["recommended_topic_id"] == "t1"
    # The lesson and first questions for t1 and t2 were prepared ahead (docs/35).
    for topic in topics:
        assert topic["preparation"] == {"lesson": {"state": "ready"},
                                        "questions": {"state": "ready"}}

    assert service.topic_view(cid, "t1")["next_step"]["reason_code"] == "topic_not_started"
    calls_before = len(service.model.calls)
    lesson_view = service.open_lesson(cid, "t1")
    assert len(service.model.calls) == calls_before  # nothing left to generate
    assert lesson_view["lesson"]["status"] == "generated_unverified"
    assert lesson_view["next_step"]["step"] == "answer_check"
    assert lesson_view["next_step"]["needs_more_questions"] is False

    first_set = service.add_questions(cid, "t1", more=False)
    assert first_set["generation"]["skipped"] == "already_prepared"
    items = first_set["items"]
    assert len(items) == 3 and "answer_value" not in items[0]

    first, second = items[0]["item_id"], items[2]["item_id"]
    assert service.reveal(first, "hint")["text"] == "m = c / a."
    after_hint = service.submit(first, "3")
    assert after_hint["feedback"] == {**after_hint["feedback"], "correct": True, "assisted": True}
    assert after_hint["next_step"]["reason_code"] == "assisted_success_needs_unassisted_check"
    assert after_hint["next_step"]["item_id"] != first

    service.submit(items[1]["item_id"], "B")
    done = service.submit(second, "5")
    assert done["progress"]["status"] == "practiced"
    assert done["next_step"]["reason_code"] == "ready_for_next_topic"
    assert done["next_step"]["topic_id"] == "t2"

    with pytest.raises(ValueError):
        service.submit(second, "five")

    service.store.close()
    reopened = make_service(tmp_path)
    again = reopened.course_view(cid)
    assert again["recommended_topic_id"] == "t2"
    assert again["outline"]["topics"][0]["progress"]["status"] == "practiced"
    assert reopened.topic_view(cid, "t1")["lesson"] is not None


def test_repeat_on_same_question_counts_as_assisted(tmp_path):
    service = make_service(tmp_path)
    cid = service.create_course("C")["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    service.build_outline(cid)
    item = service.open_lesson(cid, "t1")["items"][0]["item_id"]
    assert service.submit(item, "2")["feedback"]["correct"] is False
    retry = service.submit(item, "3")
    assert retry["feedback"]["assisted"] is True  # the solution was shown after attempt 1


def test_unknown_ids_are_rejected(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError):
        service.course_view("../etc")
    with pytest.raises(LookupError):
        service.course_view("course-0123456789abcdef")


# ---------------------------------------------------------------- HTTP

def test_http_flow_and_page(tmp_path):
    workspace = LocalLearningWorkspaceV01(data_root=tmp_path / "ws",
                                          gateway_factory=lambda: None)
    app = create_local_learning_web_v01(
        workspace=workspace, allow_test_host=True,
        course_service=make_service(tmp_path),
    )
    client = TestClient(app)
    headers = {"X-URPP-Local-Request": "1"}
    page = client.get("/course")
    assert page.status_code == 200 and "Course path" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert "innerHTML" not in client.get("/assets/course.js").text

    cid = client.post("/api/courses", json={"title": "LA"}, headers=headers).json()["course_id"]
    assert client.post("/api/courses", json={"title": "LA"}).status_code == 403
    upload = client.post(f"/api/courses/{cid}/documents", headers=headers, json={
        "filename": "lu.md", "file_base64": base64.b64encode(DOC_A).decode(),
        "allow_local_teaching": True})
    assert upload.status_code == 200 and len(upload.json()["documents"]) == 1
    outline = client.post(f"/api/courses/{cid}/outline", json={}, headers=headers).json()
    topic_id = outline["recommended_topic_id"]
    client.post(f"/api/courses/{cid}/topics/{topic_id}/lesson", json={}, headers=headers)
    items = client.post(f"/api/courses/{cid}/topics/{topic_id}/questions",
                        json={}, headers=headers).json()["items"]
    assert len(items) == 6  # the prepared set plus one more on request
    first_set = client.post(f"/api/courses/{cid}/topics/{topic_id}/questions",
                            json={"more": False}, headers=headers).json()
    assert first_set["generation"]["skipped"] == "already_prepared"
    peek = client.post(f"/api/questions/{items[0]['item_id']}/help",
                       json={"kind": "notes"}, headers=headers)
    assert peek.status_code == 200
    assert client.post(f"/api/questions/{items[0]['item_id']}/help",
                       json={"kind": "answer"}, headers=headers).status_code in (400, 422)
    answer = client.post(f"/api/questions/{items[0]['item_id']}/answer",
                         json={"answer": "3"}, headers=headers)
    assert answer.json()["feedback"]["correct"] is True
    assert answer.json()["feedback"]["help_used"] == ["notes"]
    bad = client.post(f"/api/questions/{items[0]['item_id']}/answer",
                      json={"answer": "three"}, headers=headers)
    assert bad.status_code == 400 and "one number" in bad.json()["detail"]
    assert client.get("/api/courses/course-0000000000000000").status_code == 404
    assert json.dumps(client.get(f"/api/courses/{cid}").json())  # serializable


def test_outline_accepts_key_name_variants_from_small_models():
    outline = build_outline_from_proposal_v01({"topics": [
        {"title": "Intro", "summary": "x", "key_concepts": [], "source_excerpts": ["S1"],
         "earlier_topics": []},
        {"title": "Next", "summary": "y", "key_concepts": [], "source_excerpts": ["S2"],
         "earlier_topics": [1]},
    ]}, sources())
    assert outline["topics"][1]["prerequisite_topic_ids"] == ["t1"]
    assert outline["topics"][1]["source_refs"] == ["doc-b:s1"]


def test_heading_fallback_splits_markdown_sections_and_keeps_titles_unique():
    doc = "# Notes A\n\n## 1. Idea\nalpha text\n\n## 2. Worked example\nbeta\n"
    other = "# Notes B\n\n## Setup\ngamma\n\n## Worked example\ndelta\n"
    outline = propose_outline_v01(FakeModel(fail_outline=True), [
        {"ref": "a:1", "document": "a.md", "locator_label": "a", "content": doc},
        {"ref": "b:1", "document": "b.md", "locator_label": "b", "content": other},
    ])
    titles = [t["title"] for t in outline["topics"]]
    assert titles == ["Idea (Notes A)", "Worked example", "Setup (Notes B)",
                      "Worked example (Notes B)"]
    assert outline["topics"][1]["prerequisite_topic_ids"] == ["t1"]
    assert outline["topics"][2]["prerequisite_topic_ids"] == []


# ---------------------------------------------------------------- docs/35

def test_peeking_at_notes_during_a_question_counts_as_help(tmp_path):
    service = make_service(tmp_path)
    cid = service.create_course("C")["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    service.build_outline(cid)
    items = service.open_lesson(cid, "t1")["items"]
    peeked, clean = items[0]["item_id"], items[2]["item_id"]
    service.reveal(peeked, "notes")
    result = service.submit(peeked, "3")
    assert result["feedback"]["assisted"] is True
    assert result["feedback"]["help_used"] == ["notes"]
    assert result["progress"]["correct_unassisted_items"] == 0
    assert result["next_step"]["reason_code"] == "assisted_success_needs_unassisted_check"
    attempt = service.store.attempts(cid, 1)[-1]
    assert attempt["notes_shown"] == 1 and attempt["hint_shown"] == 0
    # Studying before a question (no item attached) is not help for it.
    service.open_lesson(cid, "t1")
    assert service.submit(clean, "5")["feedback"]["assisted"] is False


def test_old_database_gains_notes_column(tmp_path):
    import sqlite3
    from app.services.course_workspace.store_v01 import CourseWorkspaceStoreV01

    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE cw_attempts_v01 (attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "item_id TEXT NOT NULL, course_id TEXT NOT NULL, revision INTEGER NOT NULL, "
        "topic_id TEXT NOT NULL, answer_text TEXT NOT NULL, correct INTEGER NOT NULL, "
        "hint_shown INTEGER NOT NULL, solution_shown INTEGER NOT NULL, "
        "submitted_at TEXT NOT NULL)")
    connection.execute(
        "INSERT INTO cw_attempts_v01 VALUES (1, 'item-0', 'course-0', 1, 't1', '3', 1, 0, 0, 'x')")
    connection.commit()
    connection.close()
    store = CourseWorkspaceStoreV01(path)
    assert store.attempts("course-0", 1)[0]["notes_shown"] == 0
    store.close()


def test_background_preparation_fills_lesson_and_questions(tmp_path):
    import time

    service = CourseWorkspaceServiceV01(data_root=tmp_path / "ws", model=FakeModel())
    cid = service.create_course("C")["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    service.add_document(cid, filename="solve.md", content=DOC_B, allow_local_teaching=True)
    view = service.build_outline(cid)
    assert view["outline"]["topics"][0]["preparation"]["lesson"]["state"] in (
        "queued", "working", "ready")
    deadline = time.time() + 10
    while service.course_view(cid)["preparing"] and time.time() < deadline:
        time.sleep(0.02)
    topics = service.course_view(cid)["outline"]["topics"]
    assert [t["preparation"] for t in topics] == [
        {"lesson": {"state": "ready"}, "questions": {"state": "ready"}}] * 2
    assert len(service.topic_view(cid, "t1")["items"]) == 3  # prepared once, not twice
    assert set(service.course_view(cid)["measured_seconds"]) == {"lesson", "questions"}


def test_preparation_reports_failures_and_empty_sets(tmp_path):
    class NoQuestions(FakeModel):
        def generate(self, *, system, user, schema, max_tokens=2048):
            if "check questions" in system:
                return {"items": []}
            if "professor teaching one topic" in system:
                raise RuntimeError("model crashed")
            return super().generate(system=system, user=user, schema=schema,
                                    max_tokens=max_tokens)

    service = make_service(tmp_path, NoQuestions())
    cid = service.create_course("C")["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    prep = service.build_outline(cid)["outline"]["topics"][0]["preparation"]
    assert prep["lesson"]["state"] == "failed" and prep["lesson"]["error"] == "RuntimeError"
    assert prep["questions"]["state"] == "empty"


def test_stale_preparation_after_rebuild_is_skipped(tmp_path):
    service = make_service(tmp_path)
    cid = service.create_course("C")["course_id"]
    service.add_document(cid, filename="lu.md", content=DOC_A, allow_local_teaching=True)
    service.build_outline(cid)
    service.build_outline(cid)  # revision 2
    calls = len(service.model.calls)
    service._run_preparation_job((cid, 1, "t1", "questions"))
    assert len(service.model.calls) == calls


def test_fallback_summary_keeps_whole_formulas_for_the_renderer():
    from app.services.course_workspace.outline_v01 import _plain

    assert _plain("The multiplier is\n\n$$m = \\frac{c}{a}$$\n\nNext.", 200) == \
        "The multiplier is $m = \\frac{c}{a}$ Next."
    cut = _plain("Intro $$A = LU$$ then $$" + "x+" * 100 + "1$$", 60)
    assert cut == "Intro $A = LU$ then …" and cut.count("$") % 2 == 0

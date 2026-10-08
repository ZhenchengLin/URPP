"""Course path (outline) construction: model proposal, deterministic validation.

The model sees short aliases (S1, S2, ...) instead of real source IDs. Every
reference is checked here; a proposal that cannot be validated falls back to a
heading-derived outline, so a course path always exists and its origin is
labelled.
"""

from __future__ import annotations

import re

from app.services.course_workspace.llm_json_v01 import CourseGenerationErrorV01

MAX_TOPICS_V01 = 12
OUTLINE_PREVIEW_CHARS_V01 = 1200

OUTLINE_SCHEMA_V01 = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_TOPICS_V01,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_concepts": {"type": "array", "items": {"type": "string"}},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "prerequisites": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "summary", "key_concepts", "source_ids",
                             "prerequisites"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
}

OUTLINE_SYSTEM_V01 = (
    "You design the learning path for a university course from its materials. "
    "Write in English. Split the material into 2 to 12 topics a student should "
    "learn in order, from foundations to advanced. Return JSON of the form "
    '{"topics": [{"title": ..., "summary": ..., "key_concepts": [...], '
    '"source_ids": ["S1"], "prerequisites": [1]}]} where "title" is short, '
    '"summary" is one or two sentences, "key_concepts" has at most 6 items, '
    '"source_ids" lists the excerpt IDs (S1, S2, ...) that teach the topic, and '
    '"prerequisites" lists the numbers of EARLIER topics (1-based) it depends on. '
    "Use only the supplied excerpts; do not invent topics they do not cover."
)

# Small local models do not always follow the schema's key names exactly.
_SOURCE_KEYS = ("source_ids", "source_excerpts", "sources", "excerpt_ids")
_PREREQUISITE_KEYS = ("prerequisites", "earlier_topics", "depends_on", "prerequisite_topics")


def _first_list(raw: dict, keys: tuple[str, ...]) -> list:
    for key in keys:
        if type(raw.get(key)) is list:
            return raw[key]
    return []


def _topic_list(proposal) -> list | None:
    if type(proposal) is list:
        return proposal
    if type(proposal) is dict:
        if type(proposal.get("topics")) is list:
            return proposal["topics"]
        lists = [value for value in proposal.values() if type(value) is list]
        if len(lists) == 1:
            return lists[0]
    return None


def _clean(text, limit: int) -> str:
    if type(text) is not str:
        return ""
    return re.sub(r"\s+", " ", text).strip()[:limit]


def build_outline_from_proposal_v01(proposal, sources: list[dict]) -> dict:
    """Validate a model proposal against the real sources. Raises if unusable."""
    aliases = {f"S{index}": source["ref"] for index, source in enumerate(sources, 1)}
    proposed = _topic_list(proposal)
    if proposed is None:
        raise CourseGenerationErrorV01("Outline proposal has no topic list.")

    topics: list[dict] = []
    new_number: dict[int, str] = {}  # model's 1-based number -> kept topic_id
    seen_titles: set[str] = set()
    warnings: list[str] = []
    for number, raw in enumerate(proposed[:MAX_TOPICS_V01], 1):
        if type(raw) is not dict:
            continue
        title = _clean(raw.get("title"), 120)
        refs = []
        for alias in _first_list(raw, _SOURCE_KEYS):
            ref = aliases.get(alias.strip()) if type(alias) is str else None
            if ref and ref not in refs:
                refs.append(ref)
        if len(title) < 3 or title.lower() in seen_titles:
            warnings.append(f"Dropped proposed topic {number}: missing or duplicate title.")
            continue
        if not refs:
            warnings.append(f"Dropped proposed topic {number} ({title}): no valid sources.")
            continue
        topic_id = f"t{len(topics) + 1}"
        prerequisites = []
        for value in _first_list(raw, _PREREQUISITE_KEYS):
            if type(value) is int and value < number and value in new_number:
                if new_number[value] not in prerequisites:
                    prerequisites.append(new_number[value])
        concepts = [
            _clean(concept, 80) for concept in (raw.get("key_concepts") or [])[:6]
            if _clean(concept, 80)
        ]
        topics.append({
            "topic_id": topic_id,
            "order": len(topics) + 1,
            "title": title,
            "summary": _clean(raw.get("summary"), 600),
            "key_concepts": concepts,
            "prerequisite_topic_ids": prerequisites,
            "source_refs": refs,
            "origin": "model_proposed",
        })
        new_number[number] = topic_id
        seen_titles.add(title.lower())

    if not topics:
        raise CourseGenerationErrorV01("No proposed topic survived validation.")
    used = {ref for topic in topics for ref in topic["source_refs"]}
    return {
        "generator": "model_proposed",
        "topics": topics,
        "unassigned_source_refs": [s["ref"] for s in sources if s["ref"] not in used],
        "warnings": warnings,
    }


def _plain(text: str, limit: int) -> str:
    """Readable preview: drop Markdown heading marks and page tags. Display
    formulas become inline math, so the page can typeset them (docs/35)."""
    text = re.sub(r"\[PDF page \d+, fragment \d+\]", " ", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: "$" + m.group(1).strip() + "$", text, flags=re.S)
    text = _clean(text, limit)
    if text.count("$") % 2:
        # The limit cut a formula in half: end the preview before it instead.
        text = text[:text.rfind("$")].rstrip() + " …"
    return text


def _heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return _clean(stripped.lstrip("#"), 120)
    for line in text.splitlines():
        stripped = re.sub(r"^\[PDF page \d+, fragment \d+\]$", "", line.strip())
        if len(stripped) >= 3:
            return _clean(stripped, 80)
    return ""


def _sections(text: str) -> list[tuple[str, str]]:
    """Split on level-2+ Markdown headings; returns (title, body) pairs."""
    parts = re.split(r"^(#{2,6}\s+.+)$", text, flags=re.M)
    sections = []
    for index in range(1, len(parts), 2):
        title = _clean(parts[index].lstrip("#"), 120)
        title = re.sub(r"^\d+[.)]\s*", "", title)
        body = parts[index + 1] if index + 1 < len(parts) else ""
        if title and body.strip():
            sections.append((title, body))
    return sections


def heading_outline_v01(sources: list[dict]) -> dict:
    """Deterministic fallback: one topic per Markdown section, else per excerpt."""
    topics = []
    previous_by_document: dict[str, str] = {}

    def add(title: str, summary: str, source: dict) -> None:
        if len(topics) >= MAX_TOPICS_V01:
            return
        if any(topic["title"].lower() == title.lower() for topic in topics):
            title = f"{title} ({_heading(source['content']) or source['document']})"
        topic_id = f"t{len(topics) + 1}"
        previous = previous_by_document.get(source["document"])
        topics.append({
            "topic_id": topic_id,
            "order": len(topics) + 1,
            "title": title,
            "summary": summary,
            "key_concepts": [],
            "prerequisite_topic_ids": [previous] if previous else [],
            "source_refs": [source["ref"]],
            "origin": "heading_derived",
        })
        previous_by_document[source["document"]] = topic_id

    for index, source in enumerate(sources, 1):
        sections = _sections(source["content"])
        if len(sections) >= 2:
            document_title = _heading(source["content"])
            for title, body in sections:
                add(title if len(title) > 12 or not document_title
                    else f"{title} ({document_title})", _plain(body, 200), source)
        else:
            add(_heading(source["content"]) or f"{source['document']} — part {index}",
                _plain(source["content"], 200), source)
    return {"generator": "heading_derived", "topics": topics,
            "unassigned_source_refs": [], "warnings": []}


def propose_outline_v01(model, sources: list[dict]) -> dict:
    """Ask the model for a course path; fall back deterministically on failure."""
    if not sources:
        raise ValueError("A course path needs at least one document.")
    preview = "\n\n".join(
        f"[S{index}] from {source['document']} ({source['locator_label']}):\n"
        f"{source['content'][:OUTLINE_PREVIEW_CHARS_V01]}"
        for index, source in enumerate(sources, 1)
    )
    try:
        proposal = model.generate(
            system=OUTLINE_SYSTEM_V01,
            user="Course excerpts:\n\n" + preview,
            schema=OUTLINE_SCHEMA_V01,
            max_tokens=3000,
        )
        outline = build_outline_from_proposal_v01(proposal, sources)
        outline["model"] = getattr(model, "model", "unknown")
        return outline
    except CourseGenerationErrorV01 as exc:
        outline = heading_outline_v01(sources)
        outline["warnings"].append(
            f"Model proposal unusable ({exc}); topics were derived from document headings instead."
        )
        return outline

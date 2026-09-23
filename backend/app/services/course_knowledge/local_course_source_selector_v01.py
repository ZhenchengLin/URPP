"""Developer-only bounded excerpt selection for one local Professor turn.

This is a deterministic lexical/section-heading heuristic, NOT semantic retrieval,
proof of source support, or permission to fetch additional Course Pack material.
It receives only the already authorized excerpt dictionaries from the Adapter.
It returns one original Source ID; source contents are never changed/truncated.
"""
from __future__ import annotations

import re

# Technical keywords must not be obscured by common prompt boilerplate.
_STOP = frozenset({
    "the", "and", "for", "from", "with", "that", "this", "what", "why",
    "how", "can", "could", "would", "should", "about", "please", "tell",
    "give", "explain", "teach", "learn", "basic", "basics", "concept",
    "concepts", "paper", "uploaded", "material", "document", "source",
    "using", "into", "more", "start", "first", "next", "then", "only",
    "section", "chapter", "short", "sentence", "sentences", "does", "mean",
})
_WORDS = re.compile(r"[a-z][a-z0-9_-]{2,}", re.I)
_SECTION = re.compile(r"\b(?:section|chapter)\s+([IVX]{1,5}|[1-6])\b", re.I)
_HEADING = re.compile(r"(?m)^\s*([IVX]{1,5})\.\s+([A-Z][A-Z0-9 /\-]{3,})")
_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}


def select_course_source_ids_v01(*, sources: tuple[dict, ...],
                                 current_question: str, history: tuple = ()) -> tuple[str, ...]:
    """Select exactly one complete authorized excerpt for a small local context.

    Section headings in an excerpt win over passing mentions of a section.
    Otherwise select the excerpt with the most overlapping nontrivial words.
    Short follow-ups may use the preceding student's question for continuity.
    If no words match, choose the first authorized excerpt as a limited demo
    fallback; it does NOT establish that an answer is supported by the source.
    """
    if not sources or type(current_question) is not str or not current_question.strip():
        raise ValueError("A current question and authorized sources are required.")
    if any(type(s) is not dict or type(s.get("source_id")) is not str
           or type(s.get("content")) is not str for s in sources):
        raise ValueError("Invalid authorized source selection input.")
    question = current_question
    # A short follow-up such as 'why?' may refer to the previous student's topic.
    if len(_WORDS.findall(question)) <= 2:
        for item in reversed(history):
            if getattr(item, "role", None) == "student":
                question = current_question + " " + item.text
                break

    section = _SECTION.search(question)
    requested_heading = (
        _ROMAN.get(section.group(1).upper(), section.group(1).upper())
        if section else None
    )
    keywords = {
        word.lower() for word in _WORDS.findall(question)
        if word.lower() not in _STOP
    }
    if "introduction" in keywords:
        requested_heading = requested_heading or "I"

    def rank(index: int, source: dict) -> tuple[int, int]:
        content = source["content"]
        lower = content.lower()
        headings = {m.group(1) for m in _HEADING.finditer(content)}
        score = 0
        if requested_heading and requested_heading in headings:
            score += 200
        if "cuda" in keywords and any(
            "CUDA" in m.group(2) for m in _HEADING.finditer(content)
        ):
            score += 100
        for word in keywords:
            # Bounded repetitions prevent long articles from always winning.
            score += min(3, len(re.findall(r"(?<![a-z0-9_])" +
                                           re.escape(word) + r"(?![a-z0-9_])", lower)))
            if word in lower[:1200]:
                score += 2
        return (score, -index)

    best = max(range(len(sources)), key=lambda i: rank(i, sources[i]))
    return (sources[best]["source_id"],)

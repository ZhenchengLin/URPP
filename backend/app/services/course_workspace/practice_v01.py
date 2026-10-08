"""Check questions for a topic, with a dual-solve consistency filter.

1. The model proposes numeric or multiple-choice questions with an answer key.
2. In a separate call it solves the same questions without seeing the keys.
3. Only questions whose two answers agree are kept (key_check=dual_solve_agreed).

Agreement is a consistency check, not human verification: a model can be
consistently wrong. Scoring is deterministic.
"""

from __future__ import annotations

import math
import re
import secrets

from app.services.assessment.numeric_scoring_v02 import parse_numeric_answer
from app.services.course_workspace.llm_json_v01 import CourseGenerationErrorV01

LETTERS_V01 = ("A", "B", "C", "D")

ITEMS_SCHEMA_V01 = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["numeric", "multiple_choice"]},
                    "question": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                    "answer": {"type": "string"},
                    "hint": {"type": "string"},
                    "solution": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "question", "choices", "answer", "hint",
                             "solution", "source_ids"],
            },
        }
    },
    "required": ["items"],
}

SOLVE_SCHEMA_V01 = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "work": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["number", "work", "answer"],
            },
        }
    },
    "required": ["answers"],
}

ITEMS_SYSTEM_V01 = (
    "You write check questions for one topic of a university course. Write in "
    "English. Use only the supplied course excerpts. Write 3 questions that test "
    'understanding of the topic. Return JSON of the form {"items": [{"kind": ..., '
    '"question": ..., "choices": [...], "answer": ..., "hint": ..., "solution": ..., '
    '"source_ids": ["S1"]}]}. Each question is either '
    "'numeric' (the answer is one number; put it in 'answer' as digits only, e.g. 3 or -0.5, and leave "
    "'choices' empty) or 'multiple_choice' (exactly 4 choices; 'answer' is the "
    "letter A, B, C or D of the single correct choice). Give a 'hint' that helps "
    "without revealing the answer, and a short step-by-step 'solution'. Write math "
    "in LaTeX between $...$ and escape every backslash in JSON as \\\\. List the "
    "excerpt IDs (S1, S2, ...) each question is based on."
)

SOLVE_SYSTEM_V01 = (
    "You are checking questions written for a university course. Use the supplied "
    "course excerpts. Solve each question independently: first write brief working "
    'in "work" (at most 3 sentences), then give the final "answer". For a numeric '
    "question the answer is one number in digits only. For a multiple-choice "
    "question the answer is only the letter A, B, C or D. Return JSON of the form "
    '{"answers": [{"number": 1, "work": "...", "answer": "..."}]} with one entry '
    "per question number."
)


def _pick(raw: dict, keys: tuple[str, ...], kind: type):
    for key in keys:
        if type(raw.get(key)) is kind:
            return raw[key]
    return None


def _numbers_agree(first: float, second: float) -> bool:
    return abs(first - second) <= max(1e-6, 1e-3 * abs(first))


def _letter(text) -> str | None:
    if type(text) is not str:
        return None
    # "B", "b)", "(C)", "D. text" -> letter; "Because ..." -> no letter.
    match = re.fullmatch(r"\s*\(?([A-Da-d])(?:[\).:]|\s|$).*", text, re.S)
    return match.group(1).upper() if match else None


def _validate_item(raw, aliases: dict[str, str]) -> dict | None:
    if type(raw) is not dict:
        return None
    question = _pick(raw, ("question", "prompt", "text"), str)
    if question is None or not 10 <= len(question.strip()) <= 1500:
        return None
    answer = _pick(raw, ("answer", "correct_answer", "answer_key"), str)
    if answer is None and type(raw.get("answer")) in (int, float):
        answer = str(raw["answer"])
    choices = _pick(raw, ("choices", "options"), list) or []
    kind = raw.get("kind") or raw.get("type")
    if kind not in ("numeric", "multiple_choice"):
        kind = "multiple_choice" if len(choices) == 4 else "numeric"
    item = {
        "kind": kind,
        "question": question.strip(),
        "hint": (_pick(raw, ("hint",), str) or "").strip()[:1500],
        "solution": (_pick(raw, ("solution", "explanation"), str) or "").strip()[:3000],
    }
    if kind == "numeric":
        value = parse_numeric_answer(answer) if answer is not None else None
        if value is None or not math.isfinite(value):
            return None
        item["answer_value"] = value
        item["choices"] = []
    elif kind == "multiple_choice":
        if (
            type(choices) is not list or len(choices) != 4
            or any(type(c) is not str or not c.strip() for c in choices)
            or len({c.strip().lower() for c in choices}) != 4
        ):
            return None
        letter = _letter(answer)
        if letter is None:
            return None
        item["choices"] = [c.strip()[:500] for c in choices]
        item["answer_letter"] = letter
    else:
        return None
    refs = []
    for alias in _pick(raw, ("source_ids", "sources", "source_excerpts"), list) or []:
        ref = aliases.get(alias.strip()) if type(alias) is str else None
        if ref and ref not in refs:
            refs.append(ref)
    item["source_refs"] = refs or list(aliases.values())[:1]
    return item


def _agrees(item: dict, answer) -> bool:
    if item["kind"] == "numeric":
        value = parse_numeric_answer(answer) if type(answer) is str else None
        return value is not None and _numbers_agree(item["answer_value"], value)
    return _letter(answer) == item["answer_letter"]


def _question_text(number: int, item: dict) -> str:
    text = f"Question {number} ({item['kind']}): {item['question']}"
    if item["kind"] == "multiple_choice":
        text += "\n" + "\n".join(
            f"{letter}. {choice}" for letter, choice in zip(LETTERS_V01, item["choices"])
        )
    return text


MAX_SEEN_QUESTIONS_IN_PROMPT_V01 = 12


def question_fingerprint_v01(text: str) -> str:
    """Question text without case, spacing, or punctuation. Two questions with
    the same fingerprint are the same question for practice evidence (docs/35)."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def generate_items_v01(model, topic: dict, sources: list[dict],
                       existing_questions: list[str] = ()) -> dict:
    """Return {'items': kept items, 'rejected': counts by reason}.

    The model runs at temperature 0, so without the list of questions the
    student has already seen it would write the same set again."""
    aliases = {f"S{index}": source["ref"] for index, source in enumerate(sources, 1)}
    excerpts = "\n\n".join(
        f"[S{index}] {source['locator_label']}:\n{source['content'][:6000]}"
        for index, source in enumerate(sources, 1)
    )
    seen = ""
    if existing_questions:
        recent = list(existing_questions)[-MAX_SEEN_QUESTIONS_IN_PROMPT_V01:]
        seen = ("\n\nThe student has already seen these questions. Write new ones "
                "that test a different fact or use different numbers; do not repeat "
                "or reword them:\n" + "\n".join(f"- {q[:300]}" for q in recent))
    proposal = model.generate(
        system=ITEMS_SYSTEM_V01,
        user=f"Topic: {topic['title']}\nSummary: {topic['summary']}\n\n"
             f"Course excerpts:\n\n{excerpts}{seen}",
        schema=ITEMS_SCHEMA_V01,
        max_tokens=3000,
    )
    proposed = proposal if type(proposal) is list else (
        _pick(proposal, ("items", "questions"), list) if type(proposal) is dict else None)
    if proposed is None:
        raise CourseGenerationErrorV01("Question proposal has no item list.")
    candidates = []
    invalid = duplicate = 0
    fingerprints = {question_fingerprint_v01(q) for q in existing_questions}
    for raw in proposed[:4]:
        item = _validate_item(raw, aliases)
        if item is None:
            invalid += 1
        elif question_fingerprint_v01(item["question"]) in fingerprints:
            duplicate += 1
        else:
            fingerprints.add(question_fingerprint_v01(item["question"]))
            candidates.append(item)
    if not candidates:
        return {"items": [], "rejected": {"invalid": invalid, "duplicate": duplicate,
                                          "disagreed": 0}}

    # The checker sees the same excerpts as the writer, but never the answer key.
    solved = model.generate(
        system=SOLVE_SYSTEM_V01,
        user="Course excerpts:\n\n" + excerpts + "\n\nQuestions:\n\n" + "\n\n".join(
            _question_text(number, item) for number, item in enumerate(candidates, 1)
        ),
        schema=SOLVE_SCHEMA_V01,
        max_tokens=1500,
    )
    answers = {}
    entries = solved if type(solved) is list else (
        _pick(solved, ("answers", "solutions"), list) if type(solved) is dict else None) or []
    for position, entry in enumerate(entries, 1):
        if type(entry) is not dict:
            continue
        number = entry.get("number") if type(entry.get("number")) is int else position
        value = entry.get("answer")
        answers.setdefault(number, str(value) if type(value) in (int, float) else value)
    kept = []
    for number, item in enumerate(candidates, 1):
        if _agrees(item, answers.get(number)):
            kept.append({
                **item,
                "item_id": "item-" + secrets.token_hex(8),
                "key_check": "dual_solve_agreed",
                "model": getattr(model, "model", "unknown"),
            })
    return {"items": kept,
            "rejected": {"invalid": invalid, "duplicate": duplicate,
                         "disagreed": len(candidates) - len(kept)}}


def score_answer_v01(item: dict, answer_text: str) -> bool | None:
    """True/False for a gradable answer; None if it is not in the expected form."""
    if type(answer_text) is not str or not answer_text.strip():
        return None
    if item["kind"] == "numeric":
        value = parse_numeric_answer(answer_text)
        if value is None:
            return None
        return _numbers_agree(item["answer_value"], value)
    letter = _letter(answer_text)
    if letter is None or len(answer_text.strip()) > 3:
        return None
    return letter == item["answer_letter"]


def public_item_v01(item: dict) -> dict:
    """The item as shown before answering: no key, hint, or solution."""
    return {
        "item_id": item["item_id"],
        "kind": item["kind"],
        "question": item["question"],
        "choices": item["choices"],
        "source_refs": item["source_refs"],
        "key_check": item["key_check"],
    }

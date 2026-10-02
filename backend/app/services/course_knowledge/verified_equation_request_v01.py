"""URPP 14D-4B4D2G.

Resolve explicit student equation requests against already-selected
authorized Course Sources and the Verified Equation Registry.

This module separates two responsibilities:

1. Exact reviewed mathematical representation:
   deterministic VerifiedEquationRecord rendering.

2. Generated semantic teaching:
   optionally delegated later to the Professor.

This module does NOT:
- call an LLM;
- modify the existing Course Source Selector;
- modify Course Packs;
- write Chat Sessions;
- establish mastery;
- infer that generated explanations are mathematically correct;
- automatically verify equations extracted from PDFs.

A request is handled only when it explicitly names an equation.
If any requested equation lacks one exact eligible verified record,
the resolver fails closed rather than returning a partial formula set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.services.course_knowledge.models_v01 import (
    CourseSourceV01,
)

from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
    lookup_verified_equation_v01,
)


EquationRequestStatusV01 = Literal[
    "not_applicable",
    "verified",
    "incomplete",
]


# First explicit equation marker.
#
# Keep this intentionally compatible with the current local Course Source
# Selector vocabulary without modifying that already-tested Selector.
_MARKED_EQUATION = re.compile(
    r"(?:公式|方程|式|equations?|eq\.?)"
    r"\s*[（(]?\s*"
    r"(\d{1,2})"
    r"\s*[)）]?",
    re.I,
)

# Once an explicitly marked equation has been found, allow immediately
# coordinated parenthesized labels:
#
#   式 (15) 和 (16)
#   equations (15) and (16)
#
# This does NOT interpret arbitrary numbers elsewhere in the question.
_CONTINUED_EQUATION = re.compile(
    r"\s*(?:和|与|及|、|,|，|and|&)\s*"
    r"[（(]\s*(\d{1,2})\s*[)）]",
    re.I,
)


# These tokens mean the user needs semantic material in addition to
# deterministic formula transcription.
_SEMANTIC_REQUEST = re.compile(
    r"(?:"
    r"解释|为什么|为何|意义|含义|变量|参数|方法|"
    r"区别|比较|推导|怎么|如何|分别是什么|是什么|"
    r"\bexplain\b|\bwhy\b|\bmeaning\b|\bmethod\b|"
    r"\bvariable\b|\bparameter\b|\bcompare\b|"
    r"\bderive\b|\bderivation\b|\bhow\b|"
    r"\bwhat\s+is\b"
    r")",
    re.I,
)


@dataclass(frozen=True, slots=True)
class VerifiedEquationRequestResolutionV01:
    """One deterministic resolution decision.

    rendered_markdown is populated only when EVERY requested equation
    has one exact eligible source-bound verified record.

    requires_professor_explanation says only that the student requested
    semantic explanation beyond exact formula display. It does not call
    or authorize a Professor.
    """

    status: EquationRequestStatusV01

    requested_labels: tuple[str, ...]

    missing_labels: tuple[str, ...]

    rendered_markdown: str | None

    source_ids: tuple[str, ...]

    record_ids: tuple[str, ...]

    requires_professor_explanation: bool


def extract_explicit_equation_labels_v01(
    question: str,
) -> tuple[str, ...]:
    """Extract explicit equation labels from the current question only.

    Examples:

    "请写出式 (16)" -> ("16",)

    "式 (15) 和 (16) 分别是什么方法？"
        -> ("15", "16")

    Arbitrary bare numbers are ignored.

    Duplicate labels are removed while preserving first occurrence.
    """

    if (
        type(question) is not str
        or not question.strip()
        or len(question) > 1500
    ):
        raise ValueError(
            "Invalid bounded equation question."
        )

    labels: list[str] = []

    cursor = 0

    while True:
        match = _MARKED_EQUATION.search(
            question,
            cursor,
        )

        if match is None:
            break

        labels.append(match[1])

        continuation_cursor = match.end()

        while True:
            continuation = (
                _CONTINUED_EQUATION.match(
                    question,
                    continuation_cursor,
                )
            )

            if continuation is None:
                break

            labels.append(
                continuation[1]
            )

            continuation_cursor = (
                continuation.end()
            )

        cursor = max(
            match.end(),
            continuation_cursor,
        )

    unique: list[str] = []

    for label in labels:
        if label not in unique:
            unique.append(label)

    return tuple(unique)


def equation_request_requires_explanation_v01(
    question: str,
) -> bool:
    """Return whether explicit formula display alone is insufficient.

    This is a narrow routing hint, not semantic answer validation.
    """

    labels = extract_explicit_equation_labels_v01(
        question
    )

    if not labels:
        return False

    return bool(
        _SEMANTIC_REQUEST.search(question)
    )


def resolve_verified_equation_request_v01(
    *,
    registry: VerifiedEquationRegistryV01,
    sources: tuple[
        CourseSourceV01,
        ...
    ],
    question: str,
) -> VerifiedEquationRequestResolutionV01:
    """Resolve all explicitly requested equations, or fail closed.

    The supplied sources are authoritative. The registry cannot grant
    access to any source not present in sources.

    No partial formula answer is returned when one requested equation
    is missing or ambiguous.
    """

    labels = extract_explicit_equation_labels_v01(
        question
    )

    requires_explanation = (
        equation_request_requires_explanation_v01(
            question
        )
    )

    if not labels:
        return VerifiedEquationRequestResolutionV01(
            status="not_applicable",
            requested_labels=(),
            missing_labels=(),
            rendered_markdown=None,
            source_ids=(),
            record_ids=(),
            requires_professor_explanation=False,
        )

    results = []
    missing = []

    for label in labels:
        result = lookup_verified_equation_v01(
            registry=registry,
            sources=sources,
            equation_label=label,
        )

        if result is None:
            missing.append(label)
        else:
            results.append(result)

    if missing:
        return VerifiedEquationRequestResolutionV01(
            status="incomplete",
            requested_labels=labels,
            missing_labels=tuple(missing),
            rendered_markdown=None,
            source_ids=(),
            record_ids=(),
            requires_professor_explanation=(
                requires_explanation
            ),
        )

    source_ids = []
    record_ids = []
    rendered = []

    for result in results:
        if result.source.source_id not in source_ids:
            source_ids.append(
                result.source.source_id
            )

        record_ids.append(
            result.record.record_id
        )

        rendered.append(
            result.rendered_markdown
        )

    return VerifiedEquationRequestResolutionV01(
        status="verified",
        requested_labels=labels,
        missing_labels=(),
        rendered_markdown="\n\n".join(rendered),
        source_ids=tuple(source_ids),
        record_ids=tuple(record_ids),
        requires_professor_explanation=(
            requires_explanation
        ),
    )

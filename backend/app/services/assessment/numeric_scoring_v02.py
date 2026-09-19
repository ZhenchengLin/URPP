"""
URPP Design 01C — Deterministic Numeric Scoring V0.2.

Accepts a single numeric answer. Does not execute student input.

Only explicitly reviewed problem attempts are supported here.
Transfer and retrieval assessment need separate validation rules.
"""

import math
import re

from app.domain.learning.models import EvidenceType

from app.domain.learning.state_v02 import EvidenceEventV02

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    StudentAttemptV02,
)


SCORING_POLICY_VERSION = "numeric-scoring-v0.2"

NUMERIC_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?"
)


def parse_numeric_answer(response_text: str) -> float | None:
    """Parse one finite number without evaluating expressions."""

    text = response_text.strip()

    if not text or len(text) > 64:
        return None

    if NUMERIC_PATTERN.fullmatch(text) is None:
        return None

    try:
        value = float(text)
    except (ValueError, OverflowError):
        return None

    if not math.isfinite(value):
        return None

    return value


def score_numeric_attempt(
    item: AssessmentItemV02,
    attempt: StudentAttemptV02,
) -> EvidenceEventV02:
    """
    Convert a reviewed numeric assessment attempt into evidence.

    The function is deterministic: the same item and attempt
    produce the same evidence record.
    """

    if (
        item.course_id != attempt.course_id
        or item.objective_id != attempt.objective_id
        or item.assessment_item_id != attempt.assessment_item_id
    ):
        raise ValueError(
            "Assessment item and student attempt do not match."
        )

    if not item.alignment_verified:
        raise ValueError(
            "Assessment objective alignment has not been verified."
        )

    if item.evidence_type != EvidenceType.PROBLEM_ATTEMPT:
        raise ValueError(
            "Only ordinary numeric problem attempts are "
            "supported by this scoring function."
        )

    answer = parse_numeric_answer(attempt.response_text)

    if answer is None:
        outcome = "neutral"
        correctness = None
        assessment_validity = "invalid"
        model_confidence = 0.0
        observation = (
            "The response could not be automatically scored "
            "as a single finite numeric answer."
        )

    else:
        is_correct = (
            abs(answer - item.rubric.expected_value)
            <= item.rubric.absolute_tolerance
        )

        outcome = "success" if is_correct else "failure"
        correctness = 1.0 if is_correct else 0.0
        assessment_validity = "valid"

        # Here 1.0 means the restricted numeric response was
        # parsed unambiguously. It is NOT a calibrated
        # probability of student mastery.
        model_confidence = 1.0

        observation = (
            "The submitted numeric answer was scored "
            "using the assessment item's rubric."
        )

    return EvidenceEventV02(
        evidence_id=f"numeric-v02:{attempt.attempt_id}",
        student_id=attempt.student_id,
        course_id=attempt.course_id,
        session_id=attempt.session_id,
        objective_id=attempt.objective_id,
        source_message_id=attempt.source_message_id,
        assessment_item_id=attempt.assessment_item_id,
        response_group_id=attempt.response_group_id,
        evidence_type=item.evidence_type,
        observation=observation,
        objective_alignment="direct",
        assessment_validity=assessment_validity,
        outcome=outcome,
        correctness=correctness,
        assistance_level=attempt.assistance_level,
        prior_solution_exposure=attempt.prior_solution_exposure,
        novelty=attempt.novelty,
        transfer_distance="none",
        model_confidence=model_confidence,
        scoring_policy_version=SCORING_POLICY_VERSION,
        created_at=attempt.submitted_at,
    )

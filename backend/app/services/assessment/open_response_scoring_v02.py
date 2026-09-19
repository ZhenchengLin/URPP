"""
URPP Design 01C — Open-Response Review Validation V0.2.

Validates a structured review and calculates a scoring preview.

IMPORTANT:
A reviewer's identity and semantic judgments are not authenticated
by this module. Its output must NOT be treated as mastery evidence.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.services.assessment.models_v02 import StudentAttemptV02

from app.services.assessment.open_response_models_v02 import (
    OpenResponseAssessmentItemV02,
    OpenResponseReviewV02,
)


class OpenResponseScoringPreviewV02(BaseModel):
    """A review-based score that has not been approved as evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str
    attempt_id: str

    outcome: Literal["success", "partial", "failure", "neutral"]
    correctness: float | None

    status: Literal[
        "requires_reviewer_confirmation",
        "requires_additional_review",
    ]

    scoring_policy_version: str = "open-response-preview-v0.2"


def preview_open_response_review(
    item: OpenResponseAssessmentItemV02,
    attempt: StudentAttemptV02,
    review: OpenResponseReviewV02,
) -> OpenResponseScoringPreviewV02:
    """
    Validate a review against its item and attempt, then score it.

    A supporting quote must occur verbatim in the student response.
    That check establishes textual provenance, NOT semantic accuracy.
    """

    if (
        item.course_id != attempt.course_id
        or item.objective_id != attempt.objective_id
        or item.assessment_item_id != attempt.assessment_item_id
    ):
        raise ValueError(
            "Assessment item and student attempt do not match."
        )

    if (
        review.attempt_id != attempt.attempt_id
        or review.assessment_item_id != item.assessment_item_id
    ):
        raise ValueError(
            "Review identity does not match its item and attempt."
        )

    if review.rubric_version != item.rubric.rubric_version:
        raise ValueError("Review rubric version does not match.")

    if review.reviewed_at < attempt.submitted_at:
        raise ValueError(
            "Review timestamp cannot precede the student attempt."
        )

    if not item.alignment_verified:
        raise ValueError(
            "Assessment alignment has not been verified."
        )

    rubric_criteria = {
        criterion.criterion_id: criterion
        for criterion in item.rubric.criteria
    }

    review_ids = [
        result.criterion_id
        for result in review.criteria
    ]

    if len(review_ids) != len(set(review_ids)):
        raise ValueError("Duplicate criterion reviews are not allowed.")

    if set(review_ids) != set(rubric_criteria):
        raise ValueError(
            "Review must cover every rubric criterion exactly once."
        )

    scores = {
        "met": 1.0,
        "partial": 0.5,
        "not_met": 0.0,
    }

    total = 0.0
    has_unscorable = False

    for result in review.criteria:
        if result.judgment in {"met", "partial"}:
            quote = result.supporting_quote

            if not quote or quote.strip() not in attempt.response_text:
                raise ValueError(
                    "Supporting quote was not found in "
                    "the student's response."
                )

        if result.judgment == "unscorable":
            has_unscorable = True
            continue

        total += (
            rubric_criteria[result.criterion_id].weight
            * scores[result.judgment]
        )

    # Do not silently treat an unscorable criterion as zero credit
    # or renormalize the remaining criteria.
    if has_unscorable:
        return OpenResponseScoringPreviewV02(
            review_id=review.review_id,
            attempt_id=attempt.attempt_id,
            outcome="neutral",
            correctness=None,
            status="requires_additional_review",
        )

    total = min(1.0, max(0.0, total))

    if total == 1.0:
        outcome = "success"
    elif total == 0.0:
        outcome = "failure"
    else:
        outcome = "partial"

    return OpenResponseScoringPreviewV02(
        review_id=review.review_id,
        attempt_id=attempt.attempt_id,
        outcome=outcome,
        correctness=total,
        status="requires_reviewer_confirmation",
    )

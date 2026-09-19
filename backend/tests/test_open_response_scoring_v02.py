"""
Design 01C — Open-response review scoring tests.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.assessment.models_v02 import StudentAttemptV02

from app.services.assessment.open_response_models_v02 import (
    CriterionReviewV02,
    OpenResponseAssessmentItemV02,
    OpenResponseCriterionV02,
    OpenResponseReviewV02,
    OpenResponseRubricV02,
)

from app.services.assessment.open_response_scoring_v02 import (
    preview_open_response_review,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)

ANSWER = (
    "The dot product sums coordinatewise products. "
    "It is zero for orthogonal vectors."
)


def make_item(**changes):
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-inner-product",
        prompt="Define the dot product and explain orthogonality.",
        rubric=OpenResponseRubricV02(
            rubric_version="inner-product-v1",
            criteria=[
                OpenResponseCriterionV02(
                    criterion_id="definition",
                    description="Define the operation.",
                    full_credit_guidance="Describe coordinatewise products.",
                    weight=0.6,
                ),
                OpenResponseCriterionV02(
                    criterion_id="geometry",
                    description="Explain orthogonality.",
                    full_credit_guidance="Connect zero dot product to orthogonality.",
                    weight=0.4,
                ),
            ],
        ),
        alignment_verified=True,
        alignment_reviewer_id="reviewer-001",
    )
    return item.model_copy(update=changes)


def make_attempt(**changes):
    attempt = StudentAttemptV02(
        attempt_id="attempt-001",
        student_id="student-001",
        course_id="course-001",
        session_id="session-001",
        objective_id="objective-inner-product",
        assessment_item_id="item-001",
        source_message_id="message-001",
        response_group_id="response-001",
        response_text=ANSWER,
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=NOW,
    )
    return attempt.model_copy(update=changes)


def criterion_review(
    identifier,
    judgment,
    quote=None,
):
    return CriterionReviewV02(
        criterion_id=identifier,
        judgment=judgment,
        supporting_quote=quote,
        explanation="Rubric-based reviewer observation.",
    )


def make_review(**changes):
    review = OpenResponseReviewV02(
        review_id="review-001",
        attempt_id="attempt-001",
        assessment_item_id="item-001",
        rubric_version="inner-product-v1",
        reviewer_id="reviewer-001",
        criteria=[
            criterion_review(
                "definition",
                "met",
                "sums coordinatewise products",
            ),
            criterion_review(
                "geometry",
                "partial",
                "zero for orthogonal vectors",
            ),
        ],
        reviewed_at=NOW + timedelta(seconds=1),
    )
    return review.model_copy(update=changes)


def test_valid_partial_review_produces_weighted_preview():
    result = preview_open_response_review(
        make_item(),
        make_attempt(),
        make_review(),
    )

    assert result.correctness == pytest.approx(0.8)
    assert result.outcome == "partial"
    assert result.status == "requires_reviewer_confirmation"


def test_all_met_produces_success_preview():
    review = make_review(
        criteria=[
            criterion_review(
                "definition",
                "met",
                "sums coordinatewise products",
            ),
            criterion_review(
                "geometry",
                "met",
                "zero for orthogonal vectors",
            ),
        ]
    )

    result = preview_open_response_review(
        make_item(),
        make_attempt(),
        review,
    )

    assert result.outcome == "success"
    assert result.correctness == 1.0


def test_all_not_met_produces_failure_preview():
    review = make_review(
        criteria=[
            criterion_review("definition", "not_met"),
            criterion_review("geometry", "not_met"),
        ]
    )

    result = preview_open_response_review(
        make_item(),
        make_attempt(),
        review,
    )

    assert result.outcome == "failure"
    assert result.correctness == 0.0


def test_unscorable_criterion_requires_additional_review():
    review = make_review(
        criteria=[
            criterion_review(
                "definition",
                "met",
                "sums coordinatewise products",
            ),
            criterion_review("geometry", "unscorable"),
        ]
    )

    result = preview_open_response_review(
        make_item(),
        make_attempt(),
        review,
    )

    assert result.outcome == "neutral"
    assert result.correctness is None
    assert result.status == "requires_additional_review"


def test_quote_must_occur_in_student_response():
    review = make_review(
        criteria=[
            criterion_review(
                "definition",
                "met",
                "a sentence the student never submitted",
            ),
            criterion_review("geometry", "not_met"),
        ]
    )

    with pytest.raises(ValueError, match="quote was not found"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_review_must_cover_every_criterion():
    review = make_review(
        criteria=[
            criterion_review(
                "definition",
                "met",
                "sums coordinatewise products",
            ),
        ]
    )

    with pytest.raises(ValueError, match="every rubric criterion"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_duplicate_criterion_reviews_are_rejected():
    repeated = criterion_review(
        "definition",
        "met",
        "sums coordinatewise products",
    )

    review = make_review(
        criteria=[repeated, repeated]
    )

    with pytest.raises(ValueError, match="Duplicate"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_mismatched_rubric_version_is_rejected():
    review = make_review(
        rubric_version="older-version"
    )

    with pytest.raises(ValueError, match="rubric version"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_mismatched_attempt_identity_is_rejected():
    review = make_review(attempt_id="another-attempt")

    with pytest.raises(ValueError, match="Review identity"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_unverified_alignment_is_rejected():
    item = make_item(alignment_verified=False)

    with pytest.raises(ValueError, match="alignment"):
        preview_open_response_review(
            item,
            make_attempt(),
            make_review(),
        )


def test_review_cannot_precede_attempt():
    review = make_review(
        reviewed_at=NOW - timedelta(seconds=1)
    )

    with pytest.raises(ValueError, match="timestamp"):
        preview_open_response_review(
            make_item(),
            make_attempt(),
            review,
        )


def test_scoring_preview_is_not_mastery_evidence():
    result = preview_open_response_review(
        make_item(),
        make_attempt(),
        make_review(),
    )

    assert result.status == "requires_reviewer_confirmation"
    assert not hasattr(result, "evidence_id")
    assert not hasattr(result, "model_confidence")

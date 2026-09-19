"""
Design 01C — Open-response assessment contract tests.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.assessment.open_response_models_v02 import (
    CriterionReviewV02,
    OpenResponseAssessmentItemV02,
    OpenResponseCriterionV02,
    OpenResponseReviewV02,
    OpenResponseRubricV02,
)


def criterion(identifier, weight):
    return OpenResponseCriterionV02(
        criterion_id=identifier,
        description=f"Observable requirement {identifier}",
        full_credit_guidance="Describe the expected evidence.",
        weight=weight,
    )


def valid_rubric():
    return OpenResponseRubricV02(
        rubric_version="explanation-rubric-v1",
        criteria=[
            criterion("definition", 0.5),
            criterion("example", 0.5),
        ],
    )


def test_valid_rubric_and_assessment_item():
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="Explain the concept and provide an example.",
        rubric=valid_rubric(),
        alignment_verified=True,
        alignment_reviewer_id="reviewer-001",
    )

    assert item.alignment_verified is True
    assert len(item.rubric.criteria) == 2


def test_duplicate_criterion_ids_are_rejected():
    with pytest.raises(ValidationError, match="unique"):
        OpenResponseRubricV02(
            rubric_version="v1",
            criteria=[
                criterion("same", 0.5),
                criterion("same", 0.5),
            ],
        )


def test_rubric_weights_must_total_one():
    with pytest.raises(ValidationError, match="total 1.0"):
        OpenResponseRubricV02(
            rubric_version="v1",
            criteria=[
                criterion("first", 0.2),
                criterion("second", 0.2),
            ],
        )


def test_verified_alignment_requires_reviewer():
    with pytest.raises(ValidationError, match="reviewer ID"):
        OpenResponseAssessmentItemV02(
            assessment_item_id="item-001",
            course_id="course-001",
            objective_id="objective-001",
            prompt="Explain the concept.",
            rubric=valid_rubric(),
            alignment_verified=True,
        )


def test_awarded_credit_requires_supporting_quote():
    with pytest.raises(ValidationError, match="quote"):
        CriterionReviewV02(
            criterion_id="definition",
            judgment="met",
            explanation="The definition is present.",
        )


def test_not_met_criterion_can_have_no_quote():
    result = CriterionReviewV02(
        criterion_id="definition",
        judgment="not_met",
        explanation="No definition was provided.",
    )

    assert result.supporting_quote is None


def test_review_requires_timezone_aware_timestamp():
    with pytest.raises(ValidationError, match="timezone"):
        OpenResponseReviewV02(
            review_id="review-001",
            attempt_id="attempt-001",
            assessment_item_id="item-001",
            rubric_version="v1",
            reviewer_id="reviewer-001",
            criteria=[
                CriterionReviewV02(
                    criterion_id="definition",
                    judgment="met",
                    supporting_quote="A definition from the answer",
                    explanation="The criterion was met.",
                )
            ],
            reviewed_at=datetime(2026, 9, 19),
        )


def test_valid_review_can_be_created():
    review = OpenResponseReviewV02(
        review_id="review-001",
        attempt_id="attempt-001",
        assessment_item_id="item-001",
        rubric_version="explanation-rubric-v1",
        reviewer_id="reviewer-001",
        criteria=[
            CriterionReviewV02(
                criterion_id="definition",
                judgment="met",
                supporting_quote="An example from the answer",
                explanation="The requirement was met.",
            )
        ],
        reviewed_at=datetime(
            2026, 9, 19, tzinfo=timezone.utc
        ),
    )

    assert review.criteria[0].judgment == "met"

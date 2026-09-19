"""
URPP Design 01C — Assessment pipeline integration tests.

Keys in this module are test fixtures, not production secrets.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.assessment.assessment_pipeline_v02 import (
    ApprovedOpenResponseSubmissionV02,
    AssessmentPipelineV02,
    NumericSubmissionV02,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
    StudentAttemptV02,
)

from app.services.assessment.numeric_scoring_v02 import (
    score_numeric_attempt,
)

from app.services.assessment.open_response_models_v02 import (
    CriterionReviewV02,
    OpenResponseAssessmentItemV02,
    OpenResponseCriterionV02,
    OpenResponseReviewV02,
    OpenResponseRubricV02,
)

from app.services.assessment.review_approval_v02 import (
    issue_review_approval,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)

KEY = b"URPP-assessment-pipeline-test-key-123456789"

WRONG_KEY = b"Different-URPP-test-verification-key-123456"


def numeric_submission():
    item = AssessmentItemV02(
        assessment_item_id="numeric-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="What is 2 + 3?",
        rubric=NumericRubricV02(
            expected_value=5.0,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )

    attempt = StudentAttemptV02(
        attempt_id="numeric-attempt-001",
        student_id="student-001",
        course_id="course-001",
        session_id="session-001",
        objective_id="objective-001",
        assessment_item_id="numeric-001",
        source_message_id="message-001",
        response_group_id="response-001",
        response_text="5",
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=NOW,
    )

    return NumericSubmissionV02(
        item=item,
        attempt=attempt,
    )


def open_response_submission():
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="open-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="Define the dot product.",
        rubric=OpenResponseRubricV02(
            rubric_version="dot-product-v1",
            criteria=[
                OpenResponseCriterionV02(
                    criterion_id="definition",
                    description="Define the dot product.",
                    full_credit_guidance=(
                        "Describe the sum of coordinatewise products."
                    ),
                    weight=1.0,
                )
            ],
        ),
        alignment_verified=True,
        alignment_reviewer_id="reviewer-001",
    )

    attempt = StudentAttemptV02(
        attempt_id="open-attempt-001",
        student_id="student-001",
        course_id="course-001",
        session_id="session-002",
        objective_id="objective-001",
        assessment_item_id="open-001",
        source_message_id="message-002",
        response_group_id="response-002",
        response_text=(
            "The dot product is the sum of "
            "coordinatewise products."
        ),
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=NOW,
    )

    review = OpenResponseReviewV02(
        review_id="review-001",
        attempt_id=attempt.attempt_id,
        assessment_item_id=item.assessment_item_id,
        rubric_version=item.rubric.rubric_version,
        reviewer_id="reviewer-001",
        criteria=[
            CriterionReviewV02(
                criterion_id="definition",
                judgment="met",
                supporting_quote=(
                    "sum of coordinatewise products"
                ),
                explanation="The definition is present.",
            )
        ],
        reviewed_at=NOW + timedelta(seconds=1),
    )

    approval = issue_review_approval(
        item,
        attempt,
        review,
        authenticated_reviewer_id="reviewer-001",
        approved_at=NOW + timedelta(seconds=2),
        scoring_confidence=0.95,
        signing_key=KEY,
    )

    return ApprovedOpenResponseSubmissionV02(
        item=item,
        attempt=attempt,
        review=review,
        approval=approval,
    )


def estimate(pipeline, submissions):
    return pipeline.estimate_from_assessments(
        submissions,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW + timedelta(seconds=3),
    )


def test_numeric_assessment_reaches_state_engine():
    result = estimate(
        AssessmentPipelineV02(),
        [numeric_submission()],
    )

    assert result.performance_estimate == 1.0
    assert result.distinct_assessment_count == 1
    assert result.state.value == "unknown"


def test_signed_open_response_reaches_state_engine():
    result = estimate(
        AssessmentPipelineV02(verification_key=KEY),
        [open_response_submission()],
    )

    assert result.performance_estimate == 1.0
    assert result.distinct_assessment_count == 1
    assert result.state.value == "unknown"


def test_open_response_without_verification_key_is_rejected():
    with pytest.raises(ValueError, match="verification key"):
        estimate(
            AssessmentPipelineV02(),
            [open_response_submission()],
        )


def test_wrong_verification_key_is_rejected():
    with pytest.raises(ValueError, match="signature"):
        estimate(
            AssessmentPipelineV02(
                verification_key=WRONG_KEY
            ),
            [open_response_submission()],
        )


def test_preconstructed_evidence_cannot_enter_pipeline():
    submission = numeric_submission()

    preconstructed_evidence = score_numeric_attempt(
        submission.item,
        submission.attempt,
    )

    with pytest.raises(TypeError, match="supported assessment"):
        estimate(
            AssessmentPipelineV02(),
            [preconstructed_evidence],
        )


def test_mismatched_student_scope_is_rejected():
    submission = numeric_submission()

    with pytest.raises(ValueError):
        AssessmentPipelineV02().estimate_from_assessments(
            [submission],
            student_id="a-different-student",
            course_id="course-001",
            objective_id="objective-001",
            as_of=NOW + timedelta(seconds=3),
        )

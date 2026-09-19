"""
URPP Design 01C — Signed review approval tests.

The signing key below is a TEST-ONLY fixture, not a deployment key.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.assessment.models_v02 import (
    StudentAttemptV02,
)

from app.services.assessment.open_response_models_v02 import (
    CriterionReviewV02,
    OpenResponseAssessmentItemV02,
    OpenResponseCriterionV02,
    OpenResponseReviewV02,
    OpenResponseRubricV02,
)

from app.services.assessment.review_approval_v02 import (
    finalize_approved_review,
    issue_review_approval,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)
KEY = b"URPP-unit-test-signing-key-not-for-production-123"

ANSWER = (
    "The dot product sums coordinatewise products. "
    "It is zero for orthogonal vectors."
)


def make_records():
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-inner-product",
        prompt="Define dot product and explain orthogonality.",
        rubric=OpenResponseRubricV02(
            rubric_version="inner-product-v1",
            criteria=[
                OpenResponseCriterionV02(
                    criterion_id="definition",
                    description="Define the operation.",
                    full_credit_guidance="Describe the dot product.",
                    weight=0.6,
                ),
                OpenResponseCriterionV02(
                    criterion_id="geometry",
                    description="Explain orthogonality.",
                    full_credit_guidance="Explain the zero dot product.",
                    weight=0.4,
                ),
            ],
        ),
        alignment_verified=True,
        alignment_reviewer_id="reviewer-001",
    )

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

    review = OpenResponseReviewV02(
        review_id="review-001",
        attempt_id="attempt-001",
        assessment_item_id="item-001",
        rubric_version="inner-product-v1",
        reviewer_id="reviewer-001",
        criteria=[
            CriterionReviewV02(
                criterion_id="definition",
                judgment="met",
                supporting_quote="sums coordinatewise products",
                explanation="The response defines the operation.",
            ),
            CriterionReviewV02(
                criterion_id="geometry",
                judgment="partial",
                supporting_quote="zero for orthogonal vectors",
                explanation="The geometric interpretation is partial.",
            ),
        ],
        reviewed_at=NOW + timedelta(seconds=1),
    )

    return item, attempt, review


def approve(item, attempt, review, **changes):
    parameters = {
        "authenticated_reviewer_id": "reviewer-001",
        "approved_at": NOW + timedelta(seconds=2),
        "scoring_confidence": 0.95,
        "signing_key": KEY,
    }
    parameters.update(changes)

    return issue_review_approval(
        item,
        attempt,
        review,
        **parameters,
    )


def test_signed_review_generates_evidence():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    evidence = finalize_approved_review(
        item,
        attempt,
        review,
        approval,
        verification_key=KEY,
    )

    assert evidence.outcome == "partial"
    assert evidence.correctness == pytest.approx(0.8)
    assert evidence.assessment_validity.value == "valid"
    assert evidence.model_confidence == 0.95
    assert evidence.assessment_item_id == attempt.assessment_item_id
    assert evidence.created_at == approval.approved_at


def test_approved_evidence_reaches_state_engine():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    evidence = finalize_approved_review(
        item,
        attempt,
        review,
        approval,
        verification_key=KEY,
    )

    state = estimate_objective_state(
        [evidence],
        student_id=attempt.student_id,
        course_id=attempt.course_id,
        objective_id=attempt.objective_id,
        as_of=approval.approved_at,
    )

    assert evidence.evidence_id in state.included_evidence_ids
    assert state.state.value == "unknown"


def test_forged_signature_is_rejected():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    forged = approval.model_copy(
        update={"signature": "0" * 64}
    )

    with pytest.raises(ValueError, match="signature"):
        finalize_approved_review(
            item,
            attempt,
            review,
            forged,
            verification_key=KEY,
        )


def test_modifying_student_response_invalidates_approval():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    changed_attempt = attempt.model_copy(
        update={
            "response_text": ANSWER + " An extra sentence."
        }
    )

    with pytest.raises(ValueError, match="signature"):
        finalize_approved_review(
            item,
            changed_attempt,
            review,
            approval,
            verification_key=KEY,
        )


def test_modifying_review_invalidates_approval():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    changed_review = review.model_copy(
        update={
            "criteria": [
                review.criteria[0],
                CriterionReviewV02(
                    criterion_id="geometry",
                    judgment="met",
                    supporting_quote="zero for orthogonal vectors",
                    explanation="Changed scoring judgment.",
                ),
            ]
        }
    )

    with pytest.raises(ValueError, match="signature"):
        finalize_approved_review(
            item,
            attempt,
            changed_review,
            approval,
            verification_key=KEY,
        )


def test_unscorable_review_cannot_be_approved():
    item, attempt, review = make_records()

    unscorable = review.model_copy(
        update={
            "criteria": [
                review.criteria[0],
                CriterionReviewV02(
                    criterion_id="geometry",
                    judgment="unscorable",
                    explanation="Insufficient basis for scoring.",
                ),
            ]
        }
    )

    with pytest.raises(ValueError, match="Unscorable"):
        approve(item, attempt, unscorable)


def test_reviewer_identity_must_match():
    item, attempt, review = make_records()

    with pytest.raises(ValueError, match="Authenticated reviewer"):
        approve(
            item,
            attempt,
            review,
            authenticated_reviewer_id="different-reviewer",
        )


def test_approval_cannot_precede_review():
    item, attempt, review = make_records()

    with pytest.raises(ValueError, match="precede"):
        approve(
            item,
            attempt,
            review,
            approved_at=NOW,
        )


def test_approval_is_bound_to_rubric():
    item, attempt, review = make_records()
    approval = approve(item, attempt, review)

    modified_item = item.model_copy(
        update={
            "prompt": (
                "A different prompt with the same assessment ID."
            )
        }
    )

    with pytest.raises(ValueError, match="signature"):
        finalize_approved_review(
            modified_item,
            attempt,
            review,
            approval,
            verification_key=KEY,
        )


def test_weak_review_confidence_does_not_establish_state():
    item, attempt, review = make_records()

    approval = approve(
        item,
        attempt,
        review,
        scoring_confidence=0.2,
    )

    evidence = finalize_approved_review(
        item,
        attempt,
        review,
        approval,
        verification_key=KEY,
    )

    state = estimate_objective_state(
        [evidence],
        student_id=attempt.student_id,
        course_id=attempt.course_id,
        objective_id=attempt.objective_id,
        as_of=approval.approved_at,
    )

    assert evidence.evidence_id not in state.included_evidence_ids

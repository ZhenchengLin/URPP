"""
URPP Design 01C — Numeric Scoring Tests.

Tests the deterministic Assessment -> Evidence -> State pipeline.
"""

from datetime import datetime, timezone

import pytest

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
    StudentAttemptV02,
)

from app.services.assessment.numeric_scoring_v02 import (
    parse_numeric_answer,
    score_numeric_attempt,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def make_item(
    *,
    item_id="item-001",
    expected=5.0,
    tolerance=0.0,
    alignment_verified=True,
    evidence_type=EvidenceType.PROBLEM_ATTEMPT,
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id="objective-addition",
        prompt="Enter the numeric answer.",
        evidence_type=evidence_type,
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=tolerance,
            rubric_version="numeric-rubric-test-v1",
        ),
        alignment_verified=alignment_verified,
    )


def make_attempt(
    *,
    attempt_id="attempt-001",
    item_id="item-001",
    response="5",
    session_id="session-001",
):
    return StudentAttemptV02(
        attempt_id=attempt_id,
        student_id="student-001",
        course_id="course-001",
        session_id=session_id,
        objective_id="objective-addition",
        assessment_item_id=item_id,
        source_message_id=f"message-{attempt_id}",
        response_group_id=f"response-{attempt_id}",
        response_text=response,
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=NOW,
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5", 5.0),
        ("5.0", 5.0),
        (".5", 0.5),
        ("-2.5", -2.5),
        ("+5", 5.0),
        ("5e0", 5.0),
        ("1.25E+2", 125.0),
    ],
)
def test_valid_numeric_formats(text, expected):
    assert parse_numeric_answer(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "I don't know",
        "2+3",
        "5 meters",
        "5,000",
        "nan",
        "inf",
        "1e309",
        "5 5",
    ],
)
def test_invalid_numeric_formats(text):
    assert parse_numeric_answer(text) is None


def test_correct_response_generates_success_evidence():
    evidence = score_numeric_attempt(
        make_item(),
        make_attempt(),
    )

    assert evidence.outcome == "success"
    assert evidence.correctness == 1.0
    assert evidence.assessment_validity.value == "valid"
    assert evidence.objective_alignment.value == "direct"
    assert evidence.assessment_item_id == "item-001"


def test_incorrect_response_generates_failure_evidence():
    evidence = score_numeric_attempt(
        make_item(),
        make_attempt(response="8"),
    )

    assert evidence.outcome == "failure"
    assert evidence.correctness == 0.0
    assert evidence.assessment_validity.value == "valid"


def test_numeric_tolerance_is_respected():
    evidence = score_numeric_attempt(
        make_item(expected=1.0, tolerance=0.02),
        make_attempt(response="1.01"),
    )

    assert evidence.outcome == "success"


def test_unparseable_response_is_not_automatically_incorrect():
    evidence = score_numeric_attempt(
        make_item(),
        make_attempt(response="I need another explanation"),
    )

    assert evidence.outcome == "neutral"
    assert evidence.correctness is None
    assert evidence.assessment_validity.value == "invalid"


def test_unverified_alignment_is_rejected():
    with pytest.raises(ValueError, match="alignment"):
        score_numeric_attempt(
            make_item(alignment_verified=False),
            make_attempt(),
        )


def test_mismatched_assessment_identity_is_rejected():
    with pytest.raises(ValueError, match="do not match"):
        score_numeric_attempt(
            make_item(),
            make_attempt(item_id="different-item"),
        )


def test_transfer_assessment_is_not_silently_supported():
    with pytest.raises(ValueError, match="ordinary numeric"):
        score_numeric_attempt(
            make_item(
                evidence_type=EvidenceType.TRANSFER_ATTEMPT
            ),
            make_attempt(),
        )


def test_scoring_is_deterministic():
    item = make_item()
    attempt = make_attempt()

    first = score_numeric_attempt(item, attempt)
    second = score_numeric_attempt(item, attempt)

    assert first.model_dump() == second.model_dump()


def test_one_correct_answer_does_not_establish_competence():
    evidence = score_numeric_attempt(
        make_item(),
        make_attempt(),
    )

    state = estimate_objective_state(
        [evidence],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-addition",
        as_of=NOW,
    )

    assert evidence.evidence_id in state.included_evidence_ids
    assert state.performance_estimate == 1.0
    assert state.state.value == "unknown"


def test_two_distinct_independent_successes_can_establish_competence():
    first = score_numeric_attempt(
        make_item(item_id="item-001", expected=5.0),
        make_attempt(
            attempt_id="attempt-001",
            item_id="item-001",
            response="5",
        ),
    )

    second = score_numeric_attempt(
        make_item(item_id="item-002", expected=7.0),
        make_attempt(
            attempt_id="attempt-002",
            item_id="item-002",
            response="7",
        ),
    )

    state = estimate_objective_state(
        [first, second],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-addition",
        as_of=NOW,
    )

    assert state.distinct_assessment_count == 2
    assert state.independent_success_count == 2
    assert state.state.value == "competent"

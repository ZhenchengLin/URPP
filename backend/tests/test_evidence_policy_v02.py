from datetime import datetime, timezone

import pytest

from app.domain.learning.models import EvidenceType

from app.domain.learning.state_v02 import (
    AssessmentValidity,
    EvidenceEventV02,
    ObjectiveAlignment,
)

from app.services.student_model.eligibility_v02 import (
    evaluate_evidence,
)

from app.services.student_model.policy_v02 import (
    StatePolicyV02,
)


POLICY = StatePolicyV02()


def make_event(**changes):
    values = {
        "evidence_id": "evidence-001",
        "student_id": "student-001",
        "course_id": "course-001",
        "session_id": "session-001",
        "objective_id": "objective-001",
        "assessment_item_id": "item-001",
        "response_group_id": "response-001",
        "evidence_type": EvidenceType.PROBLEM_ATTEMPT,
        "observation": "Student solved the problem.",
        "objective_alignment": ObjectiveAlignment.DIRECT,
        "assessment_validity": AssessmentValidity.VALID,
        "outcome": "success",
        "correctness": 1.0,
        "assistance_level": 0,
        "prior_solution_exposure": False,
        "novelty": "novel",
        "transfer_distance": "none",
        "model_confidence": 0.9,
        "scoring_policy_version": "evidence-scoring-v0.2",
        "created_at": datetime(
            2026, 9, 18, tzinfo=timezone.utc
        ),
    }

    values.update(changes)

    return EvidenceEventV02(**values)


def test_independent_novel_success():
    event = make_event()

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is True
    assert result.diagnostic_weight == pytest.approx(0.9)


def test_assistance_reduces_weight():
    independent = make_event(assistance_level=0)
    assisted = make_event(assistance_level=5)

    result_a = evaluate_evidence(independent, POLICY)
    result_b = evaluate_evidence(assisted, POLICY)

    assert result_a.eligible is True
    assert result_b.eligible is True

    assert result_b.diagnostic_weight < result_a.diagnostic_weight

    assert result_b.diagnostic_weight == pytest.approx(0.135)


def test_full_walkthrough_is_not_performance_evidence():
    event = make_event(assistance_level=6)

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False
    assert result.reason == "zero_diagnostic_weight"


def test_self_report_is_excluded():
    event = make_event(
        evidence_type=EvidenceType.STUDENT_SELF_REPORT
    )

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False
    assert result.reason == "not_performance_evidence"


def test_unaligned_assessment_is_excluded():
    event = make_event(
        objective_alignment=ObjectiveAlignment.INDIRECT
    )

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False


def test_low_confidence_is_excluded():
    event = make_event(model_confidence=0.4)

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False
    assert result.reason == "interpretation_confidence_too_low"


def test_missing_assessment_id_is_excluded():
    event = make_event(assessment_item_id=None)

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False
    assert result.reason == "assessment_identity_missing"


def test_solution_exposure_reduces_weight():
    unseen = make_event(prior_solution_exposure=False)
    exposed = make_event(prior_solution_exposure=True)

    result_a = evaluate_evidence(unseen, POLICY)
    result_b = evaluate_evidence(exposed, POLICY)

    assert result_b.diagnostic_weight < result_a.diagnostic_weight
    assert result_b.diagnostic_weight == pytest.approx(0.315)


def test_invalid_assessment_is_excluded():
    event = make_event(
        assessment_validity=AssessmentValidity.INVALID
    )

    result = evaluate_evidence(event, POLICY)

    assert result.eligible is False
    assert result.reason == "assessment_not_valid"

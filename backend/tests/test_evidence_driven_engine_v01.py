"""
URPP Implementation 13E-1.

Selection tests use a real empty-evidence state and
explicitly labeled synthetic state snapshots.

Synthetic state snapshots test decision behavior only;
they are not evidence that a student achieved mastery.
"""

from datetime import datetime, timezone

import pytest

from app.domain.learning.models import (
    ObjectiveStateLabel,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)

from app.services.decision.models_v01 import (
    DecisionContextV01,
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.decision.transfer_delivery_gate_v01 import (
    require_trusted_transfer_delivery_v01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


def unknown_state():
    return estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )


def synthetic_state(
    *,
    label,
    included_count=1,
    distinct_count=1,
    independent_successes=0,
):
    """
    A synthetic contract fixture, NOT a real student estimate.
    """

    return unknown_state().model_copy(
        update={
            "state": label,
            "included_evidence_ids": [
                f"evidence-{index}"
                for index in range(included_count)
            ],
            "distinct_assessment_count": distinct_count,
            "independent_success_count": independent_successes,
        }
    )


def context(
    state=None,
    *,
    request_kind=None,
):
    if state is None:
        state = unknown_state()

    request = None

    if request_kind is not None:
        request = StudentLearningRequestV01(
            objective_id=state.objective_id,
            request_kind=request_kind,
            requested_at=NOW,
        )

    return PersonalizedDecisionContextV01(
        decision_context=DecisionContextV01(
            decision_id="decision-001",
            objective_state=state,
            requested_at=NOW,
        ),
        student_request=request,
    )


def decide(
    state=None,
    *,
    request_kind=None,
):
    return EvidenceDrivenDecisionEngineV01().decide(
        context(
            state,
            request_kind=request_kind,
        )
    )


def test_unknown_with_no_evidence_selects_diagnostic():
    result = decide()

    assert result.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EVIDENCE_DRIVEN
    )

    assert result.selected_for_request is False

    assert "included_evidence_count=0" in (
        result.selection_reason
    )


def test_excluded_only_evidence_does_not_replace_diagnostic():
    state = unknown_state().model_copy(
        update={
            "excluded_evidence_ids": ["excluded-001"],
        }
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )


def test_unknown_with_included_assessments_selects_practice():
    state = synthetic_state(
        label=ObjectiveStateLabel.UNKNOWN,
        included_count=1,
        distinct_count=1,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )


@pytest.mark.parametrize(
    "label",
    [
        ObjectiveStateLabel.EMERGING,
        ObjectiveStateLabel.DEVELOPING,
    ],
)
def test_early_state_without_independent_success_selects_hint(
    label,
):
    state = synthetic_state(
        label=label,
        independent_successes=0,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_HINT
    )


def test_early_state_without_included_evidence_selects_review():
    state = synthetic_state(
        label=ObjectiveStateLabel.EMERGING,
        included_count=0,
        distinct_count=0,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )


def test_early_state_with_independent_success_selects_practice():
    state = synthetic_state(
        label=ObjectiveStateLabel.DEVELOPING,
        independent_successes=1,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert "independent_success_count=1" in (
        result.selection_reason
    )


def test_competent_with_independent_success_selects_practice():
    state = synthetic_state(
        label=ObjectiveStateLabel.COMPETENT,
        included_count=2,
        distinct_count=2,
        independent_successes=2,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )


def test_competent_without_independent_success_selects_explanation():
    state = synthetic_state(
        label=ObjectiveStateLabel.COMPETENT,
        independent_successes=0,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.SELF_EXPLANATION
    )


def test_strong_with_independent_success_selects_explanation():
    state = synthetic_state(
        label=ObjectiveStateLabel.STRONG,
        included_count=3,
        distinct_count=3,
        independent_successes=2,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.SELF_EXPLANATION
    )


def test_strong_without_independent_success_seeks_practice():
    state = synthetic_state(
        label=ObjectiveStateLabel.STRONG,
        independent_successes=0,
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )


@pytest.mark.parametrize(
    "label",
    [
        ObjectiveStateLabel.COMPETENT,
        ObjectiveStateLabel.STRONG,
    ],
)
def test_automatic_selection_never_proposes_blocked_transfer(
    label,
):
    state = synthetic_state(
        label=label,
        included_count=3,
        distinct_count=3,
        independent_successes=2,
    )

    result = decide(state)

    assert result.decision.selected_action != (
        TeachingActionV01.TRANSFER_ASSESSMENT
    )

    assert TeachingActionV01.TRANSFER_ASSESSMENT not in (
        result.decision.allowed_actions
    )

    assert (
        result.decision.selected_action
        in result.decision.allowed_actions
    )


def test_explicit_explanation_request_preserves_student_choice():
    result = decide(
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        )
    )

    assert result.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )

    assert result.selected_for_request is True


def test_explicit_independent_request_preserves_student_choice():
    result = decide(
        request_kind=(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        )
    )

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )


def test_explicit_transfer_request_preserves_selection_but_not_delivery():
    state = synthetic_state(
        label=ObjectiveStateLabel.COMPETENT,
        included_count=2,
        distinct_count=2,
        independent_successes=2,
    )

    result = decide(
        state,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_TRANSFER
        ),
    )

    assert result.decision.selected_action == (
        TeachingActionV01.TRANSFER_ASSESSMENT
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action=result.decision.selected_action
        )


def test_no_request_does_not_modify_authoritative_state():
    state = synthetic_state(
        label=ObjectiveStateLabel.DEVELOPING,
        included_count=2,
        distinct_count=2,
        independent_successes=1,
    )

    before = state.model_dump(mode="json")

    result = decide(state)

    assert state.model_dump(mode="json") == before

    assert result.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )


def test_wrong_context_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="PersonalizedDecisionContextV01",
    ):
        EvidenceDrivenDecisionEngineV01().decide(
            object()
        )


def test_auto_result_has_distinct_provenance_and_policy_version():
    result = decide()

    assert result.decision.controller_version == (
        EvidenceDrivenDecisionEngineV01.VERSION
    )

    assert result.decision.policy_version == (
        EvidenceDrivenDecisionEngineV01.POLICY_VERSION
    )

    assert result.request_expanded_allowed_actions is False
    assert result.decision.fallback_used is False


def test_unknown_assistance_provenance_selects_review_not_mastery():
    """
    This synthetic snapshot tests the policy response to
    excluded evidence. It is not a student-mastery estimate.
    """

    state = unknown_state().model_copy(
        update={
            "excluded_evidence_ids": [
                "excluded-attempt-001",
            ],
            "exclusion_reasons": {
                "excluded-attempt-001":
                    "assistance_level_unknown",
            },
        }
    )

    before = state.model_dump(mode="json")

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EVIDENCE_DRIVEN
    )

    assert "assistance_level_unknown" in (
        result.selection_reason
    )

    assert state.included_evidence_ids == []
    assert state.independent_success_count == 0

    assert state.model_dump(mode="json") == before


def test_other_exclusion_reasons_do_not_trigger_assistance_fallback():
    state = unknown_state().model_copy(
        update={
            "excluded_evidence_ids": [
                "excluded-attempt-001",
            ],
            "exclusion_reasons": {
                "excluded-attempt-001":
                    "assessment_identity_missing",
            },
        }
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )


def test_mixed_exclusion_reasons_do_not_trigger_assistance_fallback():
    state = unknown_state().model_copy(
        update={
            "excluded_evidence_ids": [
                "excluded-attempt-001",
                "excluded-attempt-002",
            ],
            "exclusion_reasons": {
                "excluded-attempt-001":
                    "assistance_level_unknown",
                "excluded-attempt-002":
                    "assessment_identity_missing",
            },
        }
    )

    result = decide(state)

    assert result.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )


def test_explicit_diagnostic_request_still_overrides_provenance_fallback():
    state = unknown_state().model_copy(
        update={
            "excluded_evidence_ids": [
                "excluded-attempt-001",
            ],
            "exclusion_reasons": {
                "excluded-attempt-001":
                    "assistance_level_unknown",
            },
        }
    )

    result = decide(
        state,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC
        ),
    )

    assert result.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert result.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )

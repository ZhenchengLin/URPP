"""
URPP Design 01D — Logical Decision Engine tests.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.learning.models import ObjectiveStateLabel

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)

from app.services.decision.models_v01 import (
    DecisionContextV01,
    DecisionProposalV01,
    TeachingActionV01,
)

from app.services.decision.policy_v01 import (
    PedagogicalPolicyV01,
)

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def unknown_state():
    return estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )


def context(state=None):
    return DecisionContextV01(
        decision_id="decision-001",
        objective_state=state or unknown_state(),
        requested_at=NOW,
    )


def test_unknown_state_allows_diagnostic_assessment():
    allowed = PedagogicalPolicyV01().allowed_actions(
        context()
    )

    assert TeachingActionV01.DIAGNOSTIC_ASSESSMENT in allowed


def test_unknown_state_does_not_allow_transfer_assessment():
    allowed = PedagogicalPolicyV01().allowed_actions(
        context()
    )

    assert TeachingActionV01.TRANSFER_ASSESSMENT not in allowed


def test_rule_based_controller_selects_diagnostic_first():
    result = DecisionEngineV01(
        RuleBasedControllerV01()
    ).decide(context())

    assert (
        result.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert result.fallback_used is False


def test_competent_state_allows_transfer_assessment():
    synthetic_state = unknown_state().model_copy(
        update={
            "state": ObjectiveStateLabel.COMPETENT,
            "distinct_assessment_count": 2,
            "independent_success_count": 2,
        }
    )

    allowed = PedagogicalPolicyV01().allowed_actions(
        context(synthetic_state)
    )

    assert TeachingActionV01.TRANSFER_ASSESSMENT in allowed
    assert TeachingActionV01.DIAGNOSTIC_ASSESSMENT not in allowed


class DisallowedController:
    def propose(self, context, allowed_actions):
        return DecisionProposalV01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
            model_version="invalid-controller-v1",
            rationale="Proposed a disallowed action.",
        )


def test_disallowed_proposal_triggers_fallback():
    result = DecisionEngineV01(
        DisallowedController()
    ).decide(context())

    assert result.fallback_used is True

    assert (
        result.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert (
        TeachingActionV01.TRANSFER_ASSESSMENT
        not in result.allowed_actions
    )


class TimeoutController:
    def propose(self, context, allowed_actions):
        raise TimeoutError("Model unavailable.")


def test_controller_timeout_triggers_fallback():
    result = DecisionEngineV01(
        TimeoutController()
    ).decide(context())

    assert result.fallback_used is True

    assert result.controller_version == (
        RuleBasedControllerV01.VERSION
    )


class InvalidOutputController:
    def propose(self, context, allowed_actions):
        return {
            "selected_action": "transfer_assessment"
        }


def test_unstructured_output_triggers_fallback():
    result = DecisionEngineV01(
        InvalidOutputController()
    ).decide(context())

    assert result.fallback_used is True
    assert result.selected_action in result.allowed_actions


def test_decision_does_not_modify_student_state():
    original_state = unknown_state()
    before = original_state.model_dump()

    DecisionEngineV01(
        RuleBasedControllerV01()
    ).decide(context(original_state))

    assert original_state.model_dump() == before


def test_decision_timestamp_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="timezone"):
        DecisionContextV01(
            decision_id="decision-001",
            objective_state=unknown_state(),
            requested_at=datetime(2026, 9, 19),
        )


def test_decision_cannot_precede_state_snapshot():
    with pytest.raises(ValidationError, match="precede"):
        DecisionContextV01(
            decision_id="decision-001",
            objective_state=unknown_state(),
            requested_at=datetime(
                2026, 9, 18, tzinfo=timezone.utc
            ),
        )

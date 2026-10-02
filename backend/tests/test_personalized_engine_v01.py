"""
URPP Implementation 13B-2 personalized selection tests.
"""

from datetime import datetime, timezone

import pytest

from app.domain.learning.models import ObjectiveStateLabel

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)

from app.services.decision.models_v01 import (
    DecisionContextV01,
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
    PersonalizedDecisionEngineV01,
)

from app.services.decision.policy_v01 import (
    PedagogicalPolicyV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def make_state(label=ObjectiveStateLabel.UNKNOWN):
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )

    if label == ObjectiveStateLabel.UNKNOWN:
        return state

    # Synthetic states are used only to test decision routing.
    # They are not persisted or treated as real mastery evidence.
    return state.model_copy(
        update={"state": label}
    )


def make_context(
    label=ObjectiveStateLabel.UNKNOWN,
    request_kind=None,
):
    decision_context = DecisionContextV01(
        decision_id="decision-001",
        objective_state=make_state(label),
        requested_at=NOW,
    )

    request = None

    if request_kind is not None:
        request = StudentLearningRequestV01(
            objective_id="objective-001",
            request_kind=request_kind,
            requested_at=NOW,
        )

    return PersonalizedDecisionContextV01(
        decision_context=decision_context,
        student_request=request,
    )


def test_no_request_uses_existing_baseline():
    context = make_context()

    result = PersonalizedDecisionEngineV01().decide(
        context
    )

    expected = DecisionEngineV01(
        RuleBasedControllerV01()
    ).decide(context.decision_context)

    assert result.decision == expected

    assert (
        result.selection_source
        == DecisionSelectionSourceV01.BASELINE
    )

    assert result.selected_for_request is False

    assert (
        result.request_expanded_allowed_actions
        is False
    )


@pytest.mark.parametrize(
    ("request_kind", "expected_action"),
    [
        (
            StudentLearningRequestKindV01.REQUEST_EXPLANATION,
            TeachingActionV01.CONCEPTUAL_REVIEW,
        ),
        (
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY,
            TeachingActionV01.INDEPENDENT_PRACTICE,
        ),
        (
            StudentLearningRequestKindV01.REQUEST_HINT,
            TeachingActionV01.CONCEPTUAL_HINT,
        ),
        (
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC,
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
        ),
        (
            StudentLearningRequestKindV01.REQUEST_SELF_EXPLANATION,
            TeachingActionV01.SELF_EXPLANATION,
        ),
        (
            StudentLearningRequestKindV01.REQUEST_TRANSFER,
            TeachingActionV01.TRANSFER_ASSESSMENT,
        ),
    ],
)
def test_each_explicit_request_selects_its_action(
    request_kind,
    expected_action,
):
    context = make_context(
        request_kind=request_kind
    )

    result = PersonalizedDecisionEngineV01().decide(
        context
    )

    assert result.decision.selected_action == expected_action

    assert (
        expected_action
        in result.decision.allowed_actions
    )

    assert result.selected_for_request is True

    assert (
        result.selection_source
        == DecisionSelectionSourceV01
        .EXPLICIT_STUDENT_REQUEST
    )


def test_strong_student_can_request_conceptual_review():
    context = make_context(
        label=ObjectiveStateLabel.STRONG,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    baseline_allowed = PedagogicalPolicyV01().allowed_actions(
        context.decision_context
    )

    assert (
        TeachingActionV01.CONCEPTUAL_REVIEW
        not in baseline_allowed
    )

    result = PersonalizedDecisionEngineV01().decide(
        context
    )

    assert (
        result.decision.selected_action
        == TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert result.request_expanded_allowed_actions is True

    assert (
        result.decision.policy_version
        == PersonalizedDecisionEngineV01.POLICY_VERSION
    )


def test_request_already_allowed_does_not_expand_action_set():
    context = make_context(
        request_kind=(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    baseline_allowed = PedagogicalPolicyV01().allowed_actions(
        context.decision_context
    )

    result = PersonalizedDecisionEngineV01().decide(
        context
    )

    assert result.request_expanded_allowed_actions is False

    assert result.decision.allowed_actions == baseline_allowed


def test_request_does_not_modify_authoritative_student_state():
    context = make_context(
        label=ObjectiveStateLabel.STRONG,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    state = context.decision_context.objective_state
    before = state.model_dump(mode="json")

    PersonalizedDecisionEngineV01().decide(context)

    assert state.model_dump(mode="json") == before


def test_personalized_engine_rejects_legacy_context():
    legacy_context = make_context().decision_context

    with pytest.raises(
        TypeError,
        match="PersonalizedDecisionContextV01",
    ):
        PersonalizedDecisionEngineV01().decide(
            legacy_context
        )


def test_decision_result_does_not_claim_agent_execution():
    context = make_context(
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_HINT
        ),
    )

    result = PersonalizedDecisionEngineV01().decide(
        context
    )

    assert "execution has not yet occurred" in (
        result.selection_reason
    )

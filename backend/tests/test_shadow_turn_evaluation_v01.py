"""
Tests for 13E-4C-3B Shadow Evaluation Integration.
"""

from dataclasses import replace

import pytest

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)
from app.services.decision.models_v01 import (
    TeachingActionV01,
)
from app.services.decision.shadow_turn_evaluation_v01 import (
    evaluate_shadow_turn_v01,
)
from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)

from test_evidence_driven_engine_v01 import (
    context as make_decision_context,
)
from test_observation_aware_shadow_policy_v01 import (
    matching_observation_context,
)


def run_shadow(
    *,
    hint_count=0,
    solution_count=0,
    request_kind=None,
    include_observation=True,
):
    decision_context = make_decision_context(
        request_kind=request_kind,
    )

    observations = matching_observation_context(
        decision_context,
        hint_count=hint_count,
        solution_count=solution_count,
        include_observation=include_observation,
    )

    evaluation = evaluate_shadow_turn_v01(
        decision_context=decision_context,
        observation_context=observations,
        decision_engine=EvidenceDrivenDecisionEngineV01(),
    )

    return decision_context, evaluation


def test_actual_decision_matches_shadow_reference():
    _, evaluation = run_shadow(hint_count=1)

    assert (
        evaluation.observation_report.existing_action
        == evaluation.actual_decision.decision.selected_action
    )

    assert (
        evaluation.observation_report.decision_id
        == evaluation.actual_decision.decision.decision_id
    )


def test_hint_evaluation_does_not_authorize_execution():
    _, evaluation = run_shadow(hint_count=1)

    report = evaluation.observation_report

    assert report.app_hint_attempt_count == 1
    assert report.action_execution_authorized is False
    assert report.mastery_eligible is False

    if report.candidate_action is not None:
        assert report.candidate_action in (
            evaluation.actual_decision.decision.allowed_actions
        )


def test_solution_evaluation_preserves_actual_decision():
    decision_context = make_decision_context()

    engine = EvidenceDrivenDecisionEngineV01()
    expected = engine.decide(decision_context)

    observations = matching_observation_context(
        decision_context,
        solution_count=1,
    )

    evaluation = evaluate_shadow_turn_v01(
        decision_context=decision_context,
        observation_context=observations,
        decision_engine=engine,
    )

    assert evaluation.actual_decision == expected
    assert evaluation.observation_report.app_solution_attempt_count == 1


def test_explicit_request_remains_authoritative():
    _, evaluation = run_shadow(
        solution_count=1,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    assert evaluation.actual_decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert evaluation.observation_report.candidate_action is None

    assert evaluation.observation_report.status == (
        "explicit_request_preserved"
    )


def test_empty_history_proposes_no_candidate():
    _, evaluation = run_shadow(
        include_observation=False,
    )

    report = evaluation.observation_report

    assert report.observed_attempt_count == 0
    assert report.candidate_action is None
    assert report.would_differ_from_existing is False


def test_no_app_help_report_does_not_prove_independence():
    _, evaluation = run_shadow()

    report = evaluation.observation_report

    assert report.no_app_report_attempt_count == 1
    assert report.verified_independence is False
    assert report.mastery_eligible is False


@pytest.mark.parametrize(
    "field",
    ("student_id", "course_id", "objective_id"),
)
def test_mismatched_observation_scope_is_rejected(field):
    decision_context = make_decision_context()

    observations = matching_observation_context(
        decision_context,
        include_observation=False,
    )

    wrong_observations = replace(
        observations,
        **{field: "wrong-scope"},
    )

    with pytest.raises(ValueError, match="scope"):
        evaluate_shadow_turn_v01(
            decision_context=decision_context,
            observation_context=wrong_observations,
            decision_engine=EvidenceDrivenDecisionEngineV01(),
        )


def test_student_state_is_not_modified():
    decision_context = make_decision_context()

    state = decision_context.decision_context.objective_state
    before = state.model_dump(mode="json")

    observations = matching_observation_context(
        decision_context,
        hint_count=1,
    )

    evaluate_shadow_turn_v01(
        decision_context=decision_context,
        observation_context=observations,
        decision_engine=EvidenceDrivenDecisionEngineV01(),
    )

    assert state.model_dump(mode="json") == before


def test_evaluation_returns_existing_decision_result_type():
    _, evaluation = run_shadow(hint_count=1)

    assert evaluation.actual_decision.decision.selected_action in (
        evaluation.actual_decision.decision.allowed_actions
    )

    assert evaluation.observation_report.history_order_verified is False
    assert evaluation.observation_report.action_execution_authorized is False


def test_wrong_engine_type_is_rejected():
    decision_context = make_decision_context()

    observations = matching_observation_context(
        decision_context,
        include_observation=False,
    )

    with pytest.raises(TypeError, match="decision_engine"):
        evaluate_shadow_turn_v01(
            decision_context=decision_context,
            observation_context=observations,
            decision_engine=object(),
        )

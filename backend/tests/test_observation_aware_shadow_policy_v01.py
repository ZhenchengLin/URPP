"""
Focused tests for 13E-4C-3A Shadow Policy.

These tests reuse the already-tested Decision Engine and
Observation factories without modifying their behavior.
"""

from dataclasses import replace

import pytest

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)
from app.services.decision.models_v01 import (
    TeachingActionV01,
)
from app.services.decision.observation_aware_shadow_policy_v01 import (
    evaluate_observation_shadow_v01,
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
from test_teaching_observation_context_v01 import (
    observation as make_observation,
)


def matching_observation_context(
    decision_context,
    *,
    hint_count=0,
    solution_count=0,
    include_observation=True,
):
    state = decision_context.decision_context.objective_state

    observations = ()

    if include_observation:
        item = replace(
            make_observation(
                hint_count=hint_count,
                solution_count=solution_count,
            ),
            student_id=state.student_id,
            course_id=state.course_id,
            objective_id=state.objective_id,
        )
        observations = (item,)

    return TeachingObservationContextV01(
        student_id=state.student_id,
        course_id=state.course_id,
        objective_id=state.objective_id,
        observations=observations,
    )


def evaluate(
    *,
    hint_count=0,
    solution_count=0,
    include_observation=True,
    request_kind=None,
):
    decision_context = make_decision_context(
        request_kind=request_kind,
    )

    engine = EvidenceDrivenDecisionEngineV01()
    decision_result = engine.decide(decision_context)

    observation_context = matching_observation_context(
        decision_context,
        hint_count=hint_count,
        solution_count=solution_count,
        include_observation=include_observation,
    )

    report = evaluate_observation_shadow_v01(
        decision_context=decision_context,
        decision_result=decision_result,
        observation_context=observation_context,
    )

    return (
        decision_context,
        decision_result,
        observation_context,
        report,
    )


def test_empty_history_does_not_propose_action():
    _, decision, _, report = evaluate(
        include_observation=False,
    )

    assert report.existing_action == (
        decision.decision.selected_action
    )
    assert report.candidate_action is None
    assert report.status == "no_app_help_candidate"
    assert report.observed_attempt_count == 0
    assert report.would_differ_from_existing is False


def test_no_app_report_does_not_prove_independence():
    _, _, _, report = evaluate()

    assert report.no_app_report_attempt_count == 1
    assert report.candidate_action is None
    assert report.verified_independence is False
    assert report.mastery_eligible is False


def test_reported_hint_proposes_only_review_candidate():
    _, decision, _, report = evaluate(
        hint_count=1,
    )

    allowed = decision.decision.allowed_actions
    proposed = TeachingActionV01.DIAGNOSTIC_ASSESSMENT

    if proposed in allowed:
        assert report.candidate_action == proposed
    else:
        assert report.candidate_action is None
        assert report.status == "candidate_not_allowed"

    assert report.app_hint_attempt_count == 1
    assert report.action_execution_authorized is False


def test_reported_solution_proposes_only_review_candidate():
    _, decision, _, report = evaluate(
        solution_count=1,
    )

    allowed = decision.decision.allowed_actions
    proposed = TeachingActionV01.SELF_EXPLANATION

    if proposed in allowed:
        assert report.candidate_action == proposed
    else:
        assert report.candidate_action is None
        assert report.status == "candidate_not_allowed"

    assert report.app_solution_attempt_count == 1
    assert report.mastery_eligible is False


def test_solution_candidate_has_priority_over_hint_candidate():
    _, decision, _, report = evaluate(
        hint_count=1,
        solution_count=1,
    )

    proposed = TeachingActionV01.SELF_EXPLANATION

    if proposed in decision.decision.allowed_actions:
        assert report.candidate_action == proposed
    else:
        assert report.candidate_action is None

    assert report.app_hint_attempt_count == 1
    assert report.app_solution_attempt_count == 1


def test_explicit_student_request_is_preserved():
    _, decision, _, report = evaluate(
        solution_count=1,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    assert decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert report.existing_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert report.candidate_action is None
    assert report.status == "explicit_request_preserved"
    assert report.would_differ_from_existing is False


def test_shadow_does_not_modify_state_or_original_decision():
    decision_context = make_decision_context()
    decision = EvidenceDrivenDecisionEngineV01().decide(
        decision_context
    )

    observations = matching_observation_context(
        decision_context,
        hint_count=1,
    )

    state = decision_context.decision_context.objective_state

    before_state = state.model_dump(mode="json")
    before_decision = decision.model_dump(mode="json")

    evaluate_observation_shadow_v01(
        decision_context=decision_context,
        decision_result=decision,
        observation_context=observations,
    )

    assert state.model_dump(mode="json") == before_state
    assert decision.model_dump(mode="json") == before_decision


@pytest.mark.parametrize(
    "field",
    ["student_id", "course_id", "objective_id"],
)
def test_cross_scope_observations_are_rejected(field):
    decision_context = make_decision_context()
    decision = EvidenceDrivenDecisionEngineV01().decide(
        decision_context
    )

    observations = matching_observation_context(
        decision_context,
        include_observation=False,
    )

    mismatched = replace(
        observations,
        **{field: "wrong-scope"},
    )

    with pytest.raises(ValueError, match="scope"):
        evaluate_observation_shadow_v01(
            decision_context=decision_context,
            decision_result=decision,
            observation_context=mismatched,
        )


def test_decision_id_mismatch_is_rejected():
    decision_context = make_decision_context()
    decision = EvidenceDrivenDecisionEngineV01().decide(
        decision_context
    )

    observations = matching_observation_context(
        decision_context,
        include_observation=False,
    )

    changed_decision = decision.model_copy(
        update={
            "decision": decision.decision.model_copy(
                update={"decision_id": "different-decision"}
            )
        }
    )

    with pytest.raises(ValueError, match="decision context"):
        evaluate_observation_shadow_v01(
            decision_context=decision_context,
            decision_result=changed_decision,
            observation_context=observations,
        )


def test_shadow_does_not_claim_verified_history_order():
    _, _, _, report = evaluate(
        hint_count=1,
    )

    assert report.history_order_verified is False
    assert report.action_execution_authorized is False


def test_observation_context_is_required():
    decision_context = make_decision_context()
    decision = EvidenceDrivenDecisionEngineV01().decide(
        decision_context
    )

    with pytest.raises(TypeError, match="observation_context"):
        evaluate_observation_shadow_v01(
            decision_context=decision_context,
            decision_result=decision,
            observation_context=None,
        )

"""
URPP 13E-4D-2: Opt-in teaching integration.

The existing teaching interface remains compatible.
The observed interface runs the authoritative decision
and one teaching agent exactly once.
"""

from dataclasses import replace

import pytest

import app.services.decision.post_turn_shadow_observer_v01 as observer_module

from app.services.decision.models_v01 import (
    TeachingActionV01,
)
from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)
from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
)

from test_evidence_driven_engine_v01 import (
    context as make_context,
)
from test_observation_aware_shadow_policy_v01 import (
    matching_observation_context,
)
from test_post_turn_shadow_observer_v01 import (
    CountingAgent,
    CountingDecisionEngine,
)


def setup_turn(*, request_kind=None):
    original_context = make_context(
        request_kind=request_kind,
    )

    engine = CountingDecisionEngine()
    professor = CountingAgent()
    assessment = CountingAgent()

    orchestrator = PersonalizedTeachingTurnOrchestratorV01(
        decision_engine=engine,
        professor_agent=professor,
        assessment_agent=assessment,
    )

    state = original_context.decision_context.objective_state

    return (
        original_context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    )


def invoke_observed(
    original_context,
    state,
    orchestrator,
    observations,
):
    decision = original_context.decision_context

    return orchestrator.run_turn_observed(
        state,
        decision_id=decision.decision_id,
        requested_at=decision.requested_at,
        student_request=original_context.student_request,
        observation_context=observations,
    )


def test_original_run_turn_remains_compatible():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    decision = context.decision_context

    result = orchestrator.run_turn(
        state,
        decision_id=decision.decision_id,
        requested_at=decision.requested_at,
    )

    assert result.content == "Completed teaching content."
    assert result.decision.decision.selected_action in (
        result.decision.decision.allowed_actions
    )

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_observed_turn_uses_original_decision_context(
    monkeypatch,
):
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    observations = matching_observation_context(
        context,
        hint_count=1,
    )

    captured = {}

    original_observer = (
        observer_module.observe_completed_turn_v01
    )

    def capture_observer(**kwargs):
        captured.update(kwargs)
        return original_observer(**kwargs)

    monkeypatch.setattr(
        observer_module,
        "observe_completed_turn_v01",
        capture_observer,
    )

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        observations,
    )

    assert outcome.status == "evaluated"

    # The observer receives the exact object passed to
    # the Decision Engine, not a reconstructed Context.
    assert captured["decision_context"] is engine.actual_context

    assert captured["completed_turn"] is outcome.completed_turn

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_observed_turn_with_no_context_is_unavailable():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        None,
    )

    assert outcome.status == "unavailable"
    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_cross_scope_observation_cannot_replace_teaching():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    observations = matching_observation_context(
        context,
        include_observation=False,
    )

    wrong = replace(
        observations,
        objective_id="other-objective",
    )

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        wrong,
    )

    assert outcome.status == "failed"
    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_shadow_exception_does_not_replace_actual_turn(
    monkeypatch,
):
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    observations = matching_observation_context(
        context,
        solution_count=1,
    )

    def broken_shadow(**kwargs):
        raise RuntimeError("private shadow failure")

    monkeypatch.setattr(
        observer_module,
        "evaluate_observation_shadow_v01",
        broken_shadow,
    )

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        observations,
    )

    assert outcome.status == "failed"
    assert outcome.report is None
    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_explicit_request_preserves_actual_action():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn(
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    observations = matching_observation_context(
        context,
        solution_count=1,
    )

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        observations,
    )

    assert outcome.completed_turn.decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert outcome.report is not None
    assert outcome.report.candidate_action is None

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_invalid_observation_type_rejected_before_execution():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    with pytest.raises(
        TypeError,
        match="observation_context",
    ):
        invoke_observed(
            context,
            state,
            orchestrator,
            object(),
        )

    assert engine.calls == 0
    assert professor.calls + assessment.calls == 0


def test_authoritative_agent_failure_still_propagates():
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    def broken_produce(**kwargs):
        raise RuntimeError("authoritative agent failure")

    professor.produce = broken_produce
    assessment.produce = broken_produce

    with pytest.raises(
        RuntimeError,
        match="authoritative agent failure",
    ):
        invoke_observed(
            context,
            state,
            orchestrator,
            None,
        )

    assert engine.calls == 1



def test_observer_itself_can_fail_without_losing_completed_turn(
    monkeypatch,
):
    (
        context,
        state,
        orchestrator,
        engine,
        professor,
        assessment,
    ) = setup_turn()

    observations = matching_observation_context(
        context,
        hint_count=1,
    )

    def broken_observer(**kwargs):
        raise RuntimeError(
            "internal observer failure with private details"
        )

    monkeypatch.setattr(
        observer_module,
        "observe_completed_turn_v01",
        broken_observer,
    )

    outcome = invoke_observed(
        context,
        state,
        orchestrator,
        observations,
    )

    assert outcome.status == "failed"
    assert outcome.report is None

    assert outcome.failure_code == (
        "shadow_evaluation_failed"
    )

    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert "private details" not in repr(outcome)

    # The authoritative flow is not repeated.
    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1

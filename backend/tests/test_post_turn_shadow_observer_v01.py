"""
13E-4D-1 tests.

Verify that post-turn observation cannot replace an
already completed teaching result or re-run the engine.
"""

from dataclasses import replace

import pytest

import app.services.decision.post_turn_shadow_observer_v01 as observer_module

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)
from app.services.decision.models_v01 import (
    TeachingActionV01,
)
from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)
from app.services.decision.post_turn_shadow_observer_v01 import (
    observe_completed_turn_v01,
)
from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
)

from test_evidence_driven_engine_v01 import (
    context as make_decision_context,
)
from test_observation_aware_shadow_policy_v01 import (
    matching_observation_context,
)


class CountingDecisionEngine(
    EvidenceDrivenDecisionEngineV01
):
    """
    Capture the actual context used by the Orchestrator.

    This avoids reconstructing a potentially stale context
    after the teaching turn has completed.
    """

    def __init__(self):
        super().__init__()
        self.calls = 0
        self.actual_context = None

    def decide(self, context):
        self.calls += 1
        self.actual_context = context
        return super().decide(context)


class CountingAgent:
    """Minimal teaching-agent test double."""

    def __init__(self):
        self.calls = 0

    def produce(self, *, context, decision):
        self.calls += 1
        return "Completed teaching content."


def completed_turn_with_observations(
    *,
    hint_count=0,
    solution_count=0,
    request_kind=None,
):
    initial_context = make_decision_context(
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

    original = initial_context.decision_context

    completed_turn = orchestrator.run_turn(
        original.objective_state,
        decision_id=original.decision_id,
        requested_at=original.requested_at,
        student_request=initial_context.student_request,
    )

    # Use the exact context received by the real Decision
    # Engine, rather than creating a second context later.
    actual_context = engine.actual_context

    assert actual_context is not None
    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1

    observations = matching_observation_context(
        actual_context,
        hint_count=hint_count,
        solution_count=solution_count,
    )

    return (
        actual_context,
        completed_turn,
        observations,
        engine,
        professor,
        assessment,
    )


def test_success_preserves_original_completed_turn():
    (
        context,
        completed,
        observations,
        engine,
        professor,
        assessment,
    ) = completed_turn_with_observations(
        hint_count=1,
    )

    original_state = (
        context.decision_context.objective_state.model_dump(
            mode="json"
        )
    )

    original_decision = completed.decision.model_dump(
        mode="json"
    )

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=observations,
    )

    assert outcome.status == "evaluated"
    assert outcome.completed_turn is completed
    assert outcome.report is not None

    assert outcome.report.existing_action == (
        completed.decision.decision.selected_action
    )

    assert outcome.report.action_execution_authorized is False
    assert outcome.report.mastery_eligible is False

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1

    assert (
        context.decision_context.objective_state.model_dump(
            mode="json"
        )
        == original_state
    )

    assert completed.decision.model_dump(
        mode="json"
    ) == original_decision


def test_missing_observations_preserve_completed_turn():
    (
        context,
        completed,
        _,
        engine,
        professor,
        assessment,
    ) = completed_turn_with_observations()

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=None,
    )

    assert outcome.status == "unavailable"
    assert outcome.report is None
    assert outcome.failure_code is None

    assert outcome.completed_turn is completed

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


@pytest.mark.parametrize(
    "field",
    ("student_id", "course_id", "objective_id"),
)
def test_cross_scope_observation_failure_is_isolated(field):
    (
        context,
        completed,
        _,
        engine,
        professor,
        assessment,
    ) = completed_turn_with_observations()

    # An empty context allows construction of a mismatched
    # scope without violating its own entry-level checks.
    empty_observations = matching_observation_context(
        context,
        include_observation=False,
    )

    mismatched = replace(
        empty_observations,
        **{field: "other-scope"},
    )

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=mismatched,
    )

    assert outcome.status == "failed"
    assert outcome.report is None

    assert outcome.failure_code == "shadow_evaluation_failed"

    assert outcome.completed_turn is completed

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_shadow_exception_is_isolated(
    monkeypatch,
):
    (
        context,
        completed,
        observations,
        engine,
        professor,
        assessment,
    ) = completed_turn_with_observations(
        hint_count=1,
    )

    def fail_shadow(**kwargs):
        raise RuntimeError(
            "internal shadow failure with private details"
        )

    monkeypatch.setattr(
        observer_module,
        "evaluate_observation_shadow_v01",
        fail_shadow,
    )

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=observations,
    )

    assert outcome.status == "failed"
    assert outcome.report is None
    assert outcome.failure_code == "shadow_evaluation_failed"

    assert outcome.completed_turn is completed
    assert completed.content == "Completed teaching content."

    assert "private details" not in repr(outcome)

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_explicit_request_still_controls_actual_action():
    (
        context,
        completed,
        observations,
        engine,
        professor,
        assessment,
    ) = completed_turn_with_observations(
        solution_count=1,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=observations,
    )

    assert completed.decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert outcome.status == "evaluated"
    assert outcome.completed_turn is completed

    assert outcome.report.candidate_action is None
    assert outcome.report.status == "explicit_request_preserved"

    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_candidate_cannot_replace_actual_action():
    (
        context,
        completed,
        observations,
        _,
        _,
        _,
    ) = completed_turn_with_observations(
        solution_count=1,
    )

    original_action = completed.decision.decision.selected_action

    outcome = observe_completed_turn_v01(
        decision_context=context,
        completed_turn=completed,
        observation_context=observations,
    )

    assert outcome.status == "evaluated"
    assert outcome.completed_turn is completed

    assert (
        outcome.completed_turn.decision.decision.selected_action
        == original_action
    )

    assert outcome.report.action_execution_authorized is False


def test_invalid_completed_turn_is_not_hidden():
    (
        context,
        _,
        observations,
        _,
        _,
        _,
    ) = completed_turn_with_observations()

    with pytest.raises(
        TypeError,
        match="completed_turn",
    ):
        observe_completed_turn_v01(
            decision_context=context,
            completed_turn=object(),
            observation_context=observations,
        )


def test_invalid_observation_input_is_not_hidden():
    (
        context,
        completed,
        _,
        _,
        _,
        _,
    ) = completed_turn_with_observations()

    with pytest.raises(
        TypeError,
        match="observation_context",
    ):
        observe_completed_turn_v01(
            decision_context=context,
            completed_turn=completed,
            observation_context=object(),
        )

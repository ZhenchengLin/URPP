"""
URPP Design 01D — Teaching Turn Orchestrator tests.

All Agents in this module are test doubles.
No real LLM or external decision model is invoked.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pydantic import ValidationError

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)

from app.services.decision.models_v01 import (
    DecisionProposalV01,
    TeachingActionV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    DecisionContextBuilderV01,
    TeachingTurnOrchestratorV01,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


def make_state():
    return estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )


class RecordingAgent:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def produce(self, *, context, decision):
        self.calls.append(
            {
                "decision_id": context.decision_id,
                "action": decision.selected_action,
            }
        )

        return self.response


class ConceptualReviewController:
    def propose(self, context, allowed_actions):
        return DecisionProposalV01(
            selected_action=TeachingActionV01.CONCEPTUAL_REVIEW,
            model_version="conceptual-review-test-controller",
            rationale="Exercise the Professor Agent route.",
        )


class InvalidController:
    def propose(self, context, allowed_actions):
        return DecisionProposalV01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
            model_version="invalid-test-controller",
            rationale="Exercise the policy fallback.",
        )


def make_orchestrator(
    *,
    controller=None,
    professor_response="Here is a conceptual explanation.",
    assessment_response="Here is a diagnostic question.",
):
    professor = RecordingAgent(professor_response)
    assessment = RecordingAgent(assessment_response)

    engine = DecisionEngineV01(
        controller or RuleBasedControllerV01()
    )

    orchestrator = TeachingTurnOrchestratorV01(
        decision_engine=engine,
        professor_agent=professor,
        assessment_agent=assessment,
    )

    return orchestrator, professor, assessment


def test_context_builder_preserves_student_state():
    state = make_state()

    context = DecisionContextBuilderV01().build(
        state,
        decision_id="decision-001",
        requested_at=NOW,
    )

    assert context.objective_state is state
    assert context.decision_id == "decision-001"


def test_unknown_state_routes_diagnostic_to_assessment_agent():
    orchestrator, professor, assessment = make_orchestrator()

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-001",
        requested_at=NOW,
    )

    assert result.agent_kind == "assessment"

    assert (
        result.decision.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert result.content == "Here is a diagnostic question."

    assert professor.calls == []
    assert len(assessment.calls) == 1


def test_conceptual_review_routes_to_professor_agent():
    orchestrator, professor, assessment = make_orchestrator(
        controller=ConceptualReviewController(),
    )

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-002",
        requested_at=NOW,
    )

    assert result.agent_kind == "professor"

    assert (
        result.decision.selected_action
        == TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert len(professor.calls) == 1
    assert assessment.calls == []


def test_disallowed_controller_uses_policy_fallback():
    orchestrator, professor, assessment = make_orchestrator(
        controller=InvalidController(),
    )

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-003",
        requested_at=NOW,
    )

    assert result.decision.fallback_used is True

    assert (
        result.decision.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert professor.calls == []
    assert len(assessment.calls) == 1


def test_agent_cannot_return_empty_content():
    orchestrator, _, _ = make_orchestrator(
        assessment_response="   ",
    )

    with pytest.raises(
        ValidationError,
        match="cannot be empty",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-004",
            requested_at=NOW,
        )


def test_agent_cannot_return_unstructured_object():
    orchestrator, _, _ = make_orchestrator(
        assessment_response={
            "unexpected": "object"
        },
    )

    with pytest.raises(
        TypeError,
        match="must return a string",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-005",
            requested_at=NOW,
        )


def test_teaching_turn_does_not_update_student_state():
    state = make_state()

    before = state.model_dump(mode="json")

    orchestrator, _, _ = make_orchestrator()

    orchestrator.run_turn(
        state,
        decision_id="decision-006",
        requested_at=NOW,
    )

    assert state.model_dump(mode="json") == before


def test_context_builder_rejects_blank_decision_id():
    with pytest.raises(
        ValueError,
        match="non-empty",
    ):
        DecisionContextBuilderV01().build(
            make_state(),
            decision_id="   ",
            requested_at=NOW,
        )


def test_context_builder_rejects_stale_decision_timestamp():
    with pytest.raises(
        ValidationError,
        match="precede",
    ):
        DecisionContextBuilderV01().build(
            make_state(),
            decision_id="decision-007",
            requested_at=NOW - timedelta(seconds=1),
        )


class FailingAssessmentAgent:
    def __init__(self):
        self.calls = 0

    def produce(self, *, context, decision):
        self.calls += 1
        raise RuntimeError("Assessment generation failed.")


def test_agent_failure_is_not_silently_replaced():
    professor = RecordingAgent("A conceptual explanation.")
    assessment = FailingAssessmentAgent()

    orchestrator = TeachingTurnOrchestratorV01(
        decision_engine=DecisionEngineV01(
            RuleBasedControllerV01()
        ),
        professor_agent=professor,
        assessment_agent=assessment,
    )

    with pytest.raises(
        RuntimeError,
        match="Assessment generation failed",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-008",
            requested_at=NOW,
        )

    assert assessment.calls == 1
    assert professor.calls == []

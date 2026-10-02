"""
URPP Implementation 13C-1 tests.

These tests use recording Agent doubles. They do not
represent an integrated LLM teaching system.
"""

from datetime import datetime, timezone

import pytest

from app.domain.learning.models import ObjectiveStateLabel

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
    PersonalizedDecisionEngineV01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def make_state(
    label=ObjectiveStateLabel.UNKNOWN,
):
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )

    if label == ObjectiveStateLabel.UNKNOWN:
        return state

    # Synthetic routing fixture only. Not persisted evidence.
    return state.model_copy(
        update={"state": label}
    )


def make_request(kind):
    return StudentLearningRequestV01(
        objective_id="objective-001",
        request_kind=kind,
        requested_at=NOW,
    )


class RecordingAgent:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def produce(self, *, context, decision):
        self.calls.append(
            (context, decision)
        )

        return self.content


def make_orchestrator(
    professor=None,
    assessment=None,
):
    professor = (
        professor
        if professor is not None
        else RecordingAgent("Professor content.")
    )

    assessment = (
        assessment
        if assessment is not None
        else RecordingAgent("Assessment content.")
    )

    orchestrator = (
        PersonalizedTeachingTurnOrchestratorV01(
            decision_engine=PersonalizedDecisionEngineV01(),
            professor_agent=professor,
            assessment_agent=assessment,
        )
    )

    return orchestrator, professor, assessment


def test_no_request_preserves_baseline_assessment_route():
    orchestrator, professor, assessment = make_orchestrator()

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-001",
        requested_at=NOW,
    )

    assert (
        result.decision.decision.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert (
        result.decision.selection_source
        == DecisionSelectionSourceV01.BASELINE
    )

    assert result.agent_kind == "assessment"

    assert len(assessment.calls) == 1
    assert len(professor.calls) == 0

    received_context, received_decision = assessment.calls[0]

    assert received_context.student_request is None
    assert received_decision == result.decision


def test_strong_student_request_reaches_professor_agent():
    orchestrator, professor, assessment = make_orchestrator()

    state = make_state(
        ObjectiveStateLabel.STRONG
    )

    before = state.model_dump(mode="json")

    result = orchestrator.run_turn(
        state,
        decision_id="decision-explanation",
        requested_at=NOW,
        student_request=make_request(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    assert result.agent_kind == "professor"

    assert (
        result.decision.decision.selected_action
        == TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert (
        result.decision.request_expanded_allowed_actions
        is True
    )

    assert result.decision.selected_for_request is True

    assert len(professor.calls) == 1
    assert len(assessment.calls) == 0

    received_context, received_decision = professor.calls[0]

    assert (
        received_context.student_request.request_kind
        == StudentLearningRequestKindV01.REQUEST_EXPLANATION
    )

    assert received_decision == result.decision

    assert state.model_dump(mode="json") == before


def test_request_to_try_independently_reaches_assessment_agent():
    orchestrator, professor, assessment = make_orchestrator()

    result = orchestrator.run_turn(
        make_state(
            ObjectiveStateLabel.DEVELOPING
        ),
        decision_id="decision-practice",
        requested_at=NOW,
        student_request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    assert result.agent_kind == "assessment"

    assert (
        result.decision.decision.selected_action
        == TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert len(assessment.calls) == 1
    assert len(professor.calls) == 0

    received_context, _ = assessment.calls[0]

    assert (
        received_context.student_request.request_kind
        == StudentLearningRequestKindV01.TRY_INDEPENDENTLY
    )


@pytest.mark.parametrize(
    ("request_kind", "expected_action", "expected_agent"),
    [
        (
            StudentLearningRequestKindV01.REQUEST_HINT,
            TeachingActionV01.CONCEPTUAL_HINT,
            "professor",
        ),
        (
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC,
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
            "assessment",
        ),
        (
            StudentLearningRequestKindV01.REQUEST_SELF_EXPLANATION,
            TeachingActionV01.SELF_EXPLANATION,
            "professor",
        ),
        (
            StudentLearningRequestKindV01.REQUEST_TRANSFER,
            TeachingActionV01.TRANSFER_ASSESSMENT,
            "assessment",
        ),
    ],
)
def test_supported_requests_reach_correct_agent(
    request_kind,
    expected_action,
    expected_agent,
):
    orchestrator, professor, assessment = make_orchestrator()

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-request",
        requested_at=NOW,
        student_request=make_request(
            request_kind
        ),
    )

    assert result.decision.decision.selected_action == expected_action

    assert result.agent_kind == expected_agent

    selected_agent = (
        professor
        if expected_agent == "professor"
        else assessment
    )

    assert len(selected_agent.calls) == 1

    received_context, _ = selected_agent.calls[0]

    assert received_context.student_request.request_kind == request_kind


def test_unmatched_objective_rejected_before_agent_call():
    orchestrator, professor, assessment = make_orchestrator()

    mismatched_request = StudentLearningRequestV01(
        objective_id="other-objective",
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=NOW,
    )

    with pytest.raises(
        ValueError,
        match="current Objective",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-mismatch",
            requested_at=NOW,
            student_request=mismatched_request,
        )

    assert not professor.calls
    assert not assessment.calls


@pytest.mark.parametrize(
    "invalid_content",
    [
        "",
        "   ",
        {"text": "Unstructured content."},
    ],
)
def test_invalid_agent_output_is_rejected(
    invalid_content,
):
    professor = RecordingAgent(
        invalid_content
    )

    orchestrator, professor, assessment = make_orchestrator(
        professor=professor,
    )

    expected_error = (
        TypeError
        if not isinstance(invalid_content, str)
        else ValueError
    )

    with pytest.raises(expected_error):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-invalid-output",
            requested_at=NOW,
            student_request=make_request(
                StudentLearningRequestKindV01.REQUEST_EXPLANATION
            ),
        )

    assert len(professor.calls) == 1
    assert not assessment.calls


def test_agent_failure_is_not_silently_replaced():
    class FailingAssessmentAgent:
        def produce(self, *, context, decision):
            raise RuntimeError(
                "Assessment Agent unavailable."
            )

    professor = RecordingAgent(
        "Professor content."
    )

    orchestrator, professor, _ = make_orchestrator(
        professor=professor,
        assessment=FailingAssessmentAgent(),
    )

    with pytest.raises(
        RuntimeError,
        match="Assessment Agent unavailable",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-agent-failure",
            requested_at=NOW,
        )

    assert not professor.calls


def test_agent_cannot_silently_modify_student_state():
    class MutatingProfessorAgent:
        def produce(self, *, context, decision):
            state = context.decision_context.objective_state

            # Deliberately bypass frozen-model protection to
            # test the orchestrator's mutation-detection check.
            object.__setattr__(
                state,
                "state",
                ObjectiveStateLabel.EMERGING,
            )

            return "Invalidly mutated content."

    orchestrator, _, assessment = make_orchestrator(
        professor=MutatingProfessorAgent(),
    )

    with pytest.raises(
        ValueError,
        match="modified Student State",
    ):
        orchestrator.run_turn(
            make_state(
                ObjectiveStateLabel.STRONG
            ),
            decision_id="decision-mutating-agent",
            requested_at=NOW,
            student_request=make_request(
                StudentLearningRequestKindV01.REQUEST_EXPLANATION
            ),
        )

    assert not assessment.calls


def test_turn_result_content_is_not_assessment_evidence():
    orchestrator, professor, assessment = make_orchestrator()

    result = orchestrator.run_turn(
        make_state(),
        decision_id="decision-content",
        requested_at=NOW,
    )

    assert result.content == "Assessment content."
    assert result.agent_kind == "assessment"

    assert not hasattr(
        result,
        "evidence_id",
    )

    assert not hasattr(
        result,
        "assignment_id",
    )

    assert not professor.calls
    assert len(assessment.calls) == 1

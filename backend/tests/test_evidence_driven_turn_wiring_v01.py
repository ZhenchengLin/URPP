"""
URPP Implementation 13E-2A.

Tests verify the actual Personalized Orchestrator and
Numeric Session Adapter composition.

Synthetic states test routing only. They are not
real student-performance evidence.

Persisted assessment-to-state feedback is deferred
to the SQLite end-to-end integration stage.
"""

from datetime import datetime, timezone

import pytest

from app.domain.learning.models import (
    ObjectiveStateLabel,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)

from app.services.decision.evidence_driven_turn_wiring_v01 import (
    create_evidence_driven_personalized_turn_v01,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
)

from app.services.decision.personalized_numeric_session_adapter_v01 import (
    PersonalizedNumericSessionTurnAdapterV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


class RecordingAgent:
    def __init__(self):
        self.calls = []

    def produce(
        self,
        *,
        context,
        decision,
    ):
        self.calls.append(
            (context, decision)
        )

        return "Prepared teaching content."


def make_state():
    return estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )


def make_request(kind):
    return StudentLearningRequestV01(
        objective_id="objective-001",
        request_kind=kind,
        requested_at=NOW,
    )


def make_stack():
    professor = RecordingAgent()
    assessment = RecordingAgent()

    orchestrator = create_evidence_driven_personalized_turn_v01(
        professor_agent=professor,
        assessment_agent=assessment,
    )

    return orchestrator, professor, assessment


def test_real_empty_evidence_state_routes_to_diagnostic_agent():
    orchestrator, professor, assessment = make_stack()

    state = make_state()
    before = state.model_dump(mode="json")

    turn = orchestrator.run_turn(
        state,
        decision_id="decision-001",
        requested_at=NOW,
    )

    assert turn.decision.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert turn.decision.selection_source == (
        DecisionSelectionSourceV01.EVIDENCE_DRIVEN
    )

    assert turn.agent_kind == "assessment"

    assert len(assessment.calls) == 1
    assert professor.calls == []

    assert state.model_dump(mode="json") == before


def test_synthetic_early_state_routes_conceptual_hint_to_professor():
    orchestrator, professor, assessment = make_stack()

    state = make_state().model_copy(
        update={
            "state": ObjectiveStateLabel.EMERGING,
            "included_evidence_ids": ["synthetic-evidence-001"],
            "distinct_assessment_count": 1,
        }
    )

    turn = orchestrator.run_turn(
        state,
        decision_id="decision-002",
        requested_at=NOW,
    )

    assert turn.decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_HINT
    )

    assert turn.agent_kind == "professor"

    assert len(professor.calls) == 1
    assert assessment.calls == []


def test_explicit_explanation_request_preserves_choice():
    orchestrator, professor, assessment = make_stack()

    turn = orchestrator.run_turn(
        make_state(),
        decision_id="decision-003",
        requested_at=NOW,
        student_request=make_request(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    assert turn.decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    assert turn.decision.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )

    assert turn.agent_kind == "professor"

    assert len(professor.calls) == 1
    assert assessment.calls == []


def test_explicit_independent_request_uses_assessment_agent():
    orchestrator, professor, assessment = make_stack()

    turn = orchestrator.run_turn(
        make_state(),
        decision_id="decision-004",
        requested_at=NOW,
        student_request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    assert turn.decision.decision.selected_action == (
        TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert turn.decision.selection_source == (
        DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    )

    assert turn.agent_kind == "assessment"

    assert len(assessment.calls) == 1
    assert professor.calls == []


def test_explicit_transfer_is_blocked_before_assessment_agent():
    orchestrator, professor, assessment = make_stack()

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        orchestrator.run_turn(
            make_state(),
            decision_id="decision-005",
            requested_at=NOW,
            student_request=make_request(
                StudentLearningRequestKindV01.REQUEST_TRANSFER
            ),
        )

    assert assessment.calls == []
    assert professor.calls == []


def test_no_request_adapter_uses_evidence_driven_decision_once():
    orchestrator, professor, assessment = make_stack()

    adapter = PersonalizedNumericSessionTurnAdapterV01(
        personalized_turn_orchestrator=orchestrator,
    )

    turn = adapter.run_turn(
        make_state(),
        decision_id="decision-006",
        requested_at=NOW,
    )

    assert turn.decision.selected_action == (
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert turn.agent_kind == "assessment"

    assert len(assessment.calls) == 1
    assert professor.calls == []


def test_adapter_does_not_misrepresent_professor_action_as_assessment():
    orchestrator, professor, assessment = make_stack()

    adapter = PersonalizedNumericSessionTurnAdapterV01(
        personalized_turn_orchestrator=orchestrator,
    )

    state = make_state().model_copy(
        update={
            "state": ObjectiveStateLabel.EMERGING,
            "included_evidence_ids": ["synthetic-evidence-001"],
            "distinct_assessment_count": 1,
        }
    )

    with pytest.raises(
        ValueError,
        match="did not select an assessment action",
    ):
        adapter.run_turn(
            state,
            decision_id="decision-007",
            requested_at=NOW,
        )

    assert len(professor.calls) == 1
    assert assessment.calls == []

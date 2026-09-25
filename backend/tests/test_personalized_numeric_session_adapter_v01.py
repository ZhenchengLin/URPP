"""
URPP Implementation 13C-2A.

Tests for the personalized-to-recoverable session adapter.

These are decision and interface tests. Persistent SQLite
integration is a separate 13C-2B verification step.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.learning.models import (
    ObjectiveStateLabel,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
)

from app.services.decision.personalized_numeric_session_adapter_v01 import (
    PersonalizedNumericSessionTurnAdapterV01,
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


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
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

    # Synthetic decision-routing fixture only.
    return state.model_copy(
        update={"state": label}
    )


def make_request(
    kind,
    *,
    objective_id="objective-001",
    requested_at=NOW,
):
    return StudentLearningRequestV01(
        objective_id=objective_id,
        request_kind=kind,
        requested_at=requested_at,
    )


def make_adapter(request=None):
    professor = RecordingAgent(
        "Professor teaching content."
    )

    assessment = RecordingAgent(
        "Assessment Agent content."
    )

    orchestrator = (
        PersonalizedTeachingTurnOrchestratorV01(
            decision_engine=PersonalizedDecisionEngineV01(),
            professor_agent=professor,
            assessment_agent=assessment,
        )
    )

    adapter = PersonalizedNumericSessionTurnAdapterV01(
        personalized_turn_orchestrator=orchestrator,
        student_request=request,
    )

    return adapter, professor, assessment


def test_independent_request_reaches_assessment_agent():
    request = make_request(
        StudentLearningRequestKindV01.TRY_INDEPENDENTLY
    )

    adapter, professor, assessment = make_adapter(
        request
    )

    result = adapter.run_turn(
        make_state(
            ObjectiveStateLabel.DEVELOPING
        ),
        decision_id="decision-001",
        requested_at=NOW,
    )

    assert (
        result.decision.selected_action
        == TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert result.agent_kind == "assessment"

    assert len(assessment.calls) == 1
    assert not professor.calls

    received_context, _ = assessment.calls[0]

    assert received_context.student_request == request


def test_transfer_request_does_not_claim_transfer_success():
    request = make_request(
        StudentLearningRequestKindV01.REQUEST_TRANSFER
    )

    state = make_state()

    before = state.model_dump(
        mode="json"
    )

    adapter, professor, assessment = make_adapter(
        request
    )

    result = adapter.run_turn(
        state,
        decision_id="decision-transfer",
        requested_at=NOW,
    )

    assert (
        result.decision.selected_action
        == TeachingActionV01.TRANSFER_ASSESSMENT
    )

    assert state.model_dump(mode="json") == before

    assert state.transfer_success_count == 0

    assert len(assessment.calls) == 1
    assert not professor.calls


def test_no_request_uses_existing_baseline_decision():
    adapter, professor, assessment = make_adapter()

    result = adapter.run_turn(
        make_state(),
        decision_id="decision-baseline",
        requested_at=NOW,
    )

    assert (
        result.decision.selected_action
        == TeachingActionV01.DIAGNOSTIC_ASSESSMENT
    )

    assert len(assessment.calls) == 1
    assert not professor.calls


def test_explanation_request_cannot_become_numeric_assignment():
    request = make_request(
        StudentLearningRequestKindV01.REQUEST_EXPLANATION
    )

    with pytest.raises(
        ValueError,
        match="assessment-related student request",
    ):
        make_adapter(request)


def test_hint_request_cannot_become_numeric_assignment():
    request = make_request(
        StudentLearningRequestKindV01.REQUEST_HINT
    )

    with pytest.raises(
        ValueError,
        match="assessment-related student request",
    ):
        make_adapter(request)


def test_mismatched_objective_is_rejected_before_agent_call():
    request = make_request(
        StudentLearningRequestKindV01.TRY_INDEPENDENTLY,
        objective_id="other-objective",
    )

    adapter, professor, assessment = make_adapter(
        request
    )

    with pytest.raises(
        ValueError,
        match="current Objective",
    ):
        adapter.run_turn(
            make_state(),
            decision_id="decision-mismatch",
            requested_at=NOW,
        )

    assert not professor.calls
    assert not assessment.calls


def test_request_timestamp_must_match_decision():
    request = make_request(
        StudentLearningRequestKindV01.TRY_INDEPENDENTLY,
        requested_at=NOW,
    )

    adapter, professor, assessment = make_adapter(
        request
    )

    with pytest.raises(
        ValueError,
        match="must match",
    ):
        adapter.run_turn(
            make_state(),
            decision_id="decision-time",
            requested_at=NOW + timedelta(seconds=1),
        )

    assert not professor.calls
    assert not assessment.calls


def test_explicit_request_cannot_be_reused_for_another_turn():
    request = make_request(
        StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC
    )

    adapter, professor, assessment = make_adapter(
        request
    )

    adapter.run_turn(
        make_state(),
        decision_id="decision-first",
        requested_at=NOW,
    )

    with pytest.raises(
        RuntimeError,
        match="already been used",
    ):
        adapter.run_turn(
            make_state(),
            decision_id="decision-second",
            requested_at=NOW,
        )

    assert len(assessment.calls) == 1
    assert not professor.calls


def test_request_cannot_silently_produce_professor_action():
    adapter, professor, assessment = make_adapter()

    with pytest.raises(
        ValueError,
        match="did not select an assessment action",
    ):
        adapter.run_turn(
            make_state(
                ObjectiveStateLabel.DEVELOPING
            ),
            decision_id="decision-review",
            requested_at=NOW,
        )

    assert len(professor.calls) == 1
    assert not assessment.calls

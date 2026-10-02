"""
URPP 13E-4D-3 integration and temporal safety tests.

Use the existing persisted Numeric Session fixture.
No real LLM, authentication service or production
database is involved.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.session_observed_turn_v01 import (
    run_observed_numeric_session_turn_v01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    environment,
    record_hint,
)

from test_post_turn_shadow_observer_v01 import (
    CountingAgent,
    CountingDecisionEngine,
)

from test_session_observation_source_v01 import (
    complete_existing_assignment,
    make_source,
)


def make_observed_stack(engine, assistance, decision_at):
    source = make_source(engine, assistance)

    decision_engine = CountingDecisionEngine()
    professor = CountingAgent()
    assessment = CountingAgent()

    orchestrator = PersonalizedTeachingTurnOrchestratorV01(
        decision_engine=decision_engine,
        professor_agent=professor,
        assessment_agent=assessment,
    )

    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=decision_at,
    )

    return (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    )


def execute(
    source,
    orchestrator,
    state,
    decision_at,
    *,
    session_id="session-001",
):
    return run_observed_numeric_session_turn_v01(
        orchestrator=orchestrator,
        observation_source=source,
        objective_state=state,
        session_id=session_id,
        decision_id="decision-observed-4d3",
        requested_at=decision_at,
    )


def assert_single_authoritative_turn(
    engine,
    professor,
    assessment,
):
    assert engine.calls == 1
    assert professor.calls + assessment.calls == 1


def test_persisted_hint_reaches_shadow_without_redeciding(
    environment,
):
    _, engine, assistance, service, delivery = environment

    record_hint(assistance, delivery)

    complete_existing_assignment(
        service,
        delivery,
    )

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    outcome = execute(
        source,
        orchestrator,
        state,
        decision_at,
    )

    assert outcome.status == "evaluated"
    assert outcome.report is not None

    assert outcome.report.observed_attempt_count == 1
    assert outcome.report.app_hint_attempt_count == 1

    assert outcome.report.action_execution_authorized is False
    assert outcome.report.verified_independence is False
    assert outcome.report.mastery_eligible is False

    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert_single_authoritative_turn(
        decision_engine,
        professor,
        assessment,
    )


def test_pending_assignment_produces_unavailable_observation(
    environment,
):
    _, engine, assistance, _, _ = environment

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    outcome = execute(
        source,
        orchestrator,
        state,
        decision_at,
    )

    assert outcome.status == "unavailable"
    assert outcome.report is None

    assert outcome.completed_turn.content == (
        "Completed teaching content."
    )

    assert_single_authoritative_turn(
        decision_engine,
        professor,
        assessment,
    )


def test_future_attempt_does_not_enter_earlier_decision(
    environment,
):
    _, engine, assistance, service, delivery = environment

    complete_existing_assignment(
        service,
        delivery,
    )

    decision_at = NOW + timedelta(seconds=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    outcome = execute(
        source,
        orchestrator,
        state,
        decision_at,
    )

    assert outcome.status == "unavailable"
    assert outcome.report is None

    assert_single_authoritative_turn(
        decision_engine,
        professor,
        assessment,
    )


def test_observation_read_failure_preserves_actual_teaching(
    environment,
    monkeypatch,
):
    _, engine, assistance, _, _ = environment

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    def fail_read(**kwargs):
        raise RuntimeError(
            "internal database read failure with private details"
        )

    monkeypatch.setattr(
        source,
        "build",
        fail_read,
    )

    outcome = execute(
        source,
        orchestrator,
        state,
        decision_at,
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

    assert_single_authoritative_turn(
        decision_engine,
        professor,
        assessment,
    )


@pytest.mark.parametrize(
    "event_offset_seconds",
    (20, 60),
)
def test_inconsistent_assistance_event_time_is_rejected(
    environment,
    monkeypatch,
    event_offset_seconds,
):
    _, engine, assistance, service, delivery = environment

    record_hint(assistance, delivery)

    complete_existing_assignment(
        service,
        delivery,
    )

    decision_at = NOW + timedelta(minutes=1)

    source = make_source(engine, assistance)

    original_snapshot = source._snapshots.build_snapshot

    def snapshot_with_inconsistent_event(**kwargs):
        snapshot = original_snapshot(**kwargs)

        # Inject a malformed timestamp only into this test's
        # in-memory Snapshot. No persisted row is modified.
        #
        # The first case is after Attempt submission.
        # The second case is at the decision boundary.
        event = SimpleNamespace(
            occurred_at=(
                NOW
                + timedelta(seconds=event_offset_seconds)
            ),
        )

        return SimpleNamespace(
            assignment_id=snapshot.assignment_id,
            attempt_id=snapshot.attempt_id,
            student_id=snapshot.student_id,
            course_id=snapshot.course_id,
            objective_id=snapshot.objective_id,
            session_id=snapshot.session_id,
            assistance_events=(event,),
        )

    monkeypatch.setattr(
        source._snapshots,
        "build_snapshot",
        snapshot_with_inconsistent_event,
    )

    with pytest.raises(
        ValueError,
        match="Historical assistance event time",
    ):
        source.build(
            student_id="student-001",
            course_id="course-001",
            objective_id="objective-001",
            session_id="session-001",
            decision_at=decision_at,
        )



def test_unknown_session_is_rejected_before_teaching(
    environment,
):
    _, engine, assistance, _, _ = environment

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    with pytest.raises(
        LookupError,
        match="session",
    ):
        execute(
            source,
            orchestrator,
            state,
            decision_at,
            session_id="missing-session",
        )

    assert decision_engine.calls == 0
    assert professor.calls + assessment.calls == 0


def test_wrong_student_scope_is_rejected_before_teaching(
    environment,
):
    _, engine, assistance, _, _ = environment

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    # Synthetic mismatch for scope-validation testing.
    # This does not represent an authorized State lookup.
    wrong_state = state.model_copy(
        update={"student_id": "another-student"}
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        execute(
            source,
            orchestrator,
            wrong_state,
            decision_at,
        )

    assert decision_engine.calls == 0
    assert professor.calls + assessment.calls == 0


def test_authoritative_agent_failure_is_not_hidden_by_read_failure(
    environment,
    monkeypatch,
):
    _, engine, assistance, _, _ = environment

    decision_at = NOW + timedelta(minutes=1)

    (
        source,
        orchestrator,
        state,
        decision_engine,
        professor,
        assessment,
    ) = make_observed_stack(
        engine,
        assistance,
        decision_at,
    )

    def fail_observation_read(**kwargs):
        raise RuntimeError(
            "optional observation read failure"
        )

    def fail_agent(**kwargs):
        raise RuntimeError(
            "authoritative teaching failure"
        )

    monkeypatch.setattr(
        source,
        "build",
        fail_observation_read,
    )

    monkeypatch.setattr(
        professor,
        "produce",
        fail_agent,
    )

    monkeypatch.setattr(
        assessment,
        "produce",
        fail_agent,
    )

    with pytest.raises(
        RuntimeError,
        match="authoritative teaching failure",
    ):
        execute(
            source,
            orchestrator,
            state,
            decision_at,
        )

    assert decision_engine.calls == 1

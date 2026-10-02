"""
URPP Design 01D — Recoverable Numeric Teaching Session tests.

Uses synthetic student data and isolated SQLite databases.
No authentication, external LLM, or PostgreSQL server is used.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)

from app.services.decision.recoverable_numeric_session_v01 import (
    RecoverableNumericSessionServiceV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    TeachingTurnOrchestratorV01,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


class StubAgent:
    def __init__(self, content: str):
        self.content = content

    def produce(self, *, context, decision):
        return self.content


@pytest.fixture
def environment():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(factory)

    current_time = [
        NOW + timedelta(seconds=2)
    ]

    assignments = NumericAssignmentRepositoryV01(
        assessments,
        clock=lambda: current_time[0],
    )

    sessions = NumericSessionRecordRepositoryV01(
        assessments
    )

    orchestrator = TeachingTurnOrchestratorV01(
        decision_engine=DecisionEngineV01(
            RuleBasedControllerV01()
        ),
        professor_agent=StubAgent(
            "Professor explanation."
        ),
        assessment_agent=StubAgent(
            "Unrelated Agent-generated text."
        ),
    )

    def make_service(
        *,
        student_id="student-001",
        session_id="session-001",
    ):
        return RecoverableNumericSessionServiceV01(
            assessment_repository=assessments,
            assignment_repository=assignments,
            session_repository=sessions,
            turn_orchestrator=orchestrator,
            student_id=student_id,
            course_id="course-001",
            objective_id="objective-001",
            session_id=session_id,
        )

    yield (
        assessments,
        assignments,
        sessions,
        make_service,
        current_time,
    )

    engine.dispose()


def make_item(
    *,
    item_id="item-001",
    expected=5.0,
    prompt="What is 2 + 3?",
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id="objective-001",
        prompt=prompt,
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def deliver(
    service,
    *,
    item_id="item-001",
    decision_id="decision-001",
    requested_at=NOW,
):
    return service.deliver_numeric_assessment(
        assessment_item_id=item_id,
        item_revision=1,
        decision_id=decision_id,
        requested_at=requested_at,
    )


def test_new_session_is_persisted_and_can_be_resumed(
    environment,
):
    _, _, _, make_service, _ = environment

    first = make_service()

    initial = first.start(started_at=NOW)

    assert initial.pending is None
    assert initial.completed_assignment_ids == ()
    assert initial.state.state.value == "unknown"

    restarted = make_service()

    restored = restarted.resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is None
    assert restored.completed_assignment_ids == ()
    assert restored.state.state.value == "unknown"


def test_pending_question_survives_service_restart(
    environment,
):
    assessments, _, _, make_service, _ = environment

    assessments.save_item(make_item(), revision=1)

    first = make_service()
    first.start(started_at=NOW)

    delivery = deliver(first)

    assert delivery.prompt == "What is 2 + 3?"

    restarted = make_service()

    recovered = restarted.resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert recovered.pending is not None
    assert (
        recovered.pending.assignment_id
        == delivery.assignment_id
    )
    assert recovered.pending.item_revision == 1
    assert recovered.pending.prompt == "What is 2 + 3?"


def test_completed_answer_survives_service_restart(
    environment,
):
    assessments, assignments, _, make_service, _ = environment

    assessments.save_item(make_item(), revision=1)

    first = make_service()
    first.start(started_at=NOW)

    delivery = deliver(first)

    first.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=3),
    )

    restarted = make_service()

    recovered = restarted.resume(
        as_of=NOW + timedelta(seconds=4)
    )

    stored = assignments.load_assignment(
        delivery.assignment_id
    )

    assert stored.status == "completed"
    assert stored.completed_attempt_id is not None

    assert recovered.pending is None
    assert recovered.completed_assignment_ids == (
        delivery.assignment_id,
    )

    # Submission provenance remains unknown in the current
    # internal API, so correctness is not independent mastery.
    assert recovered.state.independent_success_count == 0
    assert recovered.state.state.value == "unknown"


def test_recovered_session_can_continue_with_next_turn(
    environment,
):
    assessments, _, _, make_service, current_time = environment

    assessments.save_item(
        make_item(),
        revision=1,
    )

    assessments.save_item(
        make_item(
            item_id="item-002",
            expected=7.0,
            prompt="What is 3 + 4?",
        ),
        revision=1,
    )

    first_service = make_service()
    first_service.start(started_at=NOW)

    first_delivery = deliver(first_service)

    first_service.submit_numeric_answer(
        assignment_id=first_delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=3),
    )

    current_time[0] = NOW + timedelta(seconds=5)

    restarted = make_service()

    second_delivery = deliver(
        restarted,
        item_id="item-002",
        decision_id="decision-002",
        requested_at=NOW + timedelta(seconds=4),
    )

    assert second_delivery.prompt == "What is 3 + 4?"

    final = restarted.submit_numeric_answer(
        assignment_id=second_delivery.assignment_id,
        response_text="7",
        as_of=NOW + timedelta(seconds=6),
    )

    assert final.pending is None
    assert final.completed_assignment_ids == (
        first_delivery.assignment_id,
        second_delivery.assignment_id,
    )
    assert final.state.independent_success_count == 0


def test_other_student_cannot_resume_session(
    environment,
):
    _, _, _, make_service, _ = environment

    make_service().start(started_at=NOW)

    other_student = make_service(
        student_id="student-002",
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        other_student.resume(
            as_of=NOW + timedelta(seconds=1)
        )


def test_repeated_start_does_not_erase_progress(
    environment,
):
    assessments, _, _, make_service, _ = environment

    assessments.save_item(make_item(), revision=1)

    first = make_service()
    first.start(started_at=NOW)

    delivery = deliver(first)

    restarted = make_service()

    result = restarted.start(
        started_at=NOW + timedelta(seconds=1)
    )

    assert result.pending is not None
    assert (
        result.pending.assignment_id
        == delivery.assignment_id
    )


def test_pending_assignment_cannot_be_replaced_after_restart(
    environment,
):
    assessments, _, _, make_service, _ = environment

    assessments.save_item(make_item(), revision=1)

    first = make_service()
    first.start(started_at=NOW)

    deliver(first)

    restarted = make_service()

    with pytest.raises(
        ValueError,
        match="pending assignment",
    ):
        deliver(
            restarted,
            decision_id="decision-002",
            requested_at=NOW + timedelta(seconds=1),
        )


def test_recovery_after_database_commit_and_state_failure(
    environment,
):
    assessments, assignments, _, make_service, _ = environment

    assessments.save_item(make_item(), revision=1)

    first = make_service()
    first.start(started_at=NOW)

    delivery = deliver(first)

    class FailingStateService:
        def estimate_from_completed_assignments(
            self,
            assignment_ids,
            **kwargs,
        ):
            raise RuntimeError(
                "Simulated state reconstruction failure."
            )

    # The pre-submission resume has no completed attempts.
    # The injected failure occurs after the repository commits
    # the newly submitted attempt.
    first._completed_state_service = FailingStateService()

    with pytest.raises(
        RuntimeError,
        match="Simulated state reconstruction failure",
    ):
        first.submit_numeric_answer(
            assignment_id=delivery.assignment_id,
            response_text="5",
            as_of=NOW + timedelta(seconds=3),
        )

    stored = assignments.load_assignment(
        delivery.assignment_id
    )

    assert stored.status == "completed"
    assert stored.completed_attempt_id is not None

    # Simulate a new service instance after the process failure.
    restarted = make_service()

    recovered = restarted.resume(
        as_of=NOW + timedelta(seconds=4)
    )

    assert recovered.pending is None
    assert recovered.completed_assignment_ids == (
        delivery.assignment_id,
    )

    assert recovered.state.independent_success_count == 0

    with pytest.raises(
        ValueError,
        match="No numeric assignment",
    ):
        restarted.submit_numeric_answer(
            assignment_id=delivery.assignment_id,
            response_text="5",
            as_of=NOW + timedelta(seconds=5),
        )

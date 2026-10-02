"""
URPP Design 01D — Numeric Assignment DB Invariants V0.1.

Tests:
- one pending assignment per session;
- unique decision ID per session;
- pending slot release after completion;
- concurrent issuance and submission using file-backed SQLite;
- rollback when submission fails between Attempt INSERT
  and Assignment UPDATE.

These tests do not establish PostgreSQL concurrency guarantees
or authenticate the supplied student/session identities.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from sqlalchemy import (
    create_engine,
    event,
    func,
    select,
)

from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
)

from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
    StudentAttemptRow,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    AssessmentDeliveryV01,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


@pytest.fixture
def db(tmp_path):
    database_path = tmp_path / "numeric_assignment_invariants.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"timeout": 20},
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

    assignments = NumericAssignmentRepositoryV01(
        assessments,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    assessments.save_item(
        AssessmentItemV02(
            assessment_item_id="item-001",
            course_id="course-001",
            objective_id="objective-001",
            prompt="What is 2 + 3?",
            rubric=NumericRubricV02(
                expected_value=5.0,
                absolute_tolerance=0.0,
                rubric_version="numeric-rubric-v1",
            ),
            alignment_verified=True,
        ),
        revision=1,
    )

    yield engine, factory, assessments, assignments

    engine.dispose()


def make_delivery(
    *,
    assignment_id,
    decision_id,
):
    return AssessmentDeliveryV01(
        assignment_id=assignment_id,
        decision_id=decision_id,
        assessment_item_id="item-001",
        item_revision=1,
        prompt="What is 2 + 3?",
        selected_action=(
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT
        ),
        assigned_at=NOW,
    )


def issue(
    assignments,
    *,
    assignment_id,
    decision_id,
    session_id="session-001",
):
    from app.repositories.numeric_session_records_v01 import (
        NumericSessionRecordRepositoryV01,
    )
    from app.repositories.assessment_records_v02 import (
        AssessmentRecordRepositoryV02,
    )

    assessments = AssessmentRecordRepositoryV02(
        assignments._session_factory
    )
    NumericSessionRecordRepositoryV01(assessments).register(
        session_id=session_id,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        started_at=NOW,
    )

    return assignments.issue_assignment(
        make_delivery(
            assignment_id=assignment_id,
            decision_id=decision_id,
        ),
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id=session_id,
    )


def submit(
    assignments,
    *,
    assignment_id,
    session_id="session-001",
):
    return assignments.submit_numeric_response(
        assignment_id=assignment_id,
        student_id="student-001",
        session_id=session_id,
        response_text="5",
    )


def count_attempts(factory):
    with factory() as session:
        return session.scalar(
            select(func.count()).select_from(
                StudentAttemptRow
            )
        )


def test_second_pending_assignment_is_rejected_by_database(db):
    _, _, _, assignments = db

    issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
    )

    with pytest.raises(IntegrityError):
        issue(
            assignments,
            assignment_id="assignment-002",
            decision_id="decision-002",
        )

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).status == "pending"
    )

    with pytest.raises(LookupError):
        assignments.load_assignment(
            "assignment-002"
        )


def test_completed_assignment_releases_pending_slot(db):
    _, _, _, assignments = db

    issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
    )

    submit(
        assignments,
        assignment_id="assignment-001",
    )

    second = issue(
        assignments,
        assignment_id="assignment-002",
        decision_id="decision-002",
    )

    assert second.status == "pending"

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).status == "completed"
    )


def test_completed_decision_id_cannot_be_reused(db):
    _, _, _, assignments = db

    issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
    )

    submit(
        assignments,
        assignment_id="assignment-001",
    )

    with pytest.raises(IntegrityError):
        issue(
            assignments,
            assignment_id="assignment-002",
            decision_id="decision-001",
        )

    with pytest.raises(LookupError):
        assignments.load_assignment(
            "assignment-002"
        )


def test_different_sessions_can_each_have_one_pending(db):
    _, _, _, assignments = db

    first = issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
        session_id="session-001",
    )

    second = issue(
        assignments,
        assignment_id="assignment-002",
        decision_id="decision-001",
        session_id="session-002",
    )

    assert first.status == "pending"
    assert second.status == "pending"

    assert first.session_id != second.session_id


def test_concurrent_issuance_produces_at_most_one_pending(db):
    _, _, _, assignments = db

    barrier = Barrier(2)

    def worker(number):
        barrier.wait(timeout=10)

        assignment_id = f"assignment-{number:03d}"
        decision_id = f"decision-{number:03d}"

        try:
            issue(
                assignments,
                assignment_id=assignment_id,
                decision_id=decision_id,
            )

            return ("saved", assignment_id)

        except IntegrityError:
            return ("conflict", assignment_id)

        except OperationalError as exc:
            # SQLite can report a write-lock conflict instead of
            # waiting to return a UNIQUE-constraint violation.
            # Both outcomes must leave the database consistent.
            if "locked" not in str(exc).lower():
                raise

            return ("sqlite-locked", assignment_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, number)
            for number in (1, 2)
        ]

        results = [
            future.result(timeout=30)
            for future in futures
        ]

    saved = [
        assignment_id
        for outcome, assignment_id in results
        if outcome == "saved"
    ]

    assert len(saved) == 1

    for outcome, assignment_id in results:
        if outcome == "saved":
            assert (
                assignments.load_assignment(
                    assignment_id
                ).status == "pending"
            )
        else:
            assert outcome in {
                "conflict",
                "sqlite-locked",
            }

            with pytest.raises(LookupError):
                assignments.load_assignment(
                    assignment_id
                )


def test_concurrent_submission_creates_exactly_one_attempt(db):
    _, factory, _, assignments = db

    issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
    )

    barrier = Barrier(2)

    def worker():
        barrier.wait(timeout=10)

        try:
            attempt = submit(
                assignments,
                assignment_id="assignment-001",
            )

            return ("saved", attempt.attempt_id)

        except ValueError as exc:
            if not (
                "completed" in str(exc).lower()
                or "another submission" in str(exc).lower()
            ):
                raise

            return ("conflict", None)

        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise

            return ("sqlite-locked", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker)
            for _ in range(2)
        ]

        results = [
            future.result(timeout=30)
            for future in futures
        ]

    saved = [
        attempt_id
        for outcome, attempt_id in results
        if outcome == "saved"
    ]

    assert len(saved) == 1
    assert count_attempts(factory) == 1

    assignment = assignments.load_assignment(
        "assignment-001"
    )

    assert assignment.status == "completed"
    assert assignment.completed_attempt_id == saved[0]

    assert all(
        outcome in {
            "saved",
            "conflict",
            "sqlite-locked",
        }
        for outcome, _ in results
    )


def test_failed_assignment_update_rolls_back_attempt(db):
    engine, factory, _, assignments = db

    issue(
        assignments,
        assignment_id="assignment-001",
        decision_id="decision-001",
    )

    def interrupt_assignment_update(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        normalized = statement.strip().upper()

        if (
            normalized.startswith("UPDATE")
            and "NUMERIC_ASSIGNMENTS_V01" in normalized
        ):
            raise RuntimeError(
                "Simulated failure after Attempt INSERT."
            )

    event.listen(
        engine,
        "before_cursor_execute",
        interrupt_assignment_update,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="Simulated failure",
        ):
            submit(
                assignments,
                assignment_id="assignment-001",
            )

    finally:
        event.remove(
            engine,
            "before_cursor_execute",
            interrupt_assignment_update,
        )

    assignment = assignments.load_assignment(
        "assignment-001"
    )

    assert assignment.status == "pending"
    assert assignment.completed_attempt_id is None
    assert count_attempts(factory) == 0

    # After the failed transaction has rolled back,
    # the original assignment remains available.
    attempt = submit(
        assignments,
        assignment_id="assignment-001",
    )

    assert count_attempts(factory) == 1

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).completed_attempt_id
        == attempt.attempt_id
    )

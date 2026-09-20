"""
URPP Design 01D — Registered Session Foreign Key tests.

The strict assignment path is bound to the database Session
through a Composite Foreign Key.

SQLite foreign_keys=ON is required for enforcement.

The legacy internal compatibility path remains nullable
and does not receive the same database guarantee.
"""

from datetime import datetime, timezone

import pytest

from sqlalchemy import (
    create_engine,
    event,
    select,
)

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
    NumericAssignmentRow,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
    NumericTeachingSessionRowV01,
)

from app.repositories.numeric_database_readiness_v01 import (
    check_sqlite_numeric_database,
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


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


@pytest.fixture
def environment(tmp_path):
    database_path = tmp_path / "registered_session_fk.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}"
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
        assessments
    )

    sessions = NumericSessionRecordRepositoryV01(
        assessments
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

    yield (
        database_path,
        factory,
        assignments,
        sessions,
    )

    engine.dispose()


def register(sessions):
    return sessions.register(
        session_id="session-001",
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        started_at=NOW,
    )


def issue(
    assignments,
):
    return assignments.issue_assignment(
        AssessmentDeliveryV01(
            assignment_id="assignment-001",
            decision_id="decision-001",
            assessment_item_id="item-001",
            item_revision=1,
            prompt="What is 2 + 3?",
            selected_action=(
                TeachingActionV01.DIAGNOSTIC_ASSESSMENT
            ),
            assigned_at=NOW,
        ),
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
    )


def test_strict_assignment_has_registered_session_binding(
    environment,
):
    path, factory, assignments, sessions = environment

    register(sessions)
    issue(assignments)

    with factory() as db:
        row = db.get(
            NumericAssignmentRow,
            "assignment-001",
        )

        assert row.registered_session_id == "session-001"

    readiness = check_sqlite_numeric_database(path)

    assert readiness.schema_version == "current"
    assert readiness.assignment_count == 1


def test_database_rejects_deleting_referenced_session(
    environment,
):
    _, factory, assignments, sessions = environment

    register(sessions)
    issue(assignments)

    with factory() as db:
        with pytest.raises(IntegrityError):
            with db.begin():
                session_row = db.get(
                    NumericTeachingSessionRowV01,
                    "session-001",
                )

                db.delete(session_row)
                db.flush()

    with factory() as db:
        assert db.get(
            NumericTeachingSessionRowV01,
            "session-001",
        ) is not None


def test_database_rejects_changing_referenced_student(
    environment,
):
    _, factory, assignments, sessions = environment

    register(sessions)
    issue(assignments)

    with factory() as db:
        with pytest.raises(IntegrityError):
            with db.begin():
                session_row = db.get(
                    NumericTeachingSessionRowV01,
                    "session-001",
                )

                session_row.student_id = "another-student"
                db.flush()


def test_database_rejects_changing_assignment_scope(
    environment,
):
    _, factory, assignments, sessions = environment

    register(sessions)
    issue(assignments)

    with factory() as db:
        with pytest.raises(IntegrityError):
            with db.begin():
                row = db.get(
                    NumericAssignmentRow,
                    "assignment-001",
                )

                row.course_id = "another-course"
                db.flush()



def seed_legacy_unbound_assignment(assignments):
    """
    TEST ONLY: construct a historical unbound Assignment row.
    Normal Assignment issuance must never use this path.
    """

    from app.repositories.numeric_assignment_v01 import (
        NumericAssignmentRow,
    )

    with assignments._session_factory() as db:
        with db.begin():
            db.add(
                NumericAssignmentRow(
                    assignment_id="assignment-001",
                    decision_id="decision-001",
                    student_id="student-001",
                    course_id="course-001",
                    objective_id="objective-001",
                    session_id="session-001",
                    assessment_item_id="item-001",
                    item_revision=1,
                    assigned_at_utc=NOW.isoformat(),
                    status="pending",
                    pending_session_key="session-001",
                    registered_session_id=None,
                    completed_attempt_id=None,
                )
            )

    return assignments.load_assignment("assignment-001")


def test_database_rejects_unregistered_binding(
    environment,
):
    _, factory, assignments, _ = environment

    # Seed a historical unbound row directly for this test.
    seed_legacy_unbound_assignment(assignments)

    # Attempting to turn that record into a registered one
    # without creating the Session must fail at the DB layer.
    with factory() as db:
        with pytest.raises(IntegrityError):
            with db.begin():
                row = db.get(
                    NumericAssignmentRow,
                    "assignment-001",
                )

                row.registered_session_id = "session-001"
                db.flush()


def test_historical_row_remains_explicitly_unbound(
    environment,
):
    _, factory, assignments, _ = environment

    seed_legacy_unbound_assignment(assignments)

    with factory() as db:
        row = db.scalar(
            select(NumericAssignmentRow).where(
                NumericAssignmentRow.assignment_id
                == "assignment-001"
            )
        )

        assert row.registered_session_id is None

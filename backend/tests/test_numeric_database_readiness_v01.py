"""
URPP Design 01D — Numeric Database Readiness tests.

All databases are synthetic temporary SQLite files.

No application database is opened by these tests.
"""

import sqlite3

from datetime import datetime, timezone

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

from app.repositories.numeric_database_readiness_v01 import (
    DatabaseNotReadyError,
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


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "urpp_readiness.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
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

    assessments = AssessmentRecordRepositoryV02(
        factory
    )

    sessions = NumericSessionRecordRepositoryV01(
        assessments
    )

    assignments = NumericAssignmentRepositoryV01(
        assessments
    )

    yield (
        path,
        assessments,
        sessions,
        assignments,
    )

    engine.dispose()


def add_item(assessments):
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


def register_session(
    sessions,
    *,
    course_id="course-001",
    started_at=NOW,
):
    sessions.register(
        session_id="session-001",
        student_id="student-001",
        course_id=course_id,
        objective_id="objective-001",
        started_at=started_at,
    )


def add_assignment(assignments, *, legacy=False):
    if legacy:
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


def test_fresh_empty_database_passes(database):
    path, _, _, _ = database

    result = check_sqlite_numeric_database(path)

    assert result.schema_version == "current"
    assert result.assignment_count == 0
    assert result.teaching_session_count == 0


def test_registered_session_and_assignment_pass(database):
    path, assessments, sessions, assignments = database

    add_item(assessments)
    register_session(sessions)
    add_assignment(assignments)

    result = check_sqlite_numeric_database(path)

    assert result.assessment_item_count == 1
    assert result.assignment_count == 1
    assert result.teaching_session_count == 1


def test_missing_database_is_not_created(tmp_path):
    missing = tmp_path / "not_created.sqlite"

    with pytest.raises(
        DatabaseNotReadyError,
        match="does not exist",
    ):
        check_sqlite_numeric_database(missing)

    assert not missing.exists()


def test_missing_required_tables_are_rejected(tmp_path):
    path = tmp_path / "incomplete.sqlite"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"
        )

    with pytest.raises(
        DatabaseNotReadyError,
        match="missing required tables",
    ):
        check_sqlite_numeric_database(path)


def test_orphan_assignment_is_rejected(database):
    path, assessments, _, assignments = database

    add_item(assessments)

    # Historical unbound rows may have a NULL binding.
    # Readiness must reject the invalid stored record.
    add_assignment(assignments, legacy=True)

    with pytest.raises(
        DatabaseNotReadyError,
        match="missing Teaching Session",
    ):
        check_sqlite_numeric_database(path)


def test_assignment_session_scope_mismatch_is_rejected(
    database,
):
    path, assessments, sessions, assignments = database

    add_item(assessments)

    register_session(
        sessions,
        course_id="different-course",
    )

    add_assignment(assignments, legacy=True)

    with pytest.raises(
        DatabaseNotReadyError,
        match="inconsistent",
    ):
        check_sqlite_numeric_database(path)


def test_assignment_before_session_start_is_rejected(
    database,
):
    path, assessments, sessions, assignments = database

    add_item(assessments)

    register_session(
        sessions,
        started_at=NOW.replace(hour=1),
    )

    add_assignment(assignments, legacy=True)

    with pytest.raises(
        DatabaseNotReadyError,
        match="predates its Teaching Session",
    ):
        check_sqlite_numeric_database(path)


def test_existing_session_does_not_make_legacy_assignment_ready(
    database,
):
    path, assessments, sessions, assignments = database

    add_item(assessments)
    register_session(sessions)

    # An existing Session is not enough: the Assignment must
    # actually be bound through registered_session_id.
    add_assignment(assignments, legacy=True)

    with pytest.raises(
        DatabaseNotReadyError,
        match="Legacy unbound assignments",
    ):
        check_sqlite_numeric_database(path)

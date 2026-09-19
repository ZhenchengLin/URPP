"""
URPP Design 01D — Registered Numeric Assignment tests.

Verifies strict write-time Session checks without changing
the existing legacy internal repository contract.

The strict check is performed in the Assignment INSERT
transaction. This is not yet a database foreign-key constraint.
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
def environment(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///"
        + str(tmp_path / "registered_assignment.sqlite")
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

    yield assessments, assignments, sessions

    engine.dispose()


def register(
    sessions,
    *,
    student_id="student-001",
    course_id="course-001",
    objective_id="objective-001",
    started_at=NOW,
):
    return sessions.register(
        session_id="session-001",
        student_id=student_id,
        course_id=course_id,
        objective_id=objective_id,
        started_at=started_at,
    )


def issue(
    assignments,
    *,
    require_registered_session=True,
    assigned_at=NOW,
):
    delivery = AssessmentDeliveryV01(
        assignment_id="assignment-001",
        decision_id="decision-001",
        assessment_item_id="item-001",
        item_revision=1,
        prompt="What is 2 + 3?",
        selected_action=(
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT
        ),
        assigned_at=assigned_at,
    )

    return assignments.issue_assignment(
        delivery,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
        require_registered_session=require_registered_session,
    )


def test_strict_assignment_requires_existing_session(
    environment,
):
    _, assignments, _ = environment

    with pytest.raises(
        LookupError,
        match="Registered teaching session was not found",
    ):
        issue(assignments)

    with pytest.raises(LookupError):
        assignments.load_assignment("assignment-001")


def test_strict_assignment_accepts_matching_session(
    environment,
):
    _, assignments, sessions = environment

    register(sessions)

    saved = issue(assignments)

    assert saved.assignment_id == "assignment-001"
    assert saved.session_id == "session-001"
    assert saved.status == "pending"


def test_strict_assignment_rejects_student_mismatch(
    environment,
):
    _, assignments, sessions = environment

    register(
        sessions,
        student_id="different-student",
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        issue(assignments)

    with pytest.raises(LookupError):
        assignments.load_assignment("assignment-001")


def test_strict_assignment_rejects_course_mismatch(
    environment,
):
    _, assignments, sessions = environment

    register(
        sessions,
        course_id="different-course",
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        issue(assignments)


def test_strict_assignment_rejects_earlier_assignment(
    environment,
):
    _, assignments, sessions = environment

    register(
        sessions,
        started_at=NOW + timedelta(minutes=1),
    )

    with pytest.raises(
        ValueError,
        match="predates its registered",
    ):
        issue(assignments)

    with pytest.raises(LookupError):
        assignments.load_assignment("assignment-001")


def test_legacy_mode_remains_explicitly_compatible(
    environment,
):
    _, assignments, _ = environment

    # Existing internal prototypes and their tests may not
    # register a Session before issuing an Assignment.
    # This compatibility path is NOT database-level protection.
    saved = issue(
        assignments,
        require_registered_session=False,
    )

    assert saved.status == "pending"

    # The strict path is expected to reject the same missing
    # Session; the legacy behavior must not be treated as safe
    # for a public student-submission workflow.

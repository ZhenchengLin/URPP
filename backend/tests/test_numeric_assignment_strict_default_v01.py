"""
URPP Design 01D — Strict Assignment Default tests.

The normal Assignment Repository call requires a registered
teaching session. Legacy behavior remains explicitly opt-in
during the compatibility transition.
"""

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
    NumericAssignmentRow,
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
        + str(tmp_path / "strict_default.sqlite")
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

    yield factory, assignments, sessions

    engine.dispose()


def make_delivery():

    return AssessmentDeliveryV01(
        assignment_id="assignment-001",
        decision_id="decision-001",
        assessment_item_id="item-001",
        item_revision=1,
        prompt="What is 2 + 3?",
        selected_action=(
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT
        ),
        assigned_at=NOW,
    )


def issue_without_compatibility_flag(assignments):

    return assignments.issue_assignment(
        make_delivery(),
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
    )


def test_default_rejects_missing_registered_session(
    environment,
):
    _, assignments, _ = environment

    with pytest.raises(
        LookupError,
        match="Registered teaching session was not found",
    ):
        issue_without_compatibility_flag(assignments)

    with pytest.raises(LookupError):
        assignments.load_assignment(
            "assignment-001"
        )


def test_default_creates_registered_session_binding(
    environment,
):
    factory, assignments, sessions = environment

    sessions.register(
        session_id="session-001",
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        started_at=NOW,
    )

    saved = issue_without_compatibility_flag(
        assignments
    )

    assert saved.status == "pending"

    with factory() as db:

        row = db.get(
            NumericAssignmentRow,
            "assignment-001",
        )

        assert row.registered_session_id == "session-001"

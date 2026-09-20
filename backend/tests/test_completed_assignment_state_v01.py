"""
URPP Design 01D — Completed Assignment State tests.

Tests the path from persisted assignment to stored attempt
to the existing numeric scoring and student-state engine.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, event
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

from app.services.decision.completed_assignment_state_v01 import (
    CompletedAssignmentStateServiceV01,
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

    assessments = AssessmentRecordRepositoryV02(
        factory
    )

    assignments = NumericAssignmentRepositoryV01(
        assessments,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    service = CompletedAssignmentStateServiceV01(
        assessment_repository=assessments,
        assignment_repository=assignments,
    )

    yield assessments, assignments, service

    engine.dispose()


def make_item():
    return AssessmentItemV02(
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
    )


def prepare_assignment(
    environment,
    *,
    assignment_id="assignment-001",
    student_id="student-001",
    session_id="session-001",
):
    assessments, assignments, _ = environment

    try:
        assessments.load_item(
            "item-001",
            revision=1,
        )
    except LookupError:
        assessments.save_item(
            make_item(),
            revision=1,
        )

    delivery = AssessmentDeliveryV01(
        assignment_id=assignment_id,
        decision_id=f"decision-{assignment_id}",
        assessment_item_id="item-001",
        item_revision=1,
        prompt="What is 2 + 3?",
        selected_action=(
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT
        ),
        assigned_at=NOW,
    )

    from app.repositories.numeric_session_records_v01 import (
        NumericSessionRecordRepositoryV01,
    )

    NumericSessionRecordRepositoryV01(assessments).register(
        session_id=session_id,
        student_id=student_id,
        course_id="course-001",
        objective_id="objective-001",
        started_at=NOW,
    )

    assignments.issue_assignment(
        delivery,
        student_id=student_id,
        course_id="course-001",
        objective_id="objective-001",
        session_id=session_id,
    )


def complete_assignment(
    environment,
    *,
    assignment_id="assignment-001",
    student_id="student-001",
    session_id="session-001",
):
    _, assignments, _ = environment

    return assignments.submit_numeric_response(
        assignment_id=assignment_id,
        student_id=student_id,
        session_id=session_id,
        response_text="5",
    )


def estimate(
    environment,
    assignment_ids,
    **overrides,
):
    _, _, service = environment

    parameters = {
        "student_id": "student-001",
        "session_id": "session-001",
        "course_id": "course-001",
        "objective_id": "objective-001",
        "as_of": NOW + timedelta(seconds=3),
    }

    parameters.update(overrides)

    return service.estimate_from_completed_assignments(
        assignment_ids,
        **parameters,
    )


def test_completed_assignment_reaches_state_engine(
    environment,
):
    prepare_assignment(environment)

    complete_assignment(environment)

    state = estimate(
        environment,
        ["assignment-001"],
    )

    assert state.state.value == "unknown"

    # Implementation 05 deliberately records assistance and
    # prior solution exposure as unknown. A correct numeric
    # response must not automatically count as independent
    # mastery evidence.
    assert state.independent_success_count == 0


def test_pending_assignment_cannot_update_state(
    environment,
):
    prepare_assignment(environment)

    with pytest.raises(
        ValueError,
        match="not completed",
    ):
        estimate(
            environment,
            ["assignment-001"],
        )


def test_another_student_scope_is_rejected(
    environment,
):
    prepare_assignment(environment)
    complete_assignment(environment)

    with pytest.raises(
        ValueError,
        match="Assignment does not match",
    ):
        estimate(
            environment,
            ["assignment-001"],
            student_id="student-002",
        )


def test_another_session_scope_is_rejected(
    environment,
):
    prepare_assignment(environment)
    complete_assignment(environment)

    with pytest.raises(
        ValueError,
        match="Assignment does not match",
    ):
        estimate(
            environment,
            ["assignment-001"],
            session_id="session-002",
        )


def test_duplicate_assignment_is_rejected(
    environment,
):
    prepare_assignment(environment)
    complete_assignment(environment)

    with pytest.raises(
        ValueError,
        match="Duplicate assignment",
    ):
        estimate(
            environment,
            [
                "assignment-001",
                "assignment-001",
            ],
        )


def test_tampered_attempt_assignment_link_is_rejected(
    environment,
):
    assessments, _, _ = environment

    prepare_assignment(environment)
    attempt = complete_assignment(environment)

    with assessments._session_factory() as session:
        with session.begin():
            row = session.get(
                StudentAttemptRow,
                attempt.attempt_id,
            )

            modified = dict(row.payload)

            modified["response_group_id"] = (
                "unrelated-response-group"
            )

            row.payload = modified

    with pytest.raises(
        ValueError,
        match="not linked",
    ):
        estimate(
            environment,
            ["assignment-001"],
        )


def test_tampered_attempt_revision_is_rejected(
    environment,
):
    assessments, _, _ = environment

    prepare_assignment(environment)

    assessments.save_item(
        make_item(),
        revision=2,
    )

    attempt = complete_assignment(environment)

    with assessments._session_factory() as session:
        with session.begin():
            row = session.get(
                StudentAttemptRow,
                attempt.attempt_id,
            )

            row.item_revision = 2

    with pytest.raises(
        ValueError,
        match="assigned item revision",
    ):
        estimate(
            environment,
            ["assignment-001"],
        )


def test_state_estimation_cannot_precede_submission(
    environment,
):
    prepare_assignment(environment)
    complete_assignment(environment)

    with pytest.raises(
        ValueError,
        match="State-estimation time precedes",
    ):
        estimate(
            environment,
            ["assignment-001"],
            as_of=NOW + timedelta(seconds=1),
        )


def test_single_string_is_not_assignment_sequence(
    environment,
):
    with pytest.raises(
        TypeError,
        match="sequence",
    ):
        estimate(
            environment,
            "assignment-001",
        )

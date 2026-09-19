"""
URPP Design 01D — Persistent Numeric Assignment tests.

Uses isolated SQLite databases and a deterministic test clock.

No real student identity or public API authentication is involved.
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
def repositories():
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

    assessment_repository = (
        AssessmentRecordRepositoryV02(factory)
    )

    assignment_repository = (
        NumericAssignmentRepositoryV01(
            assessment_repository,
            clock=lambda: NOW + timedelta(seconds=2),
        )
    )

    yield assessment_repository, assignment_repository

    engine.dispose()


def make_item(*, expected_value=5.0):
    return AssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="What is 2 + 3?",
        rubric=NumericRubricV02(
            expected_value=expected_value,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_delivery(
    *,
    assignment_id="assignment-001",
    item_revision=1,
    prompt="What is 2 + 3?",
):
    return AssessmentDeliveryV01(
        assignment_id=assignment_id,
        decision_id="decision-001",
        assessment_item_id="item-001",
        item_revision=item_revision,
        prompt=prompt,
        selected_action=(
            TeachingActionV01.DIAGNOSTIC_ASSESSMENT
        ),
        assigned_at=NOW,
    )


def issue(repository, *, delivery=None):
    return repository.issue_assignment(
        delivery or make_delivery(),
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
    )


def submit(repository, **overrides):
    args = {
        "assignment_id": "assignment-001",
        "student_id": "student-001",
        "session_id": "session-001",
        "response_text": "5",
    }

    args.update(overrides)

    return repository.submit_numeric_response(**args)


def test_assignment_is_persisted_with_original_revision(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(
        make_item(expected_value=5.0),
        revision=1,
    )

    assessments.save_item(
        make_item(expected_value=7.0),
        revision=2,
    )

    record = issue(assignments)

    loaded = assignments.load_assignment(
        record.assignment_id
    )

    assert loaded.assessment_item_id == "item-001"
    assert loaded.item_revision == 1
    assert loaded.student_id == "student-001"
    assert loaded.session_id == "session-001"
    assert loaded.status == "pending"
    assert loaded.completed_attempt_id is None


def test_submission_creates_attempt_and_completes_assignment(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    attempt = submit(assignments)

    stored_attempt, revision = assessments.load_attempt(
        attempt.attempt_id
    )

    stored_assignment = assignments.load_assignment(
        "assignment-001"
    )

    assert stored_attempt == attempt
    assert revision == 1

    assert attempt.student_id == "student-001"
    assert attempt.session_id == "session-001"
    assert attempt.course_id == "course-001"
    assert attempt.objective_id == "objective-001"
    assert attempt.assessment_item_id == "item-001"

    assert attempt.attempt_id
    assert attempt.source_message_id

    assert attempt.assistance_level is None
    assert attempt.prior_solution_exposure is None
    assert attempt.novelty == "unknown"

    assert stored_assignment.status == "completed"
    assert (
        stored_assignment.completed_attempt_id
        == attempt.attempt_id
    )


def test_duplicate_submission_is_rejected(repositories):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    first = submit(assignments)

    with pytest.raises(
        ValueError,
        match="already been completed",
    ):
        submit(
            assignments,
            response_text="7",
        )

    stored = assignments.load_assignment(
        "assignment-001"
    )

    assert stored.completed_attempt_id == first.attempt_id


def test_another_student_cannot_complete_assignment(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    with pytest.raises(
        ValueError,
        match="student and session",
    ):
        submit(
            assignments,
            student_id="student-002",
        )

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).status == "pending"
    )


def test_another_session_cannot_complete_assignment(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    with pytest.raises(
        ValueError,
        match="student and session",
    ):
        submit(
            assignments,
            session_id="session-002",
        )

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).status == "pending"
    )


def test_modified_delivery_prompt_is_rejected(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    with pytest.raises(
        ValueError,
        match="Delivery prompt",
    ):
        issue(
            assignments,
            delivery=make_delivery(
                prompt="A replacement question."
            ),
        )

    with pytest.raises(
        LookupError,
        match="not found",
    ):
        assignments.load_assignment(
            "assignment-001"
        )


def test_submission_preserves_original_rubric_revision(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(
        make_item(expected_value=5.0),
        revision=1,
    )

    issue(assignments)

    assessments.save_item(
        make_item(expected_value=7.0),
        revision=2,
    )

    attempt = submit(assignments)

    stored_attempt, revision = assessments.load_attempt(
        attempt.attempt_id
    )

    original_item = assessments.load_item(
        stored_attempt.assessment_item_id,
        revision=revision,
    )

    assert revision == 1
    assert original_item.rubric.expected_value == 5.0


def test_invalid_response_does_not_complete_assignment(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    with pytest.raises(
        ValueError,
        match="response_text",
    ):
        submit(
            assignments,
            response_text="   ",
        )

    stored = assignments.load_assignment(
        "assignment-001"
    )

    assert stored.status == "pending"
    assert stored.completed_attempt_id is None


def test_duplicate_assignment_id_is_rejected(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        issue(assignments)

    assert (
        assignments.load_assignment(
            "assignment-001"
        ).status == "pending"
    )


def test_submission_is_visible_after_repository_restart(
    repositories,
):
    assessments, assignments = repositories

    assessments.save_item(make_item(), revision=1)

    issue(assignments)

    attempt = submit(assignments)

    # Construct another repository instance against the same
    # SQLAlchemy sessionmaker to simulate a new service instance.
    restarted = NumericAssignmentRepositoryV01(
        assessments,
        clock=lambda: NOW + timedelta(seconds=3),
    )

    stored = restarted.load_assignment(
        "assignment-001"
    )

    assert stored.status == "completed"
    assert stored.completed_attempt_id == attempt.attempt_id

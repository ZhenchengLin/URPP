"""
13E-4D-3 tests for the read-only Session Observation Source.
"""

from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    StudentAttemptRow,
)
from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)
from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)
from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotServiceV01,
)
from app.services.decision.session_observation_source_v01 import (
    SessionObservationSourceV01,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    environment,
)


def make_source(engine, assistance):
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(factory)

    return SessionObservationSourceV01(
        session_factory=factory,
        session_repository=NumericSessionRecordRepositoryV01(
            assessments
        ),
        assignment_repository=NumericAssignmentRepositoryV01(
            assessments
        ),
        snapshot_service=NumericAttemptProvenanceSnapshotServiceV01(
            session_factory=factory,
            assistance_log=assistance,
        ),
    )


def build(source, *, decision_at, student_id="student-001"):
    return source.build(
        student_id=student_id,
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
        decision_at=decision_at,
    )


def complete_existing_assignment(service, delivery):
    return service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=10),
    )


def test_pending_assignment_is_not_historical_observation(
    environment,
):
    _, engine, assistance, _, _ = environment

    source = make_source(engine, assistance)

    assert build(
        source,
        decision_at=NOW + timedelta(seconds=20),
    ) is None


def test_completed_attempt_is_visible_after_submission(
    environment,
):
    _, engine, assistance, service, delivery = environment

    completed = complete_existing_assignment(
        service,
        delivery,
    )

    source = make_source(engine, assistance)

    result = build(
        source,
        decision_at=NOW + timedelta(minutes=1),
    )

    assert result is not None
    assert result.observed_attempt_count == 1

    assert result.student_id == "student-001"
    assert result.course_id == "course-001"
    assert result.objective_id == "objective-001"

    assert result.observations[0].assignment_id == (
        delivery.assignment_id
    )

    assert result.observations[0].verified_independence is False
    assert result.observations[0].mastery_eligible is False


def test_future_attempt_is_excluded_from_earlier_decision(
    environment,
):
    _, engine, assistance, service, delivery = environment

    complete_existing_assignment(service, delivery)

    source = make_source(engine, assistance)

    with sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )() as db:
        record = db.get(
            StudentAttemptRow,
            service._assignments.load_assignment(
                delivery.assignment_id
            ).completed_attempt_id,
        )

        assert record is not None

        from app.services.assessment.models_v02 import (
            StudentAttemptV02,
        )

        submitted_at = StudentAttemptV02.model_validate(
            record.payload
        ).submitted_at

    # Equal submission/decision times do not qualify
    # as strictly earlier historical observations.
    assert build(
        source,
        decision_at=submitted_at,
    ) is None

    assert build(
        source,
        decision_at=submitted_at + timedelta(microseconds=1),
    ) is not None


def test_wrong_student_scope_is_rejected(
    environment,
):
    _, engine, assistance, _, _ = environment

    source = make_source(engine, assistance)

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        build(
            source,
            student_id="another-student",
            decision_at=NOW + timedelta(minutes=1),
        )


def test_naive_decision_time_is_rejected(
    environment,
):
    _, engine, assistance, _, _ = environment

    source = make_source(engine, assistance)

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build(
            source,
            decision_at=NOW.replace(tzinfo=None),
        )

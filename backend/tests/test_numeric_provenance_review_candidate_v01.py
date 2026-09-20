"""
URPP Implementation 13E-4B.

Tests use real file-backed SQLite and existing services.

Candidates do not authorize reviewers, approve Attempts,
modify scoring, or create eligible mastery evidence.
"""

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

import pytest

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceKindV01,
)

from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotServiceV01,
)

from app.services.assessment.numeric_provenance_review_candidate_v01 import (
    NumericProvenanceReviewCandidateServiceV01,
    ProvenanceSourceChangedV01,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    RecordingAssistancePresenter,
    make_presentation_service,
    open_stack,
    present_hint,
)


@pytest.fixture
def environment(tmp_path):
    """
    Import and reuse the existing SQLite-backed test
    setup, rather than constructing a fake Student State.
    """

    from test_assessment_assistance_log_v01 import (
        environment as assistance_environment,
    )

    # The existing fixture function is wrapped by pytest;
    # call its underlying generator only in this test module.
    generator = assistance_environment.__wrapped__(
        tmp_path
    )

    fixture_value = next(generator)

    try:
        yield fixture_value
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


def make_candidate_service(engine, assistance):
    snapshots = NumericAttemptProvenanceSnapshotServiceV01(
        session_factory=sessionmaker(
            bind=engine,
            expire_on_commit=False,
        ),
        assistance_log=assistance,
    )

    return NumericProvenanceReviewCandidateServiceV01(
        snapshot_service=snapshots,
    )


def complete_attempt(environment, *, response_text="5"):
    _, _, _, numeric_service, delivery = environment

    result = numeric_service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text=response_text,
        as_of=NOW + timedelta(seconds=5),
    )

    assert result.pending is None
    assert result.state.included_evidence_ids == []

    return result


def test_candidate_requires_a_completed_attempt(environment):
    _, engine, assistance, _, delivery = environment

    candidates = make_candidate_service(
        engine,
        assistance,
    )

    with pytest.raises(
        ValueError,
        match="completed Assignment",
    ):
        candidates.create_candidate(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )


def test_hint_and_solution_are_bound_to_real_attempt(
    environment,
):
    _, engine, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation = make_presentation_service(
        environment,
        presenter,
    )

    present_hint(
        presentation,
        delivery,
    )

    presentation.present_assistance(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
        kind=AssessmentAssistanceKindV01.SOLUTION,
        content="The answer is 5.",
    )

    complete_attempt(environment)

    candidates = make_candidate_service(
        engine,
        assistance,
    )

    candidate = candidates.create_candidate(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    snapshot = candidates.require_current_candidate(
        candidate
    )

    assert candidate.attempt_id == snapshot.attempt_id
    assert candidate.reported_hint_count == 1
    assert candidate.reported_solution_count == 1

    assert candidate.review_status == (
        "pending_authorized_review"
    )

    assert candidate.external_assistance_status == (
        "unknown"
    )

    assert candidate.verified_independence is False
    assert candidate.accepted_as_mastery_evidence is False

    assert candidate.source_fingerprint_sha256
    assert len(candidate.source_fingerprint_sha256) == 64


def test_empty_help_log_does_not_imply_independence(
    environment,
):
    _, engine, assistance, _, delivery = environment

    complete_attempt(environment)

    candidate = make_candidate_service(
        engine,
        assistance,
    ).create_candidate(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    assert candidate.reported_hint_count == 0
    assert candidate.reported_solution_count == 0

    assert candidate.external_assistance_status == (
        "unknown"
    )

    assert candidate.verified_independence is False
    assert candidate.accepted_as_mastery_evidence is False


def test_changed_candidate_is_rejected(environment):
    _, engine, assistance, _, delivery = environment

    complete_attempt(environment)

    candidates = make_candidate_service(
        engine,
        assistance,
    )

    original = candidates.create_candidate(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    altered = replace(
        original,
        reported_hint_count=1,
    )

    with pytest.raises(
        ProvenanceSourceChangedV01,
        match="does not match",
    ):
        candidates.require_current_candidate(
            altered
        )


def test_changed_database_source_invalidates_candidate(
    environment,
):
    _, engine, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation = make_presentation_service(
        environment,
        presenter,
    )

    hint = present_hint(
        presentation,
        delivery,
    )

    complete_attempt(environment)

    candidates = make_candidate_service(
        engine,
        assistance,
    )

    original = candidates.create_candidate(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    # Simulate a privileged database change that bypasses
    # the normal append-only Repository interface.
    # This demonstrates change detection, not prevention.
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE assessment_assistance_events_v01
                SET content_sha256 = :replacement
                WHERE event_id = :event_id
                """
            ),
            {
                "replacement": sha256(
                    b"Changed assistance content."
                ).hexdigest(),
                "event_id": hint.event_id,
            },
        )

    with pytest.raises(
        ProvenanceSourceChangedV01,
        match="does not match",
    ):
        candidates.require_current_candidate(
            original
        )


def test_candidate_rechecks_after_database_reopen(
    environment,
):
    path, engine, assistance, _, delivery = environment

    complete_attempt(environment)

    before = make_candidate_service(
        engine,
        assistance,
    ).create_candidate(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    engine.dispose()

    reopened_engine, _, reopened_log, _ = open_stack(
        path,
        initialize=False,
    )

    try:
        candidates = make_candidate_service(
            reopened_engine,
            reopened_log,
        )

        after = candidates.create_candidate(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )

        assert before == after

        snapshot = candidates.require_current_candidate(
            before
        )

        assert snapshot.attempt_id == before.attempt_id

    finally:
        reopened_engine.dispose()

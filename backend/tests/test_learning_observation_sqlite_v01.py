"""
URPP Implementation 13E-4C-1.

SQLite integration tests for Learning Observation.

The tests use the existing temporary SQLite fixture.
No production database or Student State is modified.
"""

from datetime import timedelta

import pytest

from app.services.assessment.learning_observation_shadow_v01 import (
    derive_learning_observation_v01,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    environment,
    make_provenance_snapshot_service,
    open_stack,
    record_hint,
)


def test_hint_observation_survives_sqlite_reopen(
    environment,
):
    """
    Persist Hint and Attempt, reopen SQLite, then derive
    the Observation from the reloaded source records.
    """

    path, engine, assistance, service, delivery = (
        environment
    )

    # Step 1: Persist an application-reported Hint.

    hint = record_hint(
        assistance,
        delivery,
    )

    # Step 2: Submit the actual Numeric Assignment.

    completed = service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert completed.pending is None

    # A correct answer with unknown assistance must
    # not automatically become eligible Mastery Evidence.

    assert completed.state.included_evidence_ids == []

    # Step 3: Read the completed Attempt from SQLite.

    before = make_provenance_snapshot_service(
        engine,
        assistance,
    ).build_snapshot(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    assert before.assistance_events == (hint,)

    # Step 4: Close the original database engine.

    engine.dispose()

    # Step 5: Open the same temporary SQLite database
    # with a new Engine and Repository instances.

    reopened_engine, _, reopened_log, reopened_service = (
        open_stack(
            path,
            initialize=False,
        )
    )

    try:

        after = make_provenance_snapshot_service(
            reopened_engine,
            reopened_log,
        ).build_snapshot(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )

        assert after == before

        # Step 6: Derive the new Learning Observation
        # from records reloaded from SQLite.

        observation = derive_learning_observation_v01(
            after,
        )

        assert observation.assignment_id == (
            delivery.assignment_id
        )

        assert observation.attempt_id == after.attempt_id

        assert observation.source_assistance_event_ids == (
            hint.event_id,
        )

        assert observation.reported_hint_count == 1

        assert observation.reported_solution_count == 0

        assert observation.app_assistance_context == (
            "app_hint_reported"
        )

        # Observation does not approve evidence.

        assert observation.correctness_status == (
            "not_evaluated"
        )

        assert observation.external_help_status == (
            "unknown"
        )

        assert observation.verified_independence is False

        assert observation.mastery_eligible is False

        # The existing Recoverable Session still derives
        # the original conservative Student State.

        restored = reopened_service.resume(
            as_of=NOW + timedelta(seconds=5),
        )

        assert restored.pending is None

        assert restored.state.included_evidence_ids == []

        assert restored.state.state.value == "unknown"

    finally:
        reopened_engine.dispose()


def test_empty_assistance_log_remains_unknown(
    environment,
):
    """
    No application-reported Hint does not prove that
    the student performed independently.
    """

    _, engine, assistance, service, delivery = (
        environment
    )

    service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    snapshot = make_provenance_snapshot_service(
        engine,
        assistance,
    ).build_snapshot(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )

    observation = derive_learning_observation_v01(
        snapshot,
    )

    assert observation.source_assistance_event_ids == ()

    assert observation.reported_hint_count == 0

    assert observation.reported_solution_count == 0

    assert observation.app_assistance_context == (
        "no_app_report"
    )

    assert observation.external_help_status == "unknown"

    assert observation.verified_independence is False

    assert observation.mastery_eligible is False


@pytest.mark.parametrize(
    "student_id,session_id",
    [
        ("other-student", "session-001"),
        ("student-001", "other-session"),
    ],
)
def test_snapshot_rejects_wrong_persisted_scope(
    environment,
    student_id,
    session_id,
):
    """
    The source Snapshot Service must reject a request
    for another Student or Session before the
    Observation is derived.
    """

    _, engine, assistance, service, delivery = (
        environment
    )

    service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    snapshots = make_provenance_snapshot_service(
        engine,
        assistance,
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        snapshots.build_snapshot(
            assignment_id=delivery.assignment_id,
            student_id=student_id,
            session_id=session_id,
        )

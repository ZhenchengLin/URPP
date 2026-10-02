"""
Tests for Implementation 13E-4C-1.

Learning Observation is a read-only derived description.
It cannot certify independent performance or Mastery.
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceKindV01,
    RecordedAssessmentAssistanceV01,
)

from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotV01,
)

from app.services.assessment.learning_observation_shadow_v01 import (
    LearningObservationShadowV01,
    derive_learning_observation_v01,
)


# --------------------------------------------------
# 1. TEST DATA FACTORIES
# --------------------------------------------------

def make_event(
    *,
    event_id="event-001",
    kind=AssessmentAssistanceKindV01.HINT,
):
    """Construct an application-reported assistance event."""

    return RecordedAssessmentAssistanceV01(
        event_id=event_id,
        assignment_id="assignment-001",
        student_id="student-001",
        session_id="session-001",
        kind=kind,
        content_sha256="0" * 64,
        occurred_at=datetime(
            2026,
            1,
            1,
            tzinfo=timezone.utc,
        ),
    )


def make_snapshot(*, events=()):
    """Construct a completed Attempt Provenance Snapshot."""

    return NumericAttemptProvenanceSnapshotV01(
        assignment_id="assignment-001",
        attempt_id="attempt-001",
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
        assessment_item_id="item-001",
        item_revision=1,
        response_text="5",
        stored_assistance_level=None,
        stored_prior_solution_exposure=None,
        assistance_events=events,
        assistance_report_status=(
            "application_reported"
            if events
            else "no_application_report"
        ),
    )


def assert_not_mastery_evidence(observation):
    """Check the Observation's conservative evidence boundary."""

    assert observation.correctness_status == "not_evaluated"
    assert observation.external_help_status == "unknown"
    assert observation.verified_independence is False
    assert observation.mastery_eligible is False


# --------------------------------------------------
# 2. EMPTY ASSISTANCE LOG
# --------------------------------------------------

def test_empty_log_does_not_establish_independence():

    snapshot = make_snapshot()

    observation = derive_learning_observation_v01(
        snapshot,
    )

    assert isinstance(
        observation,
        LearningObservationShadowV01,
    )

    assert observation.assignment_id == "assignment-001"
    assert observation.attempt_id == "attempt-001"

    assert observation.source_assistance_event_ids == ()

    assert observation.reported_hint_count == 0
    assert observation.reported_solution_count == 0

    assert observation.app_assistance_context == "no_app_report"

    assert_not_mastery_evidence(observation)


# --------------------------------------------------
# 3. HINT
# --------------------------------------------------

def test_reported_hint_is_recorded_without_mastery_inference():

    snapshot = make_snapshot(
        events=(make_event(),),
    )

    observation = derive_learning_observation_v01(
        snapshot,
    )

    assert observation.source_assistance_event_ids == (
        "event-001",
    )

    assert observation.reported_hint_count == 1
    assert observation.reported_solution_count == 0

    assert observation.app_assistance_context == (
        "app_hint_reported"
    )

    assert_not_mastery_evidence(observation)


# --------------------------------------------------
# 4. SOLUTION
# --------------------------------------------------

def test_reported_solution_is_distinguished_from_hint():

    snapshot = make_snapshot(
        events=(
            make_event(
                kind=AssessmentAssistanceKindV01.SOLUTION,
            ),
        ),
    )

    observation = derive_learning_observation_v01(
        snapshot,
    )

    assert observation.reported_hint_count == 0
    assert observation.reported_solution_count == 1

    assert observation.app_assistance_context == (
        "app_solution_reported"
    )

    assert_not_mastery_evidence(observation)


# --------------------------------------------------
# 5. MIXED ASSISTANCE
# --------------------------------------------------

def test_hint_and_solution_counts_are_preserved():

    hint = make_event(
        event_id="event-002",
        kind=AssessmentAssistanceKindV01.HINT,
    )

    solution = make_event(
        event_id="event-001",
        kind=AssessmentAssistanceKindV01.SOLUTION,
    )

    snapshot = make_snapshot(
        events=(hint, solution),
    )

    observation = derive_learning_observation_v01(
        snapshot,
    )

    assert observation.reported_hint_count == 1
    assert observation.reported_solution_count == 1

    assert observation.source_assistance_event_ids == (
        "event-001",
        "event-002",
    )

    assert observation.app_assistance_context == (
        "app_solution_reported"
    )

    assert_not_mastery_evidence(observation)


# --------------------------------------------------
# 6. ASSIGNMENT SCOPE
# --------------------------------------------------

@pytest.mark.parametrize(
    "field,wrong_value",
    [
        ("assignment_id", "other-assignment"),
        ("student_id", "other-student"),
        ("session_id", "other-session"),
    ],
)
def test_assistance_event_must_match_attempt_scope(
    field,
    wrong_value,
):

    event = replace(
        make_event(),
        **{field: wrong_value},
    )

    snapshot = make_snapshot(
        events=(event,),
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):
        derive_learning_observation_v01(snapshot)


# --------------------------------------------------
# 7. DUPLICATE EVENT IDS
# --------------------------------------------------

def test_duplicate_assistance_event_ids_are_rejected():

    first = make_event()

    second = make_event(
        kind=AssessmentAssistanceKindV01.SOLUTION,
    )

    snapshot = make_snapshot(
        events=(first, second),
    )

    with pytest.raises(
        ValueError,
        match="Duplicate Assistance Event IDs",
    ):
        derive_learning_observation_v01(snapshot)


# --------------------------------------------------
# 8. REPORT STATUS CONSISTENCY
# --------------------------------------------------

def test_assistance_report_status_must_match_events():

    snapshot = replace(
        make_snapshot(
            events=(make_event(),),
        ),
        assistance_report_status="no_application_report",
    )

    with pytest.raises(
        ValueError,
        match="Assistance report status",
    ):
        derive_learning_observation_v01(snapshot)


# --------------------------------------------------
# 9. SOURCE VALIDATION
# --------------------------------------------------

def test_unrecognized_assistance_source_is_rejected():

    event = replace(
        make_event(),
        source="unverified_external_source",
    )

    snapshot = make_snapshot(
        events=(event,),
    )

    with pytest.raises(
        ValueError,
        match="Unsupported Assistance Event source",
    ):
        derive_learning_observation_v01(snapshot)


# --------------------------------------------------
# 10. DETERMINISTIC DERIVATION
# --------------------------------------------------

def test_same_snapshot_produces_same_observation():

    snapshot = make_snapshot(
        events=(make_event(),),
    )

    first = derive_learning_observation_v01(snapshot)

    second = derive_learning_observation_v01(snapshot)

    assert first == second

    assert_not_mastery_evidence(first)


# --------------------------------------------------
# 11. TYPE VALIDATION
# --------------------------------------------------

def test_non_snapshot_input_is_rejected():

    with pytest.raises(
        TypeError,
        match="NumericAttemptProvenanceSnapshotV01",
    ):
        derive_learning_observation_v01(
            {"assignment_id": "assignment-001"},
        )

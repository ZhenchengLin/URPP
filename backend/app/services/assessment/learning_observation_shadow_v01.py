"""
URPP Implementation 13E-4C-1.

Read-only Learning Observation derived from a
Numeric Attempt Provenance Snapshot.

An Observation is not approved Mastery Evidence.
"""

from dataclasses import dataclass
from typing import Literal

from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotV01,
)


OBSERVATION_POLICY_VERSION = "learning-observation-shadow-v0.1"


@dataclass(frozen=True)
class LearningObservationShadowV01:
    """A description of recorded learning activity."""

    assignment_id: str
    attempt_id: str

    student_id: str
    course_id: str
    objective_id: str
    session_id: str

    assessment_item_id: str
    item_revision: int

    source_assistance_event_ids: tuple[str, ...]

    reported_hint_count: int
    reported_solution_count: int

    app_assistance_context: Literal[
        "no_app_report",
        "app_hint_reported",
        "app_solution_reported",
    ]

    correctness_status: Literal["not_evaluated"] = "not_evaluated"
    external_help_status: Literal["unknown"] = "unknown"

    verified_independence: bool = False
    mastery_eligible: bool = False

    derivation_version: str = OBSERVATION_POLICY_VERSION


def derive_learning_observation_v01(
    snapshot: NumericAttemptProvenanceSnapshotV01,
) -> LearningObservationShadowV01:
    """
    Describe persisted learning activity without inferring
    correctness, external assistance, or independent mastery.
    """

    if not isinstance(
        snapshot,
        NumericAttemptProvenanceSnapshotV01,
    ):
        raise TypeError(
            "NumericAttemptProvenanceSnapshotV01 is required."
        )

    events = snapshot.assistance_events

    event_ids = tuple(sorted(event.event_id for event in events))

    if len(event_ids) != len(set(event_ids)):
        raise ValueError("Duplicate Assistance Event IDs.")

    for event in events:
        if (
            event.assignment_id != snapshot.assignment_id
            or event.student_id != snapshot.student_id
            or event.session_id != snapshot.session_id
        ):
            raise ValueError(
                "Assistance Event scope does not match Attempt."
            )

        if event.source != "application_reported":
            raise ValueError(
                "Unsupported Assistance Event source."
            )

    kinds = tuple(event.kind.value for event in events)

    if any(kind not in {"hint", "solution"} for kind in kinds):
        raise ValueError(
            "Unsupported Assistance Event kind."
        )

    expected_status = (
        "application_reported"
        if events
        else "no_application_report"
    )

    if snapshot.assistance_report_status != expected_status:
        raise ValueError(
            "Assistance report status does not match events."
        )

    hint_count = kinds.count("hint")
    solution_count = kinds.count("solution")

    if solution_count:
        context = "app_solution_reported"
    elif hint_count:
        context = "app_hint_reported"
    else:
        context = "no_app_report"

    return LearningObservationShadowV01(
        assignment_id=snapshot.assignment_id,
        attempt_id=snapshot.attempt_id,
        student_id=snapshot.student_id,
        course_id=snapshot.course_id,
        objective_id=snapshot.objective_id,
        session_id=snapshot.session_id,
        assessment_item_id=snapshot.assessment_item_id,
        item_revision=snapshot.item_revision,
        source_assistance_event_ids=event_ids,
        reported_hint_count=hint_count,
        reported_solution_count=solution_count,
        app_assistance_context=context,
    )

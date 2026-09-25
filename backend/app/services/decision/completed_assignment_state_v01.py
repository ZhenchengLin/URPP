"""
URPP Design 01D — Completed Assignment State Service V0.1.

Reconstruct Student State from completed, persisted numeric
assessment assignments.

The service verifies the stored assignment-to-attempt link
before using the existing numeric scoring and state engine.

This is an internal consistency boundary, not authentication.
It does not prove that a student personally authored a response.
"""

from collections.abc import Sequence
from datetime import datetime

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.services.assessment.persisted_numeric_pipeline_v02 import (
    PersistedNumericAssessmentServiceV02,
)


class CompletedAssignmentStateServiceV01:
    """
    Estimate one student's objective state from completed assignments.

    Every accepted attempt must be the exact completed attempt
    referenced by its persisted assignment.

    Callers cannot provide replacement Assessment Items,
    rubrics, attempts, or EvidenceEvent objects.
    """

    def __init__(
        self,
        *,
        assessment_repository: AssessmentRecordRepositoryV02,
        assignment_repository: NumericAssignmentRepositoryV01,
    ) -> None:

        self._assessment_repository = assessment_repository
        self._assignment_repository = assignment_repository

        self._numeric_pipeline = (
            PersistedNumericAssessmentServiceV02(
                assessment_repository
            )
        )

    def estimate_from_completed_assignments(
        self,
        assignment_ids: Sequence[str],
        *,
        student_id: str,
        session_id: str,
        course_id: str,
        objective_id: str,
        as_of: datetime,
    ) -> ObjectiveStateV02:
        """
        Resolve stored assignment IDs into verified attempt IDs,
        then delegate to the existing state-estimation pipeline.

        The supplied student/session scope must eventually come
        from an authenticated application service.
        """

        if isinstance(assignment_ids, (str, bytes)):
            raise TypeError(
                "assignment_ids must be a sequence, "
                "not a single string."
            )

        if not assignment_ids:
            raise ValueError(
                "At least one completed assignment is required."
            )

        for name, value in (
            ("student_id", student_id),
            ("session_id", session_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{name} must be a non-empty string."
                )

        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or as_of.utcoffset() is None
        ):
            raise ValueError(
                "as_of must be timezone-aware."
            )

        seen_assignments: set[str] = set()
        seen_attempts: set[str] = set()
        attempt_ids: list[str] = []

        for assignment_id in assignment_ids:

            if (
                not isinstance(assignment_id, str)
                or not assignment_id.strip()
            ):
                raise ValueError(
                    "Every assignment ID must be "
                    "a non-empty string."
                )

            if assignment_id in seen_assignments:
                raise ValueError(
                    "Duplicate assignment IDs are not allowed."
                )

            seen_assignments.add(assignment_id)

            assignment = (
                self._assignment_repository.load_assignment(
                    assignment_id
                )
            )

            if (
                assignment.student_id != student_id
                or assignment.session_id != session_id
                or assignment.course_id != course_id
                or assignment.objective_id != objective_id
            ):
                raise ValueError(
                    "Assignment does not match the requested "
                    "student, session, course, and objective."
                )

            if (
                assignment.status != "completed"
                or assignment.completed_attempt_id is None
            ):
                raise ValueError(
                    "Assignment is not completed."
                )

            attempt_id = assignment.completed_attempt_id

            if attempt_id in seen_attempts:
                raise ValueError(
                    "The same attempt cannot satisfy "
                    "multiple assignments."
                )

            attempt, item_revision = (
                self._assessment_repository.load_attempt(
                    attempt_id
                )
            )

            if (
                attempt.attempt_id != attempt_id
                or attempt.student_id != student_id
                or attempt.session_id != session_id
                or attempt.course_id != course_id
                or attempt.objective_id != objective_id
            ):
                raise ValueError(
                    "Completed attempt does not match "
                    "the assignment scope."
                )

            if (
                attempt.assessment_item_id
                != assignment.assessment_item_id
                or item_revision != assignment.item_revision
            ):
                raise ValueError(
                    "Completed attempt does not match "
                    "the assigned item revision."
                )

            expected_response_group = (
                f"assignment-{assignment.assignment_id}"
            )

            if (
                attempt.response_group_id
                != expected_response_group
            ):
                raise ValueError(
                    "Completed attempt is not linked "
                    "to its stored assignment."
                )

            if attempt.submitted_at < assignment.assigned_at:
                raise ValueError(
                    "Completed attempt predates its assignment."
                )

            if (
                assignment.assigned_at > as_of
                or attempt.submitted_at > as_of
            ):
                raise ValueError(
                    "State-estimation time precedes "
                    "the assignment or its submission."
                )

            seen_attempts.add(attempt_id)
            attempt_ids.append(attempt_id)

        return self._numeric_pipeline.estimate_from_attempt_ids(
            attempt_ids,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            as_of=as_of,
        )

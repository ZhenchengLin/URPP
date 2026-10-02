"""
URPP Implementation 13E-4A.

Build a read-only, assignment-bound provenance snapshot
from persisted Numeric Assignment, Student Attempt,
and application-reported Assistance Events.

This is an internal review-input service.

It does not authenticate a reviewer, verify independent
performance, approve evidence, or update Student State.
"""

from dataclasses import dataclass
from typing import Literal

from app.repositories.assessment_records_v02 import (
    StudentAttemptRow,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceLogRepositoryV01,
    RecordedAssessmentAssistanceV01,
)

from app.services.assessment.models_v02 import (
    StudentAttemptV02,
)


@dataclass(frozen=True)
class NumericAttemptProvenanceSnapshotV01:
    """
    Persisted facts assembled for a future review.

    None of the fields below constitutes an authenticated
    reviewer decision or verified independent-performance
    certificate.
    """

    assignment_id: str
    attempt_id: str

    student_id: str
    course_id: str
    objective_id: str
    session_id: str

    assessment_item_id: str
    item_revision: int

    response_text: str

    stored_assistance_level: int | None
    stored_prior_solution_exposure: bool | None

    assistance_events: tuple[
        RecordedAssessmentAssistanceV01,
        ...
    ]

    assistance_report_status: Literal[
        "application_reported",
        "no_application_report",
    ]

    external_assistance_status: Literal[
        "unknown",
    ] = "unknown"

    review_status: Literal[
        "requires_authorized_review",
    ] = "requires_authorized_review"

    verified_independence: bool = False


class NumericAttemptProvenanceSnapshotServiceV01:
    """
    Read a completed Assignment and its actual Attempt.

    The caller must supply the internal student/session
    scope. This is not an authentication boundary.

    No rows are inserted, updated, or deleted.
    """

    def __init__(
        self,
        *,
        session_factory,
        assistance_log: AssessmentAssistanceLogRepositoryV01,
    ) -> None:
        self._session_factory = session_factory
        self._assistance_log = assistance_log

    @staticmethod
    def _require_id(
        value: str,
        name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{name} must be a nonempty string."
            )

        return value

    def build_snapshot(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
    ) -> NumericAttemptProvenanceSnapshotV01:

        assignment_id = self._require_id(
            assignment_id,
            "assignment_id",
        )

        student_id = self._require_id(
            student_id,
            "student_id",
        )

        session_id = self._require_id(
            session_id,
            "session_id",
        )

        with self._session_factory() as session:

            assignment = session.get(
                NumericAssignmentRow,
                assignment_id,
            )

            if assignment is None:
                raise LookupError(
                    "Numeric Assignment was not found."
                )

            if (
                assignment.student_id != student_id
                or assignment.session_id != session_id
            ):
                raise ValueError(
                    "Assignment does not match "
                    "the requested student and session."
                )

            if (
                assignment.status != "completed"
                or assignment.completed_attempt_id is None
            ):
                raise ValueError(
                    "A completed Assignment with a "
                    "stored Attempt is required."
                )

            attempt_row = session.get(
                StudentAttemptRow,
                assignment.completed_attempt_id,
            )

            if attempt_row is None:
                raise ValueError(
                    "Completed Assignment references "
                    "a missing Student Attempt."
                )

            attempt = StudentAttemptV02.model_validate(
                attempt_row.payload
            )

            if (
                attempt.attempt_id
                != assignment.completed_attempt_id
                or attempt.student_id
                != assignment.student_id
                or attempt.course_id
                != assignment.course_id
                or attempt.objective_id
                != assignment.objective_id
                or attempt.session_id
                != assignment.session_id
                or attempt.assessment_item_id
                != assignment.assessment_item_id
                or attempt_row.assessment_item_id
                != assignment.assessment_item_id
                or attempt_row.item_revision
                != assignment.item_revision
            ):
                raise ValueError(
                    "Stored Attempt does not match "
                    "the completed Assignment."
                )

            # Read the persisted facts into local immutable
            # values before closing the database Session.
            facts = {
                "assignment_id": assignment.assignment_id,
                "attempt_id": attempt.attempt_id,
                "student_id": attempt.student_id,
                "course_id": attempt.course_id,
                "objective_id": attempt.objective_id,
                "session_id": attempt.session_id,
                "assessment_item_id": attempt.assessment_item_id,
                "item_revision": assignment.item_revision,
                "response_text": attempt.response_text,
                "stored_assistance_level": (
                    attempt.assistance_level
                ),
                "stored_prior_solution_exposure": (
                    attempt.prior_solution_exposure
                ),
            }

        # The log independently validates Assignment scope.
        # These are application reports, not proof of actual
        # student attention or absence of external help.
        events = (
            self._assistance_log.list_assistance_for_assignment(
                assignment_id=assignment_id,
                student_id=student_id,
                session_id=session_id,
            )
        )

        return NumericAttemptProvenanceSnapshotV01(
            **facts,
            assistance_events=events,
            assistance_report_status=(
                "application_reported"
                if events
                else "no_application_report"
            ),
        )

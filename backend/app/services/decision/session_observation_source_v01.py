"""
URPP 13E-4D-3: Session-scoped historical Observation Source.

This is a read-only internal service, not an authentication
or authorization boundary.

The caller must already be authorized to access the
specified Student and Session.

No correctness, independent-work or mastery claims are
derived from application assistance records.
"""

from datetime import datetime

from app.repositories.assessment_records_v02 import (
    StudentAttemptRow,
)
from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)
from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)
from app.services.assessment.learning_observation_shadow_v01 import (
    derive_learning_observation_v01,
)
from app.services.assessment.models_v02 import (
    StudentAttemptV02,
)
from app.services.assessment.numeric_attempt_provenance_snapshot_v01 import (
    NumericAttemptProvenanceSnapshotServiceV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)


class SessionObservationSourceV01:
    """
    Build historical observations from one persisted session.

    All included attempts must have been submitted strictly
    before the supplied decision time.

    Returns None when there is no eligible history.

    Storage corruption and scope violations are errors,
    not evidence that the student has no prior activity.
    """

    VERSION = "session-observation-source-v0.1"

    def __init__(
        self,
        *,
        session_factory,
        session_repository: NumericSessionRecordRepositoryV01,
        assignment_repository: NumericAssignmentRepositoryV01,
        snapshot_service: NumericAttemptProvenanceSnapshotServiceV01,
    ) -> None:
        self._session_factory = session_factory
        self._sessions = session_repository
        self._assignments = assignment_repository
        self._snapshots = snapshot_service

    @staticmethod
    def _require_time(value: datetime) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "decision_at must be timezone-aware."
            )

        return value

    def require_session_scope(
        self,
        *,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
        decision_at: datetime,
    ) -> None:
        """
        Validate that the stored Session matches the supplied
        internal scope before optional Observation retrieval.

        This validates stored data ownership, not external
        caller authentication or access permissions.
        """
        decision_at = self._require_time(decision_at)

        stored_session = self._sessions.load(
            session_id=session_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        if decision_at < stored_session.started_at:
            raise ValueError(
                "Decision time predates the stored Session."
            )

    def build(
        self,
        *,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
        decision_at: datetime,
    ) -> TeachingObservationContextV01 | None:
        """
        Read completed attempts within the requested scope.

        The decision time is supplied by the authorized
        application caller, not inferred from database
        read time or Assignment issue order.
        """

        self.require_session_scope(
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            session_id=session_id,
            decision_at=decision_at,
        )

        assignment_ids = self._sessions.list_assignment_ids(
            session_id=session_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        observations = []
        seen_attempt_ids = set()

        for assignment_id in assignment_ids:
            assignment = self._assignments.load_assignment(
                assignment_id
            )

            if (
                assignment.student_id != student_id
                or assignment.course_id != course_id
                or assignment.objective_id != objective_id
                or assignment.session_id != session_id
            ):
                raise ValueError(
                    "Assignment does not match Session scope."
                )

            # An Assignment issued at or after the decision
            # cannot be a historical Attempt for that decision.
            if assignment.assigned_at >= decision_at:
                continue

            if assignment.status == "pending":
                continue

            if (
                assignment.status != "completed"
                or assignment.completed_attempt_id is None
            ):
                raise ValueError(
                    "Invalid completed Assignment state."
                )

            # Read only the Attempt payload needed to establish
            # the historical submission-time boundary.
            with self._session_factory() as db:
                attempt_row = db.get(
                    StudentAttemptRow,
                    assignment.completed_attempt_id,
                )

                if attempt_row is None:
                    raise ValueError(
                        "Completed Assignment references "
                        "a missing Attempt."
                    )

                attempt = StudentAttemptV02.model_validate(
                    attempt_row.payload
                )

                if (
                    attempt_row.attempt_id
                    != assignment.completed_attempt_id
                    or attempt_row.assessment_item_id
                    != assignment.assessment_item_id
                    or attempt_row.item_revision
                    != assignment.item_revision
                    or attempt.attempt_id
                    != assignment.completed_attempt_id
                    or attempt.student_id != student_id
                    or attempt.course_id != course_id
                    or attempt.objective_id != objective_id
                    or attempt.session_id != session_id
                    or attempt.assessment_item_id
                    != assignment.assessment_item_id
                ):
                    raise ValueError(
                        "Stored Attempt does not match "
                        "the completed Assignment."
                    )

                submitted_at = attempt.submitted_at

            if submitted_at < assignment.assigned_at:
                raise ValueError(
                    "Attempt submission predates Assignment."
                )

            # No application assistance from this Attempt
            # is included when the Attempt itself is not
            # historical relative to the decision.
            if submitted_at >= decision_at:
                continue

            if attempt.attempt_id in seen_attempt_ids:
                raise ValueError(
                    "Duplicate Attempt in Session history."
                )

            seen_attempt_ids.add(attempt.attempt_id)

            # Reuse the existing provenance validator.
            # It independently checks the completed Assignment,
            # linked Attempt and application assistance scope.
            snapshot = self._snapshots.build_snapshot(
                assignment_id=assignment_id,
                student_id=student_id,
                session_id=session_id,
            )

            if (
                snapshot.attempt_id != attempt.attempt_id
                or snapshot.student_id != student_id
                or snapshot.course_id != course_id
                or snapshot.objective_id != objective_id
                or snapshot.session_id != session_id
                or snapshot.assignment_id != assignment_id
            ):
                raise ValueError(
                    "Provenance Snapshot scope mismatch."
                )

            # A historical Attempt cannot contain a reported
            # assistance event dated after its submission.
            #
            # Event timestamps are application reports, not
            # immutable proof of when database rows were written.
            for event in snapshot.assistance_events:
                if (
                    event.occurred_at > submitted_at
                    or event.occurred_at >= decision_at
                ):
                    raise ValueError(
                        "Historical assistance event time "
                        "is inconsistent with the Attempt "
                        "or decision boundary."
                    )

            observations.append(
                derive_learning_observation_v01(snapshot)
            )

        if not observations:
            return None

        # Preserve the repository's deterministic ordering,
        # but do not interpret tuple position as recency.
        return TeachingObservationContextV01(
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            observations=tuple(observations),
        )

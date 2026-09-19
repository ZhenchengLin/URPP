"""
URPP Design 01D — Persisted Numeric Teaching Loop V0.1.

Connects the existing teaching-session coordinator to:

1. Database-backed assignment issuance.
2. Database-backed student submission.
3. Completed-assignment verification.
4. Existing numeric scoring and Student State estimation.

This is an INTERNAL, single-process prototype.

The assignment is persisted, but the session coordinator is not.
Authentication, authorization, cross-process session recovery,
and production concurrency handling are not implemented here.
"""

from datetime import datetime

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.services.decision.completed_assignment_state_v01 import (
    CompletedAssignmentStateServiceV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    AssessmentDeliveryV01,
    NumericTeachingSessionV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    TeachingTurnOrchestratorV01,
)


class PersistedNumericTeachingLoopV01:
    """
    Coordinate one student's numeric assessment teaching turns.

    Assignment issuance and submission are delegated to the
    existing database repository.

    Student State is updated only after the stored assignment
    and completed attempt have passed repository-backed checks.
    """

    def __init__(
        self,
        *,
        assessment_repository: AssessmentRecordRepositoryV02,
        assignment_repository: NumericAssignmentRepositoryV01,
        turn_orchestrator: TeachingTurnOrchestratorV01,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
        as_of: datetime,
    ) -> None:

        self._assessment_repository = assessment_repository
        self._assignment_repository = assignment_repository

        self._student_id = student_id
        self._course_id = course_id
        self._objective_id = objective_id
        self._session_id = session_id

        self._teaching_session = NumericTeachingSessionV01(
            repository=assessment_repository,
            turn_orchestrator=turn_orchestrator,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            session_id=session_id,
            as_of=as_of,
        )

        self._completed_state_service = (
            CompletedAssignmentStateServiceV01(
                assessment_repository=assessment_repository,
                assignment_repository=assignment_repository,
            )
        )

        self._completed_assignment_ids: list[str] = []
        self._pending_assignment_id: str | None = None

        # A database transaction can commit before the in-memory
        # coordinator finishes its state update. If that happens,
        # this prototype must stop rather than continue with
        # inconsistent state.
        self._requires_recovery = False

    @property
    def state(self) -> ObjectiveStateV02:
        return self._teaching_session.state

    @property
    def pending_assignment_id(self) -> str | None:
        return self._pending_assignment_id

    @property
    def completed_assignment_ids(self) -> tuple[str, ...]:
        return tuple(self._completed_assignment_ids)

    @property
    def requires_recovery(self) -> bool:
        return self._requires_recovery

    def _ensure_usable(self) -> None:
        if self._requires_recovery:
            raise RuntimeError(
                "Teaching session requires recovery. "
                "Do not continue with stale in-memory state."
            )

    def deliver_numeric_assessment(
        self,
        *,
        assessment_item_id: str,
        item_revision: int,
        decision_id: str,
        requested_at: datetime,
    ) -> AssessmentDeliveryV01:
        """
        Select a teaching action and persist its assignment.

        The session records a pending database assignment only
        after the repository successfully saves it.
        """

        self._ensure_usable()

        if self._pending_assignment_id is not None:
            raise ValueError(
                "Complete the pending assignment "
                "before starting another turn."
            )

        delivery = (
            self._teaching_session.start_structured_numeric_turn(
                assessment_item_id=assessment_item_id,
                item_revision=item_revision,
                decision_id=decision_id,
                requested_at=requested_at,
            )
        )

        try:
            stored = self._assignment_repository.issue_assignment(
                delivery,
                student_id=self._student_id,
                course_id=self._course_id,
                objective_id=self._objective_id,
                session_id=self._session_id,
                require_registered_session=False,
            )
        except Exception:
            # The in-memory teaching coordinator has already
            # created a pending turn. This prototype does not
            # attempt an unsafe partial rollback.
            self._requires_recovery = True
            raise

        if stored.assignment_id != delivery.assignment_id:
            self._requires_recovery = True
            raise RuntimeError(
                "Persisted assignment ID differs "
                "from the delivered assignment."
            )

        self._pending_assignment_id = stored.assignment_id

        return delivery

    def submit_numeric_answer(
        self,
        *,
        assignment_id: str,
        response_text: str,
    ) -> ObjectiveStateV02:
        """
        Persist an answer and update Student State.

        The repository supplies the server-generated attempt ID,
        original assessment revision, and submission timestamp.

        The completed-assignment service checks the database
        association before the in-memory session accepts the
        stored attempt.
        """

        self._ensure_usable()

        pending_id = self._pending_assignment_id

        if pending_id is None:
            raise ValueError(
                "No numeric assignment is awaiting an answer."
            )

        if assignment_id != pending_id:
            raise ValueError(
                "Assignment ID does not match "
                "the active teaching turn."
            )

        # Submission writes the Attempt and marks the Assignment
        # completed in one repository-managed transaction.
        #
        # Ordinary validation failures leave the pending turn
        # available for another submission attempt.
        attempt = (
            self._assignment_repository.submit_numeric_response(
                assignment_id=assignment_id,
                student_id=self._student_id,
                session_id=self._session_id,
                response_text=response_text,
            )
        )

        next_assignment_ids = [
            *self._completed_assignment_ids,
            assignment_id,
        ]

        try:
            # First verify the persisted assignment-to-attempt
            # association, then independently reconstruct state
            # using the existing scoring and state engine.
            persisted_state = (
                self._completed_state_service
                .estimate_from_completed_assignments(
                    next_assignment_ids,
                    student_id=self._student_id,
                    session_id=self._session_id,
                    course_id=self._course_id,
                    objective_id=self._objective_id,
                    as_of=attempt.submitted_at,
                )
            )

            # Advance the existing in-memory teaching session.
            # It must accept the exact stored attempt and the
            # assignment ID from the pending delivery.
            session_state = (
                self._teaching_session.accept_stored_attempt(
                    attempt_id=attempt.attempt_id,
                    assignment_id=assignment_id,
                    as_of=attempt.submitted_at,
                )
            )

            if (
                persisted_state.model_dump(mode="json")
                != session_state.model_dump(mode="json")
            ):
                raise RuntimeError(
                    "Persisted and in-memory Student State "
                    "estimates do not match."
                )

        except Exception:
            # Submission may already be committed. Without
            # durable session-recovery support, continuing
            # could reuse a completed assignment incorrectly.
            self._requires_recovery = True
            raise

        self._completed_assignment_ids = next_assignment_ids
        self._pending_assignment_id = None

        return session_state

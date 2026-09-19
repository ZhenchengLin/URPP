"""
URPP Design 01D — Recoverable Numeric Teaching Session V0.1.

Rebuilds session progress and Student State from persisted
Session, Assignment, and Attempt records.

This service deliberately does not depend on the in-memory
Pending Assessment state of NumericTeachingSessionV01.

It reuses the existing Decision Engine, structured delivery
contract, Assignment Repository, and Student State Engine.

Limitations:
- No authentication or authorization.
- No HTTP endpoint.
- No cross-process concurrency guarantee.
- No database migration or production deployment.
- Session registration and assignment issuance are separate
  database transactions.
"""

from dataclasses import dataclass
from datetime import datetime
from secrets import token_urlsafe

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
    StoredNumericAssignmentV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.decision.completed_assignment_state_v01 import (
    CompletedAssignmentStateServiceV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    AssessmentDeliveryV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
    TeachingTurnOrchestratorV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


@dataclass(frozen=True)
class PendingNumericDeliveryViewV01:
    """
    Recoverable view of the question awaiting a response.

    A recovered pending assignment may be displayed again.
    This view does not claim that a browser previously displayed it.
    """

    assignment_id: str
    decision_id: str
    assessment_item_id: str
    item_revision: int
    prompt: str
    assigned_at: datetime


@dataclass(frozen=True)
class RecoveredNumericSessionV01:
    state: ObjectiveStateV02
    pending: PendingNumericDeliveryViewV01 | None
    completed_assignment_ids: tuple[str, ...]


class RecoverableNumericSessionServiceV01:
    """
    Coordinate numeric teaching using durable records.

    A fresh instance can resume an existing session because
    its authoritative progress comes from the database.
    """

    def __init__(
        self,
        *,
        assessment_repository: AssessmentRecordRepositoryV02,
        assignment_repository: NumericAssignmentRepositoryV01,
        session_repository: NumericSessionRecordRepositoryV01,
        turn_orchestrator: TeachingTurnOrchestratorV01,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
    ) -> None:

        self._assessments = assessment_repository
        self._assignments = assignment_repository
        self._sessions = session_repository
        self._turn_orchestrator = turn_orchestrator

        self._student_id = student_id
        self._course_id = course_id
        self._objective_id = objective_id
        self._session_id = session_id

        self._completed_state_service = (
            CompletedAssignmentStateServiceV01(
                assessment_repository=assessment_repository,
                assignment_repository=assignment_repository,
            )
        )

    def start(
        self,
        *,
        started_at: datetime,
    ) -> RecoveredNumericSessionV01:
        """
        Register the session, then construct its current progress.

        Repeating this call with the same identity and scope
        resumes the existing session rather than resetting it.
        """

        self._sessions.register(
            session_id=self._session_id,
            student_id=self._student_id,
            course_id=self._course_id,
            objective_id=self._objective_id,
            started_at=started_at,
        )

        return self.resume(as_of=started_at)

    def resume(
        self,
        *,
        as_of: datetime,
    ) -> RecoveredNumericSessionV01:
        """
        Reconstruct progress from all assignments in this session.

        Completed assignments are passed through the existing
        persisted-assignment validation and state-estimation service.

        A pending assignment is reconstructed from its original
        stored assessment-item revision.
        """

        if (
            not isinstance(as_of, datetime)
            or as_of.tzinfo is None
            or as_of.utcoffset() is None
        ):
            raise ValueError(
                "as_of must be timezone-aware."
            )

        stored_session = self._sessions.load(
            session_id=self._session_id,
            student_id=self._student_id,
            course_id=self._course_id,
            objective_id=self._objective_id,
        )

        if as_of < stored_session.started_at:
            raise ValueError(
                "Recovery time predates the stored session."
            )

        assignment_ids = self._sessions.list_assignment_ids(
            session_id=self._session_id,
            student_id=self._student_id,
            course_id=self._course_id,
            objective_id=self._objective_id,
        )

        completed: list[str] = []
        pending: list[StoredNumericAssignmentV01] = []

        for assignment_id in assignment_ids:
            record = self._assignments.load_assignment(
                assignment_id
            )

            if (
                record.student_id != self._student_id
                or record.course_id != self._course_id
                or record.objective_id != self._objective_id
                or record.session_id != self._session_id
            ):
                raise ValueError(
                    "Stored assignment does not match "
                    "this teaching session."
                )

            if record.assigned_at > as_of:
                raise ValueError(
                    "Recovery time predates a stored assignment."
                )

            if record.status == "pending":
                pending.append(record)

            elif record.status == "completed":
                completed.append(record.assignment_id)

            else:
                raise ValueError(
                    "Stored assignment has an invalid status."
                )

        if len(pending) > 1:
            raise RuntimeError(
                "Multiple pending assignments require "
                "manual session reconciliation."
            )

        if completed:
            state = (
                self._completed_state_service
                .estimate_from_completed_assignments(
                    completed,
                    student_id=self._student_id,
                    session_id=self._session_id,
                    course_id=self._course_id,
                    objective_id=self._objective_id,
                    as_of=as_of,
                )
            )

        else:
            state = estimate_objective_state(
                [],
                student_id=self._student_id,
                course_id=self._course_id,
                objective_id=self._objective_id,
                as_of=as_of,
            )

        pending_view = None

        if pending:
            record = pending[0]

            item = self._assessments.load_item(
                record.assessment_item_id,
                revision=record.item_revision,
            )

            if not isinstance(item, AssessmentItemV02):
                raise TypeError(
                    "Pending assignment is not a numeric item."
                )

            pending_view = PendingNumericDeliveryViewV01(
                assignment_id=record.assignment_id,
                decision_id=record.decision_id,
                assessment_item_id=record.assessment_item_id,
                item_revision=record.item_revision,
                prompt=item.prompt,
                assigned_at=record.assigned_at,
            )

        return RecoveredNumericSessionV01(
            state=state,
            pending=pending_view,
            completed_assignment_ids=tuple(completed),
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
        Run the existing teaching decision flow and persist
        a structured assignment.

        Only the stored assessment prompt is returned as the
        actual question; Agent-generated free text cannot
        replace the item's saved prompt.
        """

        progress = self.resume(
            as_of=requested_at
        )

        if progress.pending is not None:
            raise ValueError(
                "Complete the pending assignment "
                "before starting another turn."
            )

        existing_ids = self._sessions.list_assignment_ids(
            session_id=self._session_id,
            student_id=self._student_id,
            course_id=self._course_id,
            objective_id=self._objective_id,
        )

        for existing_id in existing_ids:
            existing = self._assignments.load_assignment(
                existing_id
            )

            if existing.decision_id == decision_id:
                raise ValueError(
                    "Decision ID has already been used "
                    "in this session."
                )

        item = self._assessments.load_item(
            assessment_item_id,
            revision=item_revision,
        )

        if not isinstance(item, AssessmentItemV02):
            raise TypeError(
                "Only numeric assessment items are supported."
            )

        if (
            item.course_id != self._course_id
            or item.objective_id != self._objective_id
        ):
            raise ValueError(
                "Assessment item does not match "
                "the session scope."
            )

        if not item.alignment_verified:
            raise ValueError(
                "Assessment objective alignment is not verified."
            )

        turn = self._turn_orchestrator.run_turn(
            progress.state,
            decision_id=decision_id,
            requested_at=requested_at,
        )

        if (
            turn.agent_kind != "assessment"
            or turn.decision.selected_action
            not in ASSESSMENT_ACTIONS
        ):
            raise ValueError(
                "Teaching decision did not select "
                "an assessment action."
            )

        delivery = AssessmentDeliveryV01(
            assignment_id=token_urlsafe(24),
            decision_id=decision_id,
            assessment_item_id=assessment_item_id,
            item_revision=item_revision,
            prompt=item.prompt,
            selected_action=turn.decision.selected_action,
            assigned_at=requested_at,
        )

        stored = self._assignments.issue_assignment(
            delivery,
            student_id=self._student_id,
            course_id=self._course_id,
            objective_id=self._objective_id,
            session_id=self._session_id,
            require_registered_session=True,
        )

        if stored.assignment_id != delivery.assignment_id:
            raise RuntimeError(
                "Persisted assignment ID mismatch."
            )

        return delivery

    def submit_numeric_answer(
        self,
        *,
        assignment_id: str,
        response_text: str,
        as_of: datetime,
    ) -> RecoveredNumericSessionV01:
        """
        Submit an answer, then reconstruct progress from the database.

        If the database commit succeeds but reconstruction fails,
        a new service instance can call resume() to recover.
        """

        progress = self.resume(as_of=as_of)

        if progress.pending is None:
            raise ValueError(
                "No numeric assignment is awaiting an answer."
            )

        if progress.pending.assignment_id != assignment_id:
            raise ValueError(
                "Assignment ID does not match "
                "the pending assessment."
            )

        attempt = self._assignments.submit_numeric_response(
            assignment_id=assignment_id,
            student_id=self._student_id,
            session_id=self._session_id,
            response_text=response_text,
        )

        if as_of < attempt.submitted_at:
            raise ValueError(
                "State-estimation time precedes submission. "
                "The submission may already be committed; "
                "resume the session using a later as_of time."
            )

        return self.resume(as_of=as_of)

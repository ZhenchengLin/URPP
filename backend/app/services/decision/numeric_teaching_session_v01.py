"""
URPP Design 01D — Bound Numeric Teaching Session V0.1.

Coordinates an internal numeric-assessment teaching loop.

A server-selected, stored assessment item is bound to the
delivered teaching turn. A subsequent stored attempt must match
the selected item revision and the active student/session scope.

This implementation is in-memory session coordination.

It does NOT authenticate users, guarantee that a browser
displayed the prompt, prove that the student personally supplied
an answer, or provide transactional session persistence.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.assessment.persisted_numeric_pipeline_v02 import (
    PersistedNumericAssessmentServiceV02,
)

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
    TeachingTurnOrchestratorV01,
    TeachingTurnResultV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


@dataclass(frozen=True)
class PendingNumericAssessmentV01:
    """
    One assessment assignment awaiting a stored attempt.

    This record belongs to the server-side session coordinator.
    It is not a client authorization token.
    """

    decision_id: str
    assessment_item_id: str
    item_revision: int
    requested_at: datetime


class NumericTeachingSessionV01:
    """
    Run numeric assessment turns against stored assessment records.

    A successful turn proceeds through:

    1. Select an existing item and revision.
    2. Make a policy-checked teaching decision.
    3. Confirm that the Assessment Agent delivered the stored prompt.
    4. Accept a stored attempt matching the pending assignment.
    5. Recompute Student State from accepted attempt IDs.

    Professor-only turns and open-response review workflows are
    outside this initial session coordinator.
    """

    def __init__(
        self,
        *,
        repository: AssessmentRecordRepositoryV02,
        turn_orchestrator: TeachingTurnOrchestratorV01,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
        as_of: datetime,
    ) -> None:

        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(
                "session_id must be a non-empty string."
            )

        self._repository = repository
        self._turn_orchestrator = turn_orchestrator

        self._student_id = student_id
        self._course_id = course_id
        self._objective_id = objective_id
        self._session_id = session_id

        self._numeric_service = (
            PersistedNumericAssessmentServiceV02(repository)
        )

        self._state = estimate_objective_state(
            [],
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            as_of=as_of,
        )

        self._accepted_attempt_ids: list[str] = []
        self._used_decision_ids: set[str] = set()

        self._pending: PendingNumericAssessmentV01 | None = None

    @property
    def state(self) -> ObjectiveStateV02:
        """
        Return a copy of the current calculated Student State.

        Callers cannot replace the coordinator's internal state
        by modifying the returned object.
        """

        return self._state.model_copy(deep=True)

    @property
    def has_pending_assessment(self) -> bool:
        return self._pending is not None

    def start_numeric_turn(
        self,
        *,
        assessment_item_id: str,
        item_revision: int,
        decision_id: str,
        requested_at: datetime,
    ) -> TeachingTurnResultV01:
        """
        Deliver a server-selected, previously stored numeric item.

        This initial implementation requires the Assessment Agent
        to return the exact stored prompt as its teaching content.

        Future structured Agent output can carry an assignment ID
        instead of relying on an exact prompt comparison.
        """

        if self._pending is not None:
            raise ValueError(
                "Complete the pending assessment before "
                "starting another numeric turn."
            )

        if decision_id in self._used_decision_ids:
            raise ValueError(
                "Decision ID has already been used in this session."
            )

        if (
            requested_at.tzinfo is None
            or requested_at.utcoffset() is None
        ):
            raise ValueError(
                "requested_at must be timezone-aware."
            )

        if requested_at < self._state.as_of:
            raise ValueError(
                "A teaching turn cannot precede "
                "the current Student State."
            )

        item = self._repository.load_item(
            assessment_item_id,
            revision=item_revision,
        )

        if not isinstance(item, AssessmentItemV02):
            raise TypeError(
                "This session supports numeric assessment items only."
            )

        if (
            item.course_id != self._course_id
            or item.objective_id != self._objective_id
        ):
            raise ValueError(
                "Selected assessment item does not match "
                "this teaching session."
            )

        if not item.alignment_verified:
            raise ValueError(
                "Selected assessment item lacks verified "
                "objective alignment."
            )

        turn = self._turn_orchestrator.run_turn(
            self._state.model_copy(deep=True),
            decision_id=decision_id,
            requested_at=requested_at,
        )

        if turn.decision.selected_action not in ASSESSMENT_ACTIONS:
            raise ValueError(
                "Decision did not select an assessment action."
            )

        if turn.agent_kind != "assessment":
            raise ValueError(
                "Assessment action was not routed "
                "to the Assessment Agent."
            )

        if turn.content != item.prompt:
            raise ValueError(
                "Assessment Agent output does not match "
                "the stored assessment prompt."
            )

        self._pending = PendingNumericAssessmentV01(
            decision_id=decision_id,
            assessment_item_id=assessment_item_id,
            item_revision=item_revision,
            requested_at=requested_at,
        )

        self._used_decision_ids.add(decision_id)

        return turn

    def accept_stored_attempt(
        self,
        *,
        attempt_id: str,
        as_of: datetime,
    ) -> ObjectiveStateV02:
        """
        Accept one stored attempt for the pending assessment.

        The Attempt is loaded from the repository, not supplied
        as an arbitrary replacement object by this method.
        """

        pending = self._pending

        if pending is None:
            raise ValueError(
                "No assessment is awaiting a student attempt."
            )

        if attempt_id in self._accepted_attempt_ids:
            raise ValueError(
                "Attempt ID has already been accepted "
                "in this teaching session."
            )

        attempt, item_revision = (
            self._repository.load_attempt(attempt_id)
        )

        if (
            attempt.student_id != self._student_id
            or attempt.course_id != self._course_id
            or attempt.objective_id != self._objective_id
            or attempt.session_id != self._session_id
        ):
            raise ValueError(
                "Stored attempt does not match "
                "the active teaching session."
            )

        if (
            attempt.assessment_item_id
            != pending.assessment_item_id
            or item_revision != pending.item_revision
        ):
            raise ValueError(
                "Stored attempt does not match "
                "the pending assessment item and revision."
            )

        if attempt.submitted_at < pending.requested_at:
            raise ValueError(
                "Attempt predates the pending assessment turn."
            )

        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError(
                "as_of must be timezone-aware."
            )

        if (
            as_of < attempt.submitted_at
            or as_of < self._state.as_of
        ):
            raise ValueError(
                "State-estimation time cannot precede "
                "the accepted attempt or current state."
            )

        next_attempt_ids = [
            *self._accepted_attempt_ids,
            attempt_id,
        ]

        next_state = (
            self._numeric_service.estimate_from_attempt_ids(
                next_attempt_ids,
                student_id=self._student_id,
                course_id=self._course_id,
                objective_id=self._objective_id,
                as_of=as_of,
            )
        )

        # Update the session only after the repository-backed
        # scoring and state-estimation process succeeds.
        self._accepted_attempt_ids = next_attempt_ids
        self._state = next_state
        self._pending = None

        return self._state.model_copy(deep=True)

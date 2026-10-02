"""
URPP Implementation 13C-2A.

Adapt a personalized teaching turn to the existing
RecoverableNumericSessionServiceV01 delivery interface.

This module does not duplicate Assignment persistence,
Assessment Item validation, or Student State estimation.
"""

from datetime import datetime

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    REQUEST_ACTION_MAP,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.recoverable_numeric_session_v01 import (
    RecoverableNumericSessionServiceV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
    TeachingTurnResultV01,
)


class PersonalizedNumericSessionTurnAdapterV01:
    """
    A compatibility adapter for one requested assessment turn.

    The adapter presents the legacy run_turn signature expected
    by RecoverableNumericSessionServiceV01.

    An explicit student request is bound to this adapter instance.
    For a different request, construct a new adapter and service
    using the same persistent repositories and Session identity.

    The adapter does not persist decision provenance.
    """

    VERSION = "personalized-numeric-session-adapter-v0.1"

    def __init__(
        self,
        *,
        personalized_turn_orchestrator:
            PersonalizedTeachingTurnOrchestratorV01,
        student_request: StudentLearningRequestV01 | None = None,
    ) -> None:
        self._orchestrator = personalized_turn_orchestrator

        self._student_request = student_request

        self._explicit_request_used = False

        if student_request is not None:
            try:
                requested_action = REQUEST_ACTION_MAP[
                    student_request.request_kind
                ]
            except KeyError as exc:
                raise ValueError(
                    "Unsupported student learning request."
                ) from exc

            if requested_action not in ASSESSMENT_ACTIONS:
                raise ValueError(
                    "Numeric assessment delivery requires "
                    "an assessment-related student request."
                )

    def run_turn(
        self,
        objective_state: ObjectiveStateV02,
        *,
        decision_id: str,
        requested_at: datetime,
    ) -> TeachingTurnResultV01:
        """
        Run the personalized decision exactly once and return
        the legacy teaching-turn result shape.

        The underlying Recoverable Session remains responsible
        for checking the Assessment Item and issuing Assignment.
        """

        request = self._student_request

        if request is not None:
            if self._explicit_request_used:
                raise RuntimeError(
                    "This explicit student request has already "
                    "been used for a teaching decision. "
                    "Construct a new adapter for another turn."
                )

            if request.objective_id != objective_state.objective_id:
                raise ValueError(
                    "Student request does not match "
                    "the current Objective."
                )

            # The existing recoverable delivery method obtains
            # an Objective State snapshot as_of requested_at.
            #
            # Requiring the same request timestamp keeps this
            # one-turn adapter compatible with the existing
            # PersonalizedDecisionContextV01 time validation.
            if request.requested_at != requested_at:
                raise ValueError(
                    "Student request timestamp must match "
                    "the assessment decision timestamp."
                )

            self._explicit_request_used = True

        personalized_turn = self._orchestrator.run_turn(
            objective_state,
            decision_id=decision_id,
            requested_at=requested_at,
            student_request=request,
        )

        selected_action = (
            personalized_turn.decision.decision.selected_action
        )

        if (
            personalized_turn.agent_kind != "assessment"
            or selected_action not in ASSESSMENT_ACTIONS
        ):
            raise ValueError(
                "Personalized teaching decision did not select "
                "an assessment action."
            )

        # The Recoverable Session expects the legacy result
        # contract. We adapt its shape without making another
        # decision or regenerating the teaching content.
        #
        # The personalized decision's selection provenance
        # remains in memory in the personalized turn result.
        # This adapter does not claim that provenance is
        # persisted by the legacy Assignment schema.
        return TeachingTurnResultV01(
            decision=personalized_turn.decision.decision,
            agent_kind=personalized_turn.agent_kind,
            content=personalized_turn.content,
        )


def create_personalized_recoverable_numeric_session_v01(
    *,
    assessment_repository: AssessmentRecordRepositoryV02,
    assignment_repository: NumericAssignmentRepositoryV01,
    session_repository: NumericSessionRecordRepositoryV01,
    personalized_turn_orchestrator:
        PersonalizedTeachingTurnOrchestratorV01,
    student_id: str,
    course_id: str,
    objective_id: str,
    session_id: str,
    student_request: StudentLearningRequestV01 | None = None,
) -> RecoverableNumericSessionServiceV01:
    """
    Construct an existing Recoverable Numeric Session using
    a personalized teaching-turn adapter.

    This function does not register the Session or create
    an Assignment. The caller still uses the existing
    start(), resume(), deliver_numeric_assessment(), and
    submit_numeric_answer() methods.

    Use a new service instance for a new explicit request.
    Repository and Session identities can remain unchanged.
    """

    if (
        student_request is not None
        and student_request.objective_id != objective_id
    ):
        raise ValueError(
            "Student request does not match "
            "the Numeric Session Objective."
        )

    adapter = PersonalizedNumericSessionTurnAdapterV01(
        personalized_turn_orchestrator=(
            personalized_turn_orchestrator
        ),
        student_request=student_request,
    )

    return RecoverableNumericSessionServiceV01(
        assessment_repository=assessment_repository,
        assignment_repository=assignment_repository,
        session_repository=session_repository,
        turn_orchestrator=adapter,
        student_id=student_id,
        course_id=course_id,
        objective_id=objective_id,
        session_id=session_id,
    )

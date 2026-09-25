"""
URPP 13E-4D-3.

Internal opt-in connection between a Session-scoped,
read-only Observation Source and an observed teaching turn.

This component is not an authentication boundary.

The caller must obtain authoritative Objective State and
permission to access the requested Session before calling.

Observation retrieval is optional. A retrieval failure
cannot replace an otherwise successful teaching turn.
"""

from datetime import datetime

from app.domain.learning.state_v02 import (
    ObjectiveStateV02,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.post_turn_shadow_observer_v01 import (
    PostTurnShadowOutcomeV01,
)

from app.services.decision.session_observation_source_v01 import (
    SessionObservationSourceV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestV01,
)


def run_observed_numeric_session_turn_v01(
    *,
    orchestrator: PersonalizedTeachingTurnOrchestratorV01,
    observation_source: SessionObservationSourceV01,
    objective_state: ObjectiveStateV02,
    session_id: str,
    decision_id: str,
    requested_at: datetime,
    student_request: StudentLearningRequestV01 | None = None,
) -> PostTurnShadowOutcomeV01:
    """
    Execute one authoritative teaching turn with optional
    historical Observation.

    This is an internal opt-in entry point. It does not
    register a Session, create an Assignment, save evidence,
    update Student State, or authorize external callers.

    The existing run_turn() and Numeric Session adapters
    remain unchanged.
    """

    if not isinstance(
        orchestrator,
        PersonalizedTeachingTurnOrchestratorV01,
    ):
        raise TypeError(
            "orchestrator must be "
            "PersonalizedTeachingTurnOrchestratorV01."
        )

    if not isinstance(
        observation_source,
        SessionObservationSourceV01,
    ):
        raise TypeError(
            "observation_source must be "
            "SessionObservationSourceV01."
        )

    if not isinstance(
        objective_state,
        ObjectiveStateV02,
    ):
        raise TypeError(
            "objective_state must be ObjectiveStateV02."
        )

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError(
            "session_id must be a nonempty string."
        )

    # Obtain the Observation scope from the authoritative
    # state supplied by the authorized application caller.
    #
    # Never let a separate set of caller-provided Student,
    # Course or Objective IDs select another student's
    # historical records.
    # Session identity and ownership checks are mandatory.
    # They must not be hidden by the optional Observation
    # retrieval failure handler.
    #
    # The calling application still must authenticate and
    # authorize access to the Student and Session.
    observation_source.require_session_scope(
        student_id=objective_state.student_id,
        course_id=objective_state.course_id,
        objective_id=objective_state.objective_id,
        session_id=session_id,
        decision_at=requested_at,
    )

    try:
        observation_context = observation_source.build(
            student_id=objective_state.student_id,
            course_id=objective_state.course_id,
            objective_id=objective_state.objective_id,
            session_id=session_id,
            decision_at=requested_at,
        )

    except Exception:
        # Only optional Observation retrieval is fail-open.
        #
        # Do not place the authoritative teaching call
        # inside this exception handler.
        #
        # A failed read must not be represented as evidence
        # that the student had no previous attempts.
        unavailable_outcome = orchestrator.run_turn_observed(
            objective_state,
            decision_id=decision_id,
            requested_at=requested_at,
            student_request=student_request,
            observation_context=None,
        )

        return PostTurnShadowOutcomeV01(
            completed_turn=unavailable_outcome.completed_turn,
            status="failed",
            report=None,
            failure_code="shadow_evaluation_failed",
        )

    # This call runs the authoritative Decision Engine once
    # and one Teaching Agent. The Observer uses the same
    # Decision Context generated during that call.
    return orchestrator.run_turn_observed(
        objective_state,
        decision_id=decision_id,
        requested_at=requested_at,
        student_request=student_request,
        observation_context=observation_context,
    )

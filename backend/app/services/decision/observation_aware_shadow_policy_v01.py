"""
URPP Implementation 13E-4C-3A.

Observation-aware teaching policy in shadow mode.

The policy evaluates an existing decision and read-only
learning observations. It never selects or executes the
actual teaching action and never changes Student State.
"""

from dataclasses import dataclass
from typing import Literal

from app.services.decision.models_v01 import (
    TeachingActionV01,
)
from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
    PersonalizedDecisionResultV01,
)
from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)


SHADOW_POLICY_VERSION = "observation-aware-shadow-policy-v0.1"

ShadowStatusV01 = Literal[
    "explicit_request_preserved",
    "no_app_help_candidate",
    "candidate_not_allowed",
    "candidate_matches_existing",
    "candidate_differs_from_existing",
]


@dataclass(frozen=True)
class ObservationAwareShadowReportV01:
    """A review-only report, never an executable decision."""

    decision_id: str

    existing_action: TeachingActionV01

    candidate_action: TeachingActionV01 | None

    status: ShadowStatusV01

    source_attempt_ids: tuple[str, ...]

    observed_attempt_count: int

    app_hint_attempt_count: int

    app_solution_attempt_count: int

    no_app_report_attempt_count: int

    would_differ_from_existing: bool

    # The observation history has no verified chronology.
    history_order_verified: bool = False

    # A shadow candidate is never permission to execute.
    action_execution_authorized: bool = False

    # Observation alone cannot verify independence/mastery.
    verified_independence: bool = False

    mastery_eligible: bool = False

    policy_version: str = SHADOW_POLICY_VERSION


def evaluate_observation_shadow_v01(
    *,
    decision_context: PersonalizedDecisionContextV01,
    decision_result: PersonalizedDecisionResultV01,
    observation_context: TeachingObservationContextV01,
) -> ObservationAwareShadowReportV01:
    """
    Evaluate observations without changing the actual decision.

    A reported Solution takes precedence over a reported Hint
    only when choosing a review-only candidate. Neither claim
    describes the latest Attempt or determines mastery.
    """

    if not isinstance(
        decision_context,
        PersonalizedDecisionContextV01,
    ):
        raise TypeError(
            "decision_context must be PersonalizedDecisionContextV01."
        )

    if not isinstance(
        decision_result,
        PersonalizedDecisionResultV01,
    ):
        raise TypeError(
            "decision_result must be PersonalizedDecisionResultV01."
        )

    if not isinstance(
        observation_context,
        TeachingObservationContextV01,
    ):
        raise TypeError(
            "observation_context must be TeachingObservationContextV01."
        )

    actual_context = decision_context.decision_context
    state = actual_context.objective_state
    actual_decision = decision_result.decision

    # --------------------------------------------------
    # Verify the identity of the decision and observations.
    # --------------------------------------------------

    if actual_decision.decision_id != actual_context.decision_id:
        raise ValueError(
            "Decision result does not match the decision context."
        )

    if (
        observation_context.student_id != state.student_id
        or observation_context.course_id != state.course_id
        or observation_context.objective_id != state.objective_id
    ):
        raise ValueError(
            "Observation scope does not match Student State."
        )

    existing_action = actual_decision.selected_action
    allowed = actual_decision.allowed_actions

    if existing_action not in allowed:
        raise ValueError(
            "Existing selected action is not in allowed_actions."
        )

    has_request = decision_context.student_request is not None

    if has_request and (
        not decision_result.selected_for_request
        or decision_result.selection_source
        != DecisionSelectionSourceV01.EXPLICIT_STUDENT_REQUEST
    ):
        raise ValueError(
            "Explicit student request and decision result disagree."
        )

    if not has_request and decision_result.selected_for_request:
        raise ValueError(
            "Decision result claims a request that is absent."
        )

    # --------------------------------------------------
    # Shadow-only candidate. No chronology is inferred.
    # --------------------------------------------------

    candidate = None

    if has_request:
        status: ShadowStatusV01 = (
            "explicit_request_preserved"
        )

    else:
        if observation_context.app_solution_attempt_count > 0:
            proposed = TeachingActionV01.SELF_EXPLANATION

        elif observation_context.app_hint_attempt_count > 0:
            proposed = TeachingActionV01.DIAGNOSTIC_ASSESSMENT

        else:
            proposed = None

        if proposed is None:
            status = "no_app_help_candidate"

        elif proposed not in allowed:
            status = "candidate_not_allowed"

        else:
            candidate = proposed

            if candidate == existing_action:
                status = "candidate_matches_existing"
            else:
                status = "candidate_differs_from_existing"

    return ObservationAwareShadowReportV01(
        decision_id=actual_decision.decision_id,
        existing_action=existing_action,
        candidate_action=candidate,
        status=status,
        source_attempt_ids=observation_context.source_attempt_ids,
        observed_attempt_count=(
            observation_context.observed_attempt_count
        ),
        app_hint_attempt_count=(
            observation_context.app_hint_attempt_count
        ),
        app_solution_attempt_count=(
            observation_context.app_solution_attempt_count
        ),
        no_app_report_attempt_count=(
            observation_context.no_app_report_attempt_count
        ),
        would_differ_from_existing=(
            candidate is not None
            and candidate != existing_action
        ),
    )

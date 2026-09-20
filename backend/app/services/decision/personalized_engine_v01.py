"""
URPP Implementation 13B-2.

Deterministic teaching-action selection for explicit student requests.

This is a pure decision component. It does not execute an action,
create evidence, persist records, or modify Student State.

The V0.1 Decision Engine remains the no-request baseline.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)

from app.services.decision.models_v01 import (
    DecisionResultV01,
    TeachingActionV01,
)

from app.services.decision.policy_v01 import (
    PedagogicalPolicyV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestKindV01,
)


REQUEST_ACTION_MAP = {
    StudentLearningRequestKindV01.REQUEST_EXPLANATION:
        TeachingActionV01.CONCEPTUAL_REVIEW,

    StudentLearningRequestKindV01.TRY_INDEPENDENTLY:
        TeachingActionV01.INDEPENDENT_PRACTICE,

    StudentLearningRequestKindV01.REQUEST_HINT:
        TeachingActionV01.CONCEPTUAL_HINT,

    StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC:
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT,

    StudentLearningRequestKindV01.REQUEST_SELF_EXPLANATION:
        TeachingActionV01.SELF_EXPLANATION,

    StudentLearningRequestKindV01.REQUEST_TRANSFER:
        TeachingActionV01.TRANSFER_ASSESSMENT,
}


class DecisionSelectionSourceV01(str, Enum):
    BASELINE = "baseline"
    EXPLICIT_STUDENT_REQUEST = "explicit_student_request"


class PersonalizedDecisionResultV01(BaseModel):
    """
    A selected action plus its decision provenance.

    selected_for_request describes action selection only.
    It does not claim that an Agent has executed the action.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision: DecisionResultV01

    selection_source: DecisionSelectionSourceV01

    selected_for_request: bool

    request_expanded_allowed_actions: bool

    selection_reason: str = Field(min_length=1)


class PersonalizedDecisionEngineV01:
    """
    V0.1 personal-request selection.

    A state-dependent V0.1 action list is treated as a baseline
    teaching-policy list, not a prohibition against a student
    explicitly requesting an existing supported learning activity.

    This engine does not relax evidence-eligibility, assessment,
    session-registration, or database-integrity requirements.
    """

    VERSION = "personalized-request-selection-v0.1"

    POLICY_VERSION = "personalized-request-policy-v0.1"

    def __init__(self) -> None:
        self._baseline = DecisionEngineV01(
            RuleBasedControllerV01()
        )

        self._baseline_policy = PedagogicalPolicyV01()

    def decide(
        self,
        context: PersonalizedDecisionContextV01,
    ) -> PersonalizedDecisionResultV01:

        if not isinstance(
            context,
            PersonalizedDecisionContextV01,
        ):
            raise TypeError(
                "context must be PersonalizedDecisionContextV01."
            )

        decision_context = context.decision_context
        student_request = context.student_request

        original_state = (
            decision_context.objective_state.model_dump(
                mode="json"
            )
        )

        if student_request is None:
            decision = self._baseline.decide(
                decision_context
            )

            result = PersonalizedDecisionResultV01(
                decision=decision,
                selection_source=(
                    DecisionSelectionSourceV01.BASELINE
                ),
                selected_for_request=False,
                request_expanded_allowed_actions=False,
                selection_reason=(
                    "No explicit student request was provided; "
                    "the existing V0.1 baseline selected the action."
                ),
            )

        else:
            try:
                requested_action = REQUEST_ACTION_MAP[
                    student_request.request_kind
                ]
            except KeyError as exc:
                raise ValueError(
                    "Unsupported student learning request."
                ) from exc

            baseline_allowed = (
                self._baseline_policy.allowed_actions(
                    decision_context
                )
            )

            expanded = (
                requested_action not in baseline_allowed
            )

            if expanded:
                allowed = (
                    *baseline_allowed,
                    requested_action,
                )
            else:
                allowed = baseline_allowed

            decision = DecisionResultV01(
                decision_id=decision_context.decision_id,
                selected_action=requested_action,
                allowed_actions=tuple(allowed),
                controller_version=self.VERSION,
                fallback_used=False,
                policy_version=self.POLICY_VERSION,
            )

            result = PersonalizedDecisionResultV01(
                decision=decision,
                selection_source=(
                    DecisionSelectionSourceV01
                    .EXPLICIT_STUDENT_REQUEST
                ),
                selected_for_request=True,
                request_expanded_allowed_actions=expanded,
                selection_reason=(
                    "An explicit student request selected "
                    f"the supported teaching action "
                    f"{requested_action.value}. "
                    "Action execution has not yet occurred."
                ),
            )

        if (
            decision_context.objective_state.model_dump(
                mode="json"
            )
            != original_state
        ):
            raise ValueError(
                "Personalized decision modified Student State."
            )

        if (
            result.decision.selected_action
            not in result.decision.allowed_actions
        ):
            raise ValueError(
                "Selected action is not in the final allowed set."
            )

        return result

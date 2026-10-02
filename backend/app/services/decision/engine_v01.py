"""
URPP Design 01D — Logical Decision Engine V0.1.

Controllers propose teaching actions.
The Policy Engine defines which actions are allowed.

NanoJev and other controllers can implement the same Protocol
without changing the Student State Engine.
"""

from typing import Protocol

from app.domain.learning.models import ObjectiveStateLabel

from app.services.decision.models_v01 import (
    DecisionContextV01,
    DecisionProposalV01,
    DecisionResultV01,
    TeachingActionV01,
)

from app.services.decision.policy_v01 import (
    PedagogicalPolicyV01,
)


class LogicalDecisionController(Protocol):
    def propose(
        self,
        context: DecisionContextV01,
        allowed_actions: tuple[TeachingActionV01, ...],
    ) -> DecisionProposalV01:
        ...


class RuleBasedControllerV01:
    """
    A deterministic baseline for development and comparison.

    The chosen actions are provisional teaching heuristics.
    """

    VERSION = "rule-based-controller-v0.1"

    def propose(
        self,
        context: DecisionContextV01,
        allowed_actions: tuple[TeachingActionV01, ...],
    ) -> DecisionProposalV01:

        state = context.objective_state

        if (
            state.state == ObjectiveStateLabel.UNKNOWN
            and state.distinct_assessment_count == 0
        ):
            preferred = TeachingActionV01.DIAGNOSTIC_ASSESSMENT

        elif state.state == ObjectiveStateLabel.UNKNOWN:
            preferred = TeachingActionV01.INDEPENDENT_PRACTICE

        elif state.state in {
            ObjectiveStateLabel.EMERGING,
            ObjectiveStateLabel.DEVELOPING,
        }:
            preferred = TeachingActionV01.CONCEPTUAL_HINT

        elif state.state in {
            ObjectiveStateLabel.COMPETENT,
            ObjectiveStateLabel.STRONG,
        }:
            preferred = TeachingActionV01.TRANSFER_ASSESSMENT

        else:
            preferred = allowed_actions[0]

        if preferred not in allowed_actions:
            preferred = allowed_actions[0]

        return DecisionProposalV01(
            selected_action=preferred,
            model_version=self.VERSION,
            rationale="Deterministic pedagogical baseline.",
        )


class DecisionEngineV01:
    """
    Select an action from the deterministic policy's allowed set.

    A controller cannot expand the allowed-action set.
    An invalid proposal or controller timeout triggers fallback.

    This engine does not modify Student State, create evidence,
    or execute the teaching action.
    """

    def __init__(
        self,
        controller: LogicalDecisionController,
    ) -> None:
        self._controller = controller
        self._policy = PedagogicalPolicyV01()
        self._fallback = RuleBasedControllerV01()

    def decide(
        self,
        context: DecisionContextV01,
    ) -> DecisionResultV01:

        allowed = self._policy.allowed_actions(context)

        if not allowed:
            raise ValueError(
                "No teaching actions are permitted."
            )

        fallback_used = False

        try:
            proposal = self._controller.propose(
                context,
                allowed,
            )
        except TimeoutError:
            proposal = None

        if (
            not isinstance(proposal, DecisionProposalV01)
            or proposal.selected_action not in allowed
        ):
            fallback_used = True

            proposal = self._fallback.propose(
                context,
                allowed,
            )

        if proposal.selected_action not in allowed:
            raise ValueError(
                "Fallback proposed a disallowed action."
            )

        return DecisionResultV01(
            decision_id=context.decision_id,
            selected_action=proposal.selected_action,
            allowed_actions=allowed,
            controller_version=proposal.model_version,
            fallback_used=fallback_used,
            policy_version=self._policy.VERSION,
        )

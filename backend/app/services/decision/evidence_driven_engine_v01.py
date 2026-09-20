"""
URPP Implementation 13E-1.

Evidence-driven automatic teaching-action selection V0.1.

This component:
- Consumes an existing authoritative Student State.
- Does not estimate mastery from raw evidence or Agent output.
- Defers explicit student requests to the existing
  PersonalizedDecisionEngineV01.
- Excludes Transfer Assessment from automatic selection
  while trusted Transfer Delivery is disabled.
- Does not execute an action, create evidence, mutate state,
  or persist any record.

The selection rules are provisional teaching heuristics,
not empirically validated optimal instructional strategies.
"""

from app.domain.learning.models import ObjectiveStateLabel

from app.services.decision.models_v01 import (
    DecisionContextV01,
    DecisionResultV01,
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    DecisionSelectionSourceV01,
    PersonalizedDecisionEngineV01,
    PersonalizedDecisionResultV01,
)

from app.services.decision.policy_v01 import (
    PedagogicalPolicyV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
)


class EvidenceDrivenDecisionEngineV01:
    """
    A separate opt-in decision engine for 13E-1.

    Existing callers of PersonalizedDecisionEngineV01
    are not changed by introducing this class.
    """

    VERSION = "evidence-driven-controller-v0.1"

    POLICY_VERSION = "evidence-driven-selection-policy-v0.1"

    _AUTOMATICALLY_UNAVAILABLE = frozenset({
        TeachingActionV01.TRANSFER_ASSESSMENT,
    })

    def __init__(self) -> None:
        self._pedagogical_policy = PedagogicalPolicyV01()

        self._request_engine = PersonalizedDecisionEngineV01()

    def decide(
        self,
        context: PersonalizedDecisionContextV01,
    ) -> PersonalizedDecisionResultV01:
        """
        Choose an action from the existing policy's
        allowed set and currently available automatic actions.

        An explicit request uses the existing request engine.
        The downstream delivery checks remain authoritative.
        """

        if not isinstance(
            context,
            PersonalizedDecisionContextV01,
        ):
            raise TypeError(
                "context must be PersonalizedDecisionContextV01."
            )

        if context.student_request is not None:
            return self._request_engine.decide(context)

        decision_context = context.decision_context

        before = decision_context.objective_state.model_dump(
            mode="json"
        )

        allowed_by_policy = (
            self._pedagogical_policy.allowed_actions(
                decision_context
            )
        )

        available = tuple(
            action
            for action in allowed_by_policy
            if action not in self._AUTOMATICALLY_UNAVAILABLE
        )

        if not available:
            raise ValueError(
                "No currently available automatic teaching "
                "action is permitted."
            )

        selected, evidence_reason = self._select_automatic_action(
            decision_context
        )

        # The evidence-driven controller must not expand the
        # existing pedagogical policy's allowed-action set.
        if selected not in available:
            raise ValueError(
                "Evidence-driven policy proposed an unavailable "
                "or disallowed teaching action."
            )

        decision = DecisionResultV01(
            decision_id=decision_context.decision_id,
            selected_action=selected,
            allowed_actions=available,
            controller_version=self.VERSION,
            fallback_used=False,
            policy_version=self.POLICY_VERSION,
        )

        result = PersonalizedDecisionResultV01(
            decision=decision,
            selection_source=(
                DecisionSelectionSourceV01.EVIDENCE_DRIVEN
            ),
            selected_for_request=False,
            request_expanded_allowed_actions=False,
            selection_reason=(
                evidence_reason
                + " Transfer Assessment is excluded from "
                "automatic selection because trusted "
                "Transfer Delivery is not enabled."
            ),
        )

        after = decision_context.objective_state.model_dump(
            mode="json"
        )

        if after != before:
            raise ValueError(
                "Evidence-driven decision modified Student State."
            )

        return result

    def _select_automatic_action(
        self,
        context: DecisionContextV01,
    ) -> tuple[TeachingActionV01, str]:
        """
        Return a provisional action and a traceable reason.

        Only precomputed Objective State information is read.
        Excluded evidence and Agent explanations are not
        interpreted as independent student performance.
        """

        state = context.objective_state

        included_count = len(
            state.included_evidence_ids
        )

        distinct_count = (
            state.distinct_assessment_count
        )

        independent_successes = (
            state.independent_success_count
        )

        prefix = (
            f"Objective state={state.state.value}; "
            f"included_evidence_count={included_count}; "
            f"distinct_assessment_count={distinct_count}; "
            f"independent_success_count={independent_successes}. "
        )

        if state.state == ObjectiveStateLabel.UNKNOWN:
            if included_count == 0 or distinct_count == 0:
                return (
                    TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
                    prefix
                    + "No included evidence with a distinct "
                    "assessment is available for this objective; "
                    "select a diagnostic rather than inferring "
                    "mastery from missing or excluded evidence.",
                )

            return (
                TeachingActionV01.INDEPENDENT_PRACTICE,
                prefix
                + "The objective remains UNKNOWN despite "
                "recorded assessments; select independent "
                "practice to seek additional direct evidence.",
            )

        if state.state in {
            ObjectiveStateLabel.EMERGING,
            ObjectiveStateLabel.DEVELOPING,
        }:
            if included_count == 0 or distinct_count == 0:
                return (
                    TeachingActionV01.CONCEPTUAL_REVIEW,
                    prefix
                    + "The state snapshot has no included "
                    "distinct assessment evidence; select "
                    "conceptual review without asserting "
                    "a specific misconception.",
                )

            if independent_successes == 0:
                return (
                    TeachingActionV01.CONCEPTUAL_HINT,
                    prefix
                    + "No independent success is recorded; "
                    "select a conceptual hint without "
                    "treating assisted performance as "
                    "independent mastery.",
                )

            return (
                TeachingActionV01.INDEPENDENT_PRACTICE,
                prefix
                + "At least one independent success is recorded; "
                "select additional independent practice "
                "rather than assuming mastery is established.",
            )

        if state.state == ObjectiveStateLabel.COMPETENT:
            if independent_successes == 0:
                return (
                    TeachingActionV01.SELF_EXPLANATION,
                    prefix
                    + "The current snapshot has no recorded "
                    "independent success; request a "
                    "self-explanation instead of inferring "
                    "independent mastery from the state label.",
                )

            return (
                TeachingActionV01.INDEPENDENT_PRACTICE,
                prefix
                + "The state records independent success; "
                "select additional independent practice "
                "without asserting that transfer is verified.",
            )

        if state.state == ObjectiveStateLabel.STRONG:
            if independent_successes == 0:
                return (
                    TeachingActionV01.INDEPENDENT_PRACTICE,
                    prefix
                    + "The current snapshot has no recorded "
                    "independent success; seek further "
                    "independent performance evidence.",
                )

            return (
                TeachingActionV01.SELF_EXPLANATION,
                prefix
                + "The state records independent success; "
                "select self-explanation without asserting "
                "that transfer has been demonstrated.",
            )

        raise ValueError(
            "Unsupported Student State for evidence-driven "
            "automatic action selection."
        )

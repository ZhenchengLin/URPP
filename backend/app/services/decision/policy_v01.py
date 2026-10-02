"""
URPP Design 01D — Deterministic Pedagogical Policy V0.1.

This policy defines allowed actions.

Its action-selection rules are engineering baselines,
not empirically validated optimal teaching strategies.
"""

from app.domain.learning.models import ObjectiveStateLabel

from app.services.decision.models_v01 import (
    DecisionContextV01,
    TeachingActionV01,
)


class PedagogicalPolicyV01:
    VERSION = "pedagogical-policy-v0.1"

    def allowed_actions(
        self,
        context: DecisionContextV01,
    ) -> tuple[TeachingActionV01, ...]:

        state = context.objective_state

        if state.state == ObjectiveStateLabel.UNKNOWN:
            return (
                TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
                TeachingActionV01.CONCEPTUAL_REVIEW,
                TeachingActionV01.INDEPENDENT_PRACTICE,
            )

        if state.state in {
            ObjectiveStateLabel.EMERGING,
            ObjectiveStateLabel.DEVELOPING,
        }:
            return (
                TeachingActionV01.CONCEPTUAL_REVIEW,
                TeachingActionV01.CONCEPTUAL_HINT,
                TeachingActionV01.INDEPENDENT_PRACTICE,
                TeachingActionV01.SELF_EXPLANATION,
            )

        if state.state == ObjectiveStateLabel.COMPETENT:
            return (
                TeachingActionV01.INDEPENDENT_PRACTICE,
                TeachingActionV01.SELF_EXPLANATION,
                TeachingActionV01.TRANSFER_ASSESSMENT,
            )

        if state.state == ObjectiveStateLabel.STRONG:
            return (
                TeachingActionV01.SELF_EXPLANATION,
                TeachingActionV01.TRANSFER_ASSESSMENT,
                TeachingActionV01.INDEPENDENT_PRACTICE,
            )

        raise ValueError(
            "Unsupported Student State. No teaching action allowed."
        )

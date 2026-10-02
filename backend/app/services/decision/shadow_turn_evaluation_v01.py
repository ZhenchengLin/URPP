"""
URPP Implementation 13E-4C-3B.

Combine an existing teaching decision with its
observation-aware shadow evaluation.

This module does not execute teaching actions, persist
records, or approve Mastery Evidence.
"""

from dataclasses import dataclass

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)
from app.services.decision.observation_aware_shadow_policy_v01 import (
    ObservationAwareShadowReportV01,
    evaluate_observation_shadow_v01,
)
from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionResultV01,
)
from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)


@dataclass(frozen=True)
class ShadowTurnEvaluationV01:
    """
    Actual decision and shadow report for the same turn.

    The shadow report cannot replace the actual decision.
    """

    actual_decision: PersonalizedDecisionResultV01
    observation_report: ObservationAwareShadowReportV01


def evaluate_shadow_turn_v01(
    *,
    decision_context: PersonalizedDecisionContextV01,
    observation_context: TeachingObservationContextV01,
    decision_engine: EvidenceDrivenDecisionEngineV01,
) -> ShadowTurnEvaluationV01:
    """
    Run the existing decision once and evaluate its result
    against the supplied observation context.

    No action execution or database writes occur here.
    """

    if not isinstance(
        decision_context,
        PersonalizedDecisionContextV01,
    ):
        raise TypeError(
            "decision_context must be PersonalizedDecisionContextV01."
        )

    if not isinstance(
        observation_context,
        TeachingObservationContextV01,
    ):
        raise TypeError(
            "observation_context must be TeachingObservationContextV01."
        )

    if not isinstance(
        decision_engine,
        EvidenceDrivenDecisionEngineV01,
    ):
        raise TypeError(
            "decision_engine must be EvidenceDrivenDecisionEngineV01."
        )

    state = decision_context.decision_context.objective_state
    before_state = state.model_dump(mode="json")

    # The existing engine remains authoritative.
    actual_decision = decision_engine.decide(
        decision_context
    )

    # Evaluate precisely the result returned by that call.
    shadow_report = evaluate_observation_shadow_v01(
        decision_context=decision_context,
        decision_result=actual_decision,
        observation_context=observation_context,
    )

    after_state = state.model_dump(mode="json")

    if after_state != before_state:
        raise ValueError(
            "Shadow evaluation modified Student State."
        )

    if (
        shadow_report.existing_action
        != actual_decision.decision.selected_action
    ):
        raise ValueError(
            "Shadow report does not match actual decision."
        )

    if (
        shadow_report.decision_id
        != actual_decision.decision.decision_id
    ):
        raise ValueError(
            "Shadow report decision ID mismatch."
        )

    return ShadowTurnEvaluationV01(
        actual_decision=actual_decision,
        observation_report=shadow_report,
    )

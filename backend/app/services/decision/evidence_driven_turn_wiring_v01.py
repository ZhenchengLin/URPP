"""
URPP Implementation 13E-2A.

Opt-in composition for evidence-driven personalized turns.

This module uses the existing Personalized Orchestrator.
It does not replace legacy decision behavior globally,
create assessment evidence, or update Student State.

Until trusted Transfer Delivery exists, the assessment
Agent is not invoked for a Transfer Assessment.
"""

from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionResultV01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingAgentPortV01,
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
)

from app.services.decision.transfer_delivery_gate_v01 import (
    require_trusted_transfer_delivery_v01,
)


class _TransferGuardedAssessmentAgentV01:
    """
    Check the existing delivery gate before generating
    assessment content through this opt-in composition.

    This check is additional defense. The Recoverable
    Numeric Session retains its own delivery gate.
    """

    def __init__(
        self,
        *,
        delegate: PersonalizedTeachingAgentPortV01,
    ) -> None:
        self._delegate = delegate

    def produce(
        self,
        *,
        context: PersonalizedDecisionContextV01,
        decision: PersonalizedDecisionResultV01,
    ) -> str:
        require_trusted_transfer_delivery_v01(
            selected_action=decision.decision.selected_action,
        )

        return self._delegate.produce(
            context=context,
            decision=decision,
        )


def create_evidence_driven_personalized_turn_v01(
    *,
    professor_agent: PersonalizedTeachingAgentPortV01,
    assessment_agent: PersonalizedTeachingAgentPortV01,
) -> PersonalizedTeachingTurnOrchestratorV01:
    """
    Construct an opt-in evidence-driven teaching turn.

    Explicit student requests are handled by the existing
    request-priority logic inside the evidence-driven engine.

    A direct caller must still obtain the authoritative
    Objective State through the application's state service.
    """

    return PersonalizedTeachingTurnOrchestratorV01(
        decision_engine=EvidenceDrivenDecisionEngineV01(),
        professor_agent=professor_agent,
        assessment_agent=_TransferGuardedAssessmentAgentV01(
            delegate=assessment_agent,
        ),
    )

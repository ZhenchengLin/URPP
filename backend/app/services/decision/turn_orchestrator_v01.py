"""
URPP Design 01D — Teaching Turn Orchestrator V0.1.

Coordinates one teaching decision and dispatches it to an
appropriate internal Agent port.

This module does not implement an LLM Agent, accept student
answers, generate learning evidence, or update Student State.

Authentication, persistence, and full session management
remain separate application-service responsibilities.
"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.services.decision.engine_v01 import DecisionEngineV01

from app.services.decision.models_v01 import (
    DecisionContextV01,
    DecisionResultV01,
    TeachingActionV01,
)


AgentKindV01 = Literal["professor", "assessment"]


ASSESSMENT_ACTIONS = frozenset(
    {
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
        TeachingActionV01.INDEPENDENT_PRACTICE,
        TeachingActionV01.TRANSFER_ASSESSMENT,
    }
)

PROFESSOR_ACTIONS = frozenset(
    {
        TeachingActionV01.CONCEPTUAL_REVIEW,
        TeachingActionV01.CONCEPTUAL_HINT,
        TeachingActionV01.SELF_EXPLANATION,
    }
)


class TeachingAgentPortV01(Protocol):
    """
    Internal interface implemented by a teaching Agent adapter.

    The Agent receives a policy-checked decision and must
    return the content for this single teaching turn.

    An Agent must not update ObjectiveStateV02.
    """

    def produce(
        self,
        *,
        context: DecisionContextV01,
        decision: DecisionResultV01,
    ) -> str:
        ...


class TeachingTurnResultV01(BaseModel):
    """
    Result of executing one policy-checked teaching action.

    This result is teaching content, not assessment evidence.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision: DecisionResultV01

    agent_kind: AgentKindV01

    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def require_nonempty_content(cls, value: str) -> str:
        content = value.strip()

        if not content:
            raise ValueError(
                "Teaching Agent content cannot be empty."
            )

        return content


class DecisionContextBuilderV01:
    """
    Build a decision context from an existing Student State.

    The caller is responsible for obtaining the state from a
    trusted, appropriately authorized application service.
    """

    def build(
        self,
        objective_state: ObjectiveStateV02,
        *,
        decision_id: str,
        requested_at: datetime,
    ) -> DecisionContextV01:

        if not isinstance(
            objective_state,
            ObjectiveStateV02,
        ):
            raise TypeError(
                "objective_state must be ObjectiveStateV02."
            )

        if (
            not isinstance(decision_id, str)
            or not decision_id.strip()
        ):
            raise ValueError(
                "decision_id must be a non-empty string."
            )

        return DecisionContextV01(
            decision_id=decision_id,
            objective_state=objective_state,
            requested_at=requested_at,
        )


class TeachingTurnOrchestratorV01:
    """
    Build context, select an action, and invoke one Agent.

    This is a single-turn coordinator, not a complete
    autonomous tutoring session.

    It rejects invalid Agent output instead of silently
    inventing teaching content or learning evidence.
    """

    def __init__(
        self,
        *,
        decision_engine: DecisionEngineV01,
        professor_agent: TeachingAgentPortV01,
        assessment_agent: TeachingAgentPortV01,
    ) -> None:

        self._decision_engine = decision_engine
        self._professor_agent = professor_agent
        self._assessment_agent = assessment_agent
        self._context_builder = DecisionContextBuilderV01()

    @staticmethod
    def _route_action(
        action: TeachingActionV01,
    ) -> AgentKindV01:

        if action in ASSESSMENT_ACTIONS:
            return "assessment"

        if action in PROFESSOR_ACTIONS:
            return "professor"

        raise ValueError(
            "No Agent is registered for this teaching action."
        )

    def run_turn(
        self,
        objective_state: ObjectiveStateV02,
        *,
        decision_id: str,
        requested_at: datetime,
    ) -> TeachingTurnResultV01:

        context = self._context_builder.build(
            objective_state,
            decision_id=decision_id,
            requested_at=requested_at,
        )

        # Detect accidental in-place changes made by an
        # internal controller or Agent during this call.
        #
        # This is an engineering assertion, not an
        # authentication or security boundary.
        original_state = objective_state.model_dump(
            mode="json"
        )

        decision = self._decision_engine.decide(context)

        if (
            decision.decision_id != context.decision_id
            or decision.selected_action
            not in decision.allowed_actions
        ):
            raise ValueError(
                "Decision Engine returned an invalid decision."
            )

        if objective_state.model_dump(
            mode="json"
        ) != original_state:
            raise ValueError(
                "Decision execution modified Student State."
            )

        agent_kind = self._route_action(
            decision.selected_action
        )

        if agent_kind == "assessment":
            agent = self._assessment_agent
        else:
            agent = self._professor_agent

        content = agent.produce(
            context=context,
            decision=decision,
        )

        if objective_state.model_dump(
            mode="json"
        ) != original_state:
            raise ValueError(
                "Teaching Agent modified Student State."
            )

        if not isinstance(content, str):
            raise TypeError(
                "Teaching Agent must return a string."
            )

        return TeachingTurnResultV01(
            decision=decision,
            agent_kind=agent_kind,
            content=content,
        )

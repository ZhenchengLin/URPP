"""
URPP Implementation 13C-1.

Execute one personalized teaching turn using a structured
student request and an authoritative Student State.

This module does not create assessment evidence, update
mastery, persist a session, or implement a real LLM Agent.
"""

from datetime import datetime
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
    PersonalizedDecisionResultV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
    PROFESSOR_ACTIONS,
    AgentKindV01,
    DecisionContextBuilderV01,
)


class PersonalizedTeachingAgentPortV01(Protocol):
    """
    An Agent adapter receives the complete personalized
    context and the policy-checked decision result.

    The request is contextual information, not evidence
    that the student has mastered the Objective.
    """

    def produce(
        self,
        *,
        context: PersonalizedDecisionContextV01,
        decision: PersonalizedDecisionResultV01,
    ) -> str:
        ...


class PersonalizedTeachingTurnResultV01(BaseModel):
    """
    Result of one completed teaching-content generation call.

    The content is not assessment evidence and does not
    imply that an assessment answer has been submitted.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision: PersonalizedDecisionResultV01

    agent_kind: AgentKindV01

    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def require_nonempty_content(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Teaching Agent content cannot be empty."
            )

        return value


class PersonalizedTeachingTurnOrchestratorV01:
    """
    Select and execute exactly one personalized teaching action.

    The personalized engine is called once. The existing
    TeachingTurnOrchestratorV01 is intentionally not called,
    because it would make a second, legacy decision.
    """

    VERSION = "personalized-turn-orchestrator-v0.1"

    def __init__(
        self,
        *,
        decision_engine: PersonalizedDecisionEngineV01,
        professor_agent: PersonalizedTeachingAgentPortV01,
        assessment_agent: PersonalizedTeachingAgentPortV01,
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
        student_request: StudentLearningRequestV01 | None = None,
    ) -> PersonalizedTeachingTurnResultV01:
        """
        Build a personalized context, decide once, and call
        exactly one Agent.

        The caller must obtain Objective State and any student
        request from an appropriately authorized application
        service. This component does not authenticate callers.
        """

        decision_context = self._context_builder.build(
            objective_state,
            decision_id=decision_id,
            requested_at=requested_at,
        )

        context = PersonalizedDecisionContextV01(
            decision_context=decision_context,
            student_request=student_request,
        )

        original_state = objective_state.model_dump(
            mode="json"
        )

        personalized_decision = (
            self._decision_engine.decide(context)
        )

        if not isinstance(
            personalized_decision,
            PersonalizedDecisionResultV01,
        ):
            raise TypeError(
                "Personalized Decision Engine returned "
                "an invalid result."
            )

        decision = personalized_decision.decision

        if (
            decision.decision_id != context.decision_context.decision_id
            or decision.selected_action
            not in decision.allowed_actions
        ):
            raise ValueError(
                "Personalized Decision Engine returned "
                "an invalid decision."
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

        # The Agent receives the original structured request,
        # not merely the selected TeachingAction.
        content = agent.produce(
            context=context,
            decision=personalized_decision,
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

        return PersonalizedTeachingTurnResultV01(
            decision=personalized_decision,
            agent_kind=agent_kind,
            content=content,
        )

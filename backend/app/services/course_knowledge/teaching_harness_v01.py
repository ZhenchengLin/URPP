"""
URPP Implementation 14B-1.

An opt-in Course-Grounded Teaching Harness.

Resolve a validated Course Knowledge Context before executing
one teaching turn through the existing personalized orchestrator.

Scope:
- One student, course, objective, and teaching turn.
- Professor teaching actions only.
- No real LLM, persistence, delivery, or assessment issuance.
- No Student State update or mastery-evidence creation.

This module does not authenticate the caller or verify that
Course Pack approval metadata came from an authorized reviewer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.domain.learning.state_v02 import (
    ObjectiveStateV02,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseKnowledgeContextV01,
    CourseSourceRefV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionResultV01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedDecisionPortV01,
    PersonalizedTeachingTurnOrchestratorV01,
    PersonalizedTeachingTurnResultV01,
)

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestV01,
)


class CourseGroundedProfessorPortV01(Protocol):
    """
    Professor adapter capable of receiving course knowledge.

    The agent receives a policy-checked decision and an
    already validated Course Knowledge Context.

    It cannot use this interface to update Student State.
    """

    def produce(
        self,
        *,
        context: PersonalizedDecisionContextV01,
        decision: PersonalizedDecisionResultV01,
        course_knowledge: CourseKnowledgeContextV01,
    ) -> str:
        ...


@dataclass(frozen=True)
class CourseGroundedTeachingResultV01:
    """
    In-memory record of one generated Professor turn.

    source_refs describe the inputs provided to the Professor.
    They do not prove that every statement in the generated
    content is supported by those sources.

    'generated' does not mean presented, delivered, persisted,
    assessed, or learned.
    """

    completed_turn: PersonalizedTeachingTurnResultV01

    course_knowledge: CourseKnowledgeContextV01

    pack_id: str
    pack_revision: str

    source_refs: tuple[
        CourseSourceRefV01,
        ...
    ]

    execution_status: Literal["generated"] = "generated"


class _BoundProfessorAgentV01:
    """
    Adapt a course-aware Professor to the existing Agent Port.

    This adapter is created for one call. Course context is
    never stored on a shared, mutable Professor instance.
    """

    def __init__(
        self,
        *,
        professor: CourseGroundedProfessorPortV01,
        course_knowledge: CourseKnowledgeContextV01,
    ) -> None:
        self._professor = professor
        self._course_knowledge = course_knowledge

    def produce(
        self,
        *,
        context: PersonalizedDecisionContextV01,
        decision: PersonalizedDecisionResultV01,
    ) -> str:
        return self._professor.produce(
            context=context,
            decision=decision,
            course_knowledge=self._course_knowledge,
        )


class _BlockedAssessmentAgentV01:
    """
    Explicitly prevent Assessment execution in 14B-1.

    An Assessment Action must use the existing guarded
    assessment/session pipeline in a later integration.
    """

    def produce(
        self,
        *,
        context: PersonalizedDecisionContextV01,
        decision: PersonalizedDecisionResultV01,
    ) -> str:
        raise RuntimeError(
            "14B-1 does not execute Assessment Actions."
        )


class CourseGroundedTeachingHarnessV01:
    """
    Resolve course knowledge and execute one Professor turn.

    The existing personalized decision engine and orchestrator
    retain their current responsibilities.

    No second decision is introduced.
    """

    VERSION = "course-grounded-teaching-harness-v0.1"

    def __init__(
        self,
        *,
        decision_engine: PersonalizedDecisionPortV01,
        professor_agent: CourseGroundedProfessorPortV01,
    ) -> None:
        self._decision_engine = decision_engine
        self._professor_agent = professor_agent

    def run_professor_turn(
        self,
        objective_state: ObjectiveStateV02,
        *,
        pack: CoursePackV01,
        course_id: str,
        objective_id: str,
        expected_pack_revision: str,
        decision_id: str,
        requested_at: datetime,
        student_request: StudentLearningRequestV01 | None = None,
    ) -> CourseGroundedTeachingResultV01:
        """
        Execute a course-grounded Professor teaching turn.

        Validate course and objective scope before the Decision
        Engine or teaching agent can be called.
        """

        if (
            objective_state.course_id != course_id
            or objective_state.objective_id != objective_id
        ):
            raise ValueError(
                "Student State course/objective scope mismatch."
            )

        if (
            student_request is not None
            and student_request.objective_id != objective_id
        ):
            raise ValueError(
                "Student request objective scope mismatch."
            )

        course_knowledge = resolve_course_knowledge_v01(
            pack=pack,
            course_id=course_id,
            objective_id=objective_id,
            expected_pack_revision=expected_pack_revision,
        )

        bound_professor = _BoundProfessorAgentV01(
            professor=self._professor_agent,
            course_knowledge=course_knowledge,
        )

        orchestrator = (
            PersonalizedTeachingTurnOrchestratorV01(
                decision_engine=self._decision_engine,
                professor_agent=bound_professor,
                assessment_agent=_BlockedAssessmentAgentV01(),
            )
        )

        completed_turn = orchestrator.run_turn(
            objective_state,
            decision_id=decision_id,
            requested_at=requested_at,
            student_request=student_request,
        )

        # The assessment adapter blocks that execution path.
        # This additional invariant guards the returned result.
        if completed_turn.agent_kind != "professor":
            raise RuntimeError(
                "14B-1 requires a Professor teaching action."
            )

        return CourseGroundedTeachingResultV01(
            completed_turn=completed_turn,
            course_knowledge=course_knowledge,
            pack_id=pack.pack_id,
            pack_revision=pack.pack_revision,
            source_refs=course_knowledge.objective.source_refs,
        )

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CognitiveDemand(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class KnowledgeType(str, Enum):
    FACTUAL = "factual"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    METACOGNITIVE = "metacognitive"


class ObjectiveStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class LearningObjective(BaseModel):
    objective_id: str
    course_id: str
    concept_id: str

    title: str
    description: str

    cognitive_demand: CognitiveDemand
    knowledge_type: KnowledgeType

    importance: Literal["supporting", "core"] = "core"

    prerequisite_objectives: list[str] = Field(
        default_factory=list
    )

    source_refs: list[str] = Field(
        default_factory=list
    )

    source_type: str

    authority: Literal[
        "low",
        "medium",
        "high",
    ]

    status: ObjectiveStatus = ObjectiveStatus.ACTIVE

    created_by: str

    created_at: datetime
    updated_at: datetime


class EvidenceType(str, Enum):
    PROBLEM_ATTEMPT = "problem_attempt"
    SELF_EXPLANATION = "self_explanation"
    DEFINITION_RECALL = "definition_recall"
    STUDENT_QUESTION = "student_question"
    STUDENT_SELF_REPORT = "student_self_report"
    TRANSFER_ATTEMPT = "transfer_attempt"
    RETRIEVAL_ATTEMPT = "retrieval_attempt"
    ERROR_CORRECTION = "error_correction"
    TEACHER_OBSERVATION = "teacher_observation"
    STUDENT_DISPUTE = "student_dispute"


class ErrorType(str, Enum):
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    CALCULATION = "calculation"
    NOTATION = "notation"
    INTERPRETATION = "interpretation"
    EXECUTION = "execution"
    UNKNOWN = "unknown"


class EvidenceEvent(BaseModel):
    evidence_id: str

    student_id: str
    course_id: str
    session_id: str
    objective_id: str

    source_message_id: str | None = None

    evidence_type: EvidenceType

    observation: str

    outcome: Literal[
        "success",
        "partial",
        "failure",
        "neutral",
    ]

    correctness: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    assistance_level: int | None = Field(
        default=None,
        ge=0,
        le=6,
    )

    novelty: Literal[
        "repeated",
        "similar",
        "novel",
        "unknown",
    ] = "unknown"

    transfer_distance: Literal[
        "none",
        "near",
        "far",
        "unknown",
    ] = "unknown"

    explanation_quality: Literal[
        "poor",
        "adequate",
        "strong",
        "unknown",
    ] = "unknown"

    error_type: ErrorType | None = None

    attempt_count: int = Field(
        default=1,
        ge=1,
    )

    student_confidence: Literal[
        "low",
        "medium",
        "high",
        "unknown",
    ] = "unknown"

    evidence_strength: float = Field(
        ge=-1.0,
        le=1.0,
    )

    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    created_at: datetime


class ObjectiveStateLabel(str, Enum):
    UNKNOWN = "unknown"
    EMERGING = "emerging"
    DEVELOPING = "developing"
    COMPETENT = "competent"
    STRONG = "strong"


class ObjectiveState(BaseModel):
    student_id: str
    objective_id: str

    state: ObjectiveStateLabel

    state_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    positive_evidence_count: int = 0
    negative_evidence_count: int = 0

    independent_success_count: int = 0
    transfer_success_count: int = 0

    recent_evidence_count: int = 0

    last_evidence_at: datetime | None = None
    last_independent_success_at: datetime | None = None
    last_transfer_success_at: datetime | None = None

    status_reason: str

    updated_at: datetime

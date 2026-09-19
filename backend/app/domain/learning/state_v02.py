"""
URPP Student Modeling — V0.2 Domain Models.

This module defines the structured data contracts for
the V0.2 State Update Engine.

It does NOT implement the state estimation algorithm.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.domain.learning.models import (
    EvidenceType,
    ObjectiveStateLabel,
)


# ============================================================
# 1. OBJECTIVE ALIGNMENT
# ============================================================


class ObjectiveAlignment(str, Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    NOT_ALIGNED = "not_aligned"
    UNKNOWN = "unknown"


# ============================================================
# 2. ASSESSMENT VALIDITY
# ============================================================


class AssessmentValidity(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


# ============================================================
# 3. PERFORMANCE STABILITY
# ============================================================


class PerformanceStability(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    CONSISTENT = "consistent"
    MIXED = "mixed"


# ============================================================
# 4. EVIDENCE FRESHNESS
# ============================================================


class EvidenceFreshness(str, Enum):
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


# ============================================================
# 5. EVIDENCE SUPPORT
# ============================================================


class EvidenceSupport(str, Enum):
    INSUFFICIENT = "insufficient"
    LIMITED = "limited"
    MODERATE = "moderate"
    SUBSTANTIAL = "substantial"


# ============================================================
# 6. EVIDENCE EVENT V0.2
# ============================================================


class EvidenceEventV02(BaseModel):
    """
    An immutable, structured observation of student performance
    or learning-related behavior.

    Not every EvidenceEvent is eligible for mastery estimation.
    Eligibility is determined by the State Update Engine.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # --------------------------------------------------------
    # Identity
    # --------------------------------------------------------

    evidence_id: str

    student_id: str
    course_id: str
    session_id: str
    objective_id: str

    source_message_id: str | None = None

    # --------------------------------------------------------
    # Assessment identity
    # --------------------------------------------------------

    assessment_item_id: str | None = None

    response_group_id: str | None = None

    # --------------------------------------------------------
    # Evidence classification
    # --------------------------------------------------------

    evidence_type: EvidenceType

    observation: str

    objective_alignment: ObjectiveAlignment = (
        ObjectiveAlignment.UNKNOWN
    )

    assessment_validity: AssessmentValidity = (
        AssessmentValidity.UNCERTAIN
    )

    # --------------------------------------------------------
    # Performance
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Assistance
    # --------------------------------------------------------

    assistance_level: int | None = Field(
        default=None,
        ge=0,
        le=6,
    )

    prior_solution_exposure: bool | None = None

    # --------------------------------------------------------
    # Assessment novelty
    # --------------------------------------------------------

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

    # Explicit delay for retrieval assessments.
    # None means the delay has not been established.
    retrieval_delay_hours: float | None = Field(
        default=None,
        ge=0.0,
    )

    # --------------------------------------------------------
    # Interpretation
    # --------------------------------------------------------

    model_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    scoring_policy_version: str

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Evidence timestamps must be timezone-aware."
            )

        return value


# ============================================================
# 7. OBJECTIVE STATE V0.2
# ============================================================


class ObjectiveStateV02(BaseModel):
    """
    Derived estimate of one student's observed performance
    on one Learning Objective.

    This is NOT a permanent student trait or a scientifically
    calibrated probability of mastery.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # --------------------------------------------------------
    # Identity
    # --------------------------------------------------------

    student_id: str
    course_id: str
    objective_id: str

    # --------------------------------------------------------
    # Derived state
    # --------------------------------------------------------

    state: ObjectiveStateLabel

    performance_estimate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    evidence_support_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    evidence_support: EvidenceSupport

    performance_stability: PerformanceStability

    evidence_freshness: EvidenceFreshness

    # --------------------------------------------------------
    # Evidence summary
    # --------------------------------------------------------

    effective_evidence_mass: float = Field(
        ge=0.0,
    )

    distinct_assessment_count: int = Field(
        ge=0,
    )

    distinct_session_count: int = Field(
        ge=0,
    )

    independent_success_count: int = Field(
        ge=0,
    )

    transfer_success_count: int = Field(
        ge=0,
    )

    # --------------------------------------------------------
    # Traceability
    # --------------------------------------------------------

    included_evidence_ids: list[str] = Field(
        default_factory=list,
    )

    excluded_evidence_ids: list[str] = Field(
        default_factory=list,
    )

    exclusion_reasons: dict[str, str] = Field(
        default_factory=dict,
    )

    # --------------------------------------------------------
    # Policy versioning
    # --------------------------------------------------------

    policy_version: str

    scoring_policy_version: str

    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    as_of: datetime

    last_direct_assessment_at: datetime | None = None

    last_independent_assessment_at: datetime | None = None

    @field_validator(
        "as_of",
        "last_direct_assessment_at",
        "last_independent_assessment_at",
    )
    @classmethod
    def require_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "State timestamps must be timezone-aware."
            )

        return value

"""
URPP Design 01C — Assessment Data Contract V0.2.

Defines an assessment item, its scoring rubric, and a
student attempt.

This module does not score answers or modify student state.
"""

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.learning.models import EvidenceType


class AnswerKind(str, Enum):
    NUMERIC = "numeric"


class NumericRubricV02(BaseModel):
    """A deterministic scoring rule for a numeric answer."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    answer_kind: AnswerKind = AnswerKind.NUMERIC

    expected_value: float

    absolute_tolerance: float = Field(
        default=0.0,
        ge=0.0,
    )

    rubric_version: str = Field(min_length=1)

    @field_validator("expected_value", "absolute_tolerance")
    @classmethod
    def require_finite_number(cls, value: float) -> float:
        from math import isfinite

        if not isfinite(value):
            raise ValueError("Rubric values must be finite.")

        return value


class AssessmentItemV02(BaseModel):
    """
    One question associated with one observable Learning Objective.

    The item identity and rubric are defined before grading.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    assessment_item_id: str = Field(min_length=1)

    course_id: str = Field(min_length=1)

    objective_id: str = Field(min_length=1)

    prompt: str = Field(min_length=1)

    evidence_type: EvidenceType = EvidenceType.PROBLEM_ATTEMPT

    rubric: NumericRubricV02

    # Set only after a reviewer confirms that this particular
    # question directly assesses its stated Learning Objective.
    # A matching objective_id alone does not establish alignment.
    alignment_verified: bool = False

    @model_validator(mode="after")
    def require_supported_evidence_type(self):
        allowed = {
            EvidenceType.PROBLEM_ATTEMPT,
            EvidenceType.TRANSFER_ATTEMPT,
            EvidenceType.RETRIEVAL_ATTEMPT,
        }

        if self.evidence_type not in allowed:
            raise ValueError(
                "AssessmentItemV02 requires a supported "
                "performance evidence type."
            )

        return self


class StudentAttemptV02(BaseModel):
    """
    A student's submitted response and known assessment context.

    Assistance and prior solution exposure describe the conditions
    of the attempt. They must not be inferred from correctness.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    attempt_id: str = Field(min_length=1)

    student_id: str = Field(min_length=1)

    course_id: str = Field(min_length=1)

    session_id: str = Field(min_length=1)

    objective_id: str = Field(min_length=1)

    assessment_item_id: str = Field(min_length=1)

    source_message_id: str = Field(min_length=1)

    response_group_id: str = Field(min_length=1)

    response_text: str = Field(min_length=1)

    assistance_level: int | None = Field(
        default=None,
        ge=0,
        le=6,
    )

    prior_solution_exposure: bool | None = None

    novelty: str = Field(
        default="unknown",
        pattern="^(repeated|similar|novel|unknown)$",
    )

    submitted_at: datetime

    @field_validator("submitted_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "submitted_at must be timezone-aware."
            )

        return value

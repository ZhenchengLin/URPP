"""
URPP Design 01C — Open-Response Assessment Contract V0.2.

Defines an observable criterion-based rubric and a structured
review record. This module does not automatically grade answers
or generate EvidenceEventV02.
"""

from datetime import datetime
from math import isclose, isfinite
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.domain.learning.models import EvidenceType


class OpenResponseCriterionV02(BaseModel):
    """One observable requirement in an assessment rubric."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    full_credit_guidance: str = Field(min_length=1)
    weight: float = Field(gt=0.0, le=1.0)

    @field_validator("weight")
    @classmethod
    def require_finite_weight(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("Criterion weight must be finite.")
        return value


class OpenResponseRubricV02(BaseModel):
    """A versioned rubric whose criterion weights total 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric_version: str = Field(min_length=1)
    criteria: list[OpenResponseCriterionV02] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_criteria(self):
        ids = [c.criterion_id for c in self.criteria]

        if len(ids) != len(set(ids)):
            raise ValueError("Criterion IDs must be unique.")

        total = sum(c.weight for c in self.criteria)

        if not isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(
                "Rubric criterion weights must total 1.0."
            )

        return self


class OpenResponseAssessmentItemV02(BaseModel):
    """An open-response question tied to one Learning Objective."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assessment_item_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)

    prompt: str = Field(min_length=1)
    evidence_type: EvidenceType = EvidenceType.SELF_EXPLANATION

    rubric: OpenResponseRubricV02

    alignment_verified: bool = False
    alignment_reviewer_id: str | None = None

    @model_validator(mode="after")
    def validate_assessment(self):
        supported = {
            EvidenceType.SELF_EXPLANATION,
            EvidenceType.DEFINITION_RECALL,
            EvidenceType.PROBLEM_ATTEMPT,
        }

        if self.evidence_type not in supported:
            raise ValueError(
                "Unsupported open-response evidence type."
            )

        if self.alignment_verified and not (
            self.alignment_reviewer_id
            and self.alignment_reviewer_id.strip()
        ):
            raise ValueError(
                "Verified alignment requires a reviewer ID."
            )

        return self


class CriterionReviewV02(BaseModel):
    """
    A reviewer's judgment for one rubric criterion.

    A supporting quote is required when credit is awarded.
    The quote is not yet verified against the student response.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str = Field(min_length=1)

    judgment: Literal[
        "met",
        "partial",
        "not_met",
        "unscorable",
    ]

    supporting_quote: str | None = None
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_support_for_credit(self):
        if self.judgment in {"met", "partial"}:
            if not (
                self.supporting_quote
                and self.supporting_quote.strip()
            ):
                raise ValueError(
                    "Awarded credit requires a supporting quote."
                )

        return self


class OpenResponseReviewV02(BaseModel):
    """
    A structured review record.

    Its criterion IDs, rubric version, and supporting quotes
    must be checked against the assessment and student attempt
    before any EvidenceEventV02 can be generated.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    assessment_item_id: str = Field(min_length=1)
    rubric_version: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)

    criteria: list[CriterionReviewV02] = Field(
        min_length=1
    )

    reviewed_at: datetime

    @field_validator("reviewed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Review timestamps must be timezone-aware."
            )

        return value

"""
URPP Design 01D — Logical Decision Contracts V0.1.

These models represent teaching decisions, not student mastery.

A Decision Model cannot modify ObjectiveStateV02.
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

from app.domain.learning.state_v02 import ObjectiveStateV02


class TeachingActionV01(str, Enum):
    DIAGNOSTIC_ASSESSMENT = "diagnostic_assessment"
    CONCEPTUAL_REVIEW = "conceptual_review"
    CONCEPTUAL_HINT = "conceptual_hint"
    INDEPENDENT_PRACTICE = "independent_practice"
    SELF_EXPLANATION = "self_explanation"
    TRANSFER_ASSESSMENT = "transfer_assessment"


class DecisionContextV01(BaseModel):
    """
    The authoritative Student State at one decision point.

    The context is constructed by the application layer.
    The Decision Model must not construct its own Student State.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision_id: str = Field(min_length=1)

    objective_state: ObjectiveStateV02

    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Decision timestamp must be timezone-aware."
            )

        return value

    @model_validator(mode="after")
    def validate_time_order(self):
        if self.requested_at < self.objective_state.as_of:
            raise ValueError(
                "Decision cannot precede its Student State snapshot."
            )

        return self


class DecisionProposalV01(BaseModel):
    """
    A controller's proposed teaching action.

    This proposal has not yet passed the final policy check.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    selected_action: TeachingActionV01

    model_version: str = Field(min_length=1)

    rationale: str = Field(min_length=1)


class DecisionResultV01(BaseModel):
    """
    The final policy-checked decision.

    fallback_used indicates whether the requested controller
    failed or proposed an action outside the allowed set.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision_id: str

    selected_action: TeachingActionV01

    allowed_actions: tuple[TeachingActionV01, ...]

    controller_version: str

    fallback_used: bool

    policy_version: str = "pedagogical-policy-v0.1"

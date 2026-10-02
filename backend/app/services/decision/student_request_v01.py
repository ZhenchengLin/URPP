"""
URPP Implementation 13B-1.

Structured student learning requests for future personalized decisions.

This module does not select a teaching action, change Student State,
or modify the existing V0.1 Decision Engine.
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

from app.services.decision.models_v01 import DecisionContextV01


class StudentLearningRequestKindV01(str, Enum):
    REQUEST_EXPLANATION = "request_explanation"
    TRY_INDEPENDENTLY = "try_independently"
    REQUEST_HINT = "request_hint"
    REQUEST_DIAGNOSTIC = "request_diagnostic"
    REQUEST_SELF_EXPLANATION = "request_self_explanation"
    REQUEST_TRANSFER = "request_transfer"


class StudentLearningRequestV01(BaseModel):
    """
    A student's explicit request about the current learning activity.

    A request is not evidence of mastery. It must not directly update
    the authoritative Objective State.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    objective_id: str = Field(min_length=1)

    request_kind: StudentLearningRequestKindV01

    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Student request timestamp must be timezone-aware."
            )

        return value


class PersonalizedDecisionContextV01(BaseModel):
    """
    Composition-based input for a future personalized Decision Engine.

    The existing DecisionEngineV01 must not silently consume this
    context while ignoring its student_request field.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision_context: DecisionContextV01

    student_request: StudentLearningRequestV01 | None = None

    @model_validator(mode="after")
    def validate_student_request(self):
        request = self.student_request

        if request is None:
            return self

        state = self.decision_context.objective_state

        if request.objective_id != state.objective_id:
            raise ValueError(
                "Student request must match the current Objective."
            )

        if request.requested_at < state.as_of:
            raise ValueError(
                "Student request predates the Student State snapshot."
            )

        if request.requested_at > self.decision_context.requested_at:
            raise ValueError(
                "Student request cannot occur after the decision."
            )

        return self

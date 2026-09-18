from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MisconceptionStatus(str, Enum):
    SUSPECTED = "suspected"
    ACTIVE = "active"
    IMPROVING = "improving"
    RESOLVED = "resolved"
    RECURRING = "recurring"


class Misconception(BaseModel):
    misconception_id: str

    student_id: str
    course_id: str
    concept_id: str

    description: str

    status: MisconceptionStatus

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    supporting_evidence_ids: list[str] = Field(
        default_factory=list
    )

    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime

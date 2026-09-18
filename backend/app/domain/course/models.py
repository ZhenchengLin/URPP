from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class MaterialType(str, Enum):
    SYLLABUS = "syllabus"
    LECTURE = "lecture"
    HOMEWORK = "homework"
    READING = "reading"
    STUDY_GUIDE = "study_guide"
    PROJECT = "project"
    NOTE = "note"
    OTHER = "other"


class CourseMaterial(BaseModel):
    material_id: str
    course_id: str

    title: str
    material_type: MaterialType

    week: int | None = Field(
        default=None,
        ge=1,
    )

    course_date: date | None = None

    source_type: str
    authority: str

    processing_status: str = "pending"

    created_at: datetime

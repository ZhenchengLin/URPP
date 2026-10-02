"""
URPP Implementation 14B-3-2A.

Persist a caller-supplied student response to one learning
activity associated with an already presented teaching Trace.

This Repository records:
- the activity identifier and prompt;
- the submitted response text;
- the original generated Trace and presentation event;
- the submission timestamp.

It does NOT:
- prove that the caller is the student;
- prove the activity prompt was shown to the student;
- grade or interpret the answer;
- create Assessment Evidence or update Student State;
- create an Engine, database, or production schema.

In V0.1 the first response to one activity is immutable.
Answer revision and multiple attempts require a later contract.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Table,
    UniqueConstraint,
    select,
)

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.repositories.course_teaching_presentation_v01 import (
    CourseTeachingDeliveryStateV01,
    CourseTeachingPresentationRepositoryV01,
    course_teaching_presentations_v01,
)

from app.repositories.course_teaching_trace_v01 import (
    course_teaching_traces_v01,
)


# Reuse Teaching Trace metadata so foreign keys reference
# the existing Trace and Presentation tables. Do not add
# this table to Numeric Assessment Base.metadata.
course_learning_responses_v01 = Table(
    "course_learning_responses_v01",
    course_teaching_traces_v01.metadata,

    Column(
        "response_id",
        String(128),
        primary_key=True,
    ),
    Column(
        "trace_id",
        String(128),
        ForeignKey(
            "course_teaching_traces_v01.trace_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    ),
    Column(
        "presentation_event_id",
        String(128),
        ForeignKey(
            "course_teaching_presentations_v01.event_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    ),
    Column(
        "student_id",
        String(128),
        nullable=False,
    ),
    Column(
        "course_id",
        String(128),
        nullable=False,
    ),
    Column(
        "objective_id",
        String(128),
        nullable=False,
    ),
    Column(
        "activity_id",
        String(128),
        nullable=False,
    ),
    Column(
        "activity_prompt",
        String(2000),
        nullable=False,
    ),
    Column(
        "activity_prompt_sha256",
        String(64),
        nullable=False,
    ),
    Column(
        "response_text",
        String(4000),
        nullable=False,
    ),
    Column(
        "submitted_at_utc",
        String(48),
        nullable=False,
    ),

    UniqueConstraint(
        "trace_id",
        "activity_id",
        name="course_response_trace_activity_unique_v01",
    ),
)


@dataclass(frozen=True)
class StoredCourseLearningResponseV01:
    """
    One immutable, caller-supplied response record.

    response_text is raw submitted text, not a grade,
    a proficiency estimate, or verified learning evidence.
    """

    response_id: str
    trace_id: str
    presentation_event_id: str

    student_id: str
    course_id: str
    objective_id: str

    activity_id: str
    activity_prompt: str
    response_text: str

    submitted_at: datetime


class CourseLearningResponseRepositoryV01:
    """
    Store one response after a presentation report exists.

    A trusted application layer must handle student identity,
    authorization, and actual presentation of the activity.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
    ) -> None:
        if not isinstance(session_factory, sessionmaker):
            raise TypeError(
                "session_factory must be a SQLAlchemy sessionmaker."
            )

        self._session_factory = session_factory

        self._presentations = (
            CourseTeachingPresentationRepositoryV01(
                session_factory
            )
        )

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 128
        ):
            raise ValueError(
                f"{name} must be a non-empty string "
                "of at most 128 characters."
            )

        return value

    @staticmethod
    def _text(
        value: str,
        name: str,
        maximum_length: int,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > maximum_length
        ):
            raise ValueError(
                f"{name} must be non-empty and at most "
                f"{maximum_length} characters."
            )

        # Preserve exactly what the caller submitted,
        # including meaningful leading/trailing whitespace.
        return value

    @staticmethod
    def _aware_utc(
        value: datetime,
        name: str,
    ) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} must be timezone-aware."
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _prompt_digest(prompt: str) -> str:
        return sha256(
            prompt.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _require_presented(
        delivery: CourseTeachingDeliveryStateV01,
    ) -> None:
        if (
            delivery.status != "presentation_reported"
            or delivery.presentation is None
        ):
            raise ValueError(
                "A presentation_reported Trace is required "
                "before recording a student response."
            )

    def _decode(
        self,
        row,
        delivery: CourseTeachingDeliveryStateV01,
    ) -> StoredCourseLearningResponseV01:
        self._require_presented(delivery)

        trace = delivery.trace
        presentation = delivery.presentation

        if (
            row["trace_id"] != trace.trace_id
            or row["presentation_event_id"]
            != presentation.event_id
            or row["student_id"] != trace.student_id
            or row["course_id"] != trace.course_id
            or row["objective_id"] != trace.objective_id
        ):
            raise ValueError(
                "Stored student response does not match "
                "its Teaching Trace and Presentation Event."
            )

        if (
            row["activity_prompt_sha256"]
            != self._prompt_digest(row["activity_prompt"])
        ):
            raise ValueError(
                "Stored activity prompt digest mismatch."
            )

        self._identifier(
            row["activity_id"],
            "activity_id",
        )

        self._text(
            row["activity_prompt"],
            "activity_prompt",
            2000,
        )

        self._text(
            row["response_text"],
            "response_text",
            4000,
        )

        submitted_at = self._aware_utc(
            datetime.fromisoformat(
                row["submitted_at_utc"]
            ),
            "submitted_at",
        )

        if submitted_at < presentation.reported_at:
            raise ValueError(
                "Student response precedes "
                "its Presentation Event."
            )

        return StoredCourseLearningResponseV01(
            response_id=row["response_id"],
            trace_id=row["trace_id"],
            presentation_event_id=(
                row["presentation_event_id"]
            ),
            student_id=row["student_id"],
            course_id=row["course_id"],
            objective_id=row["objective_id"],
            activity_id=row["activity_id"],
            activity_prompt=row["activity_prompt"],
            response_text=row["response_text"],
            submitted_at=submitted_at,
        )

    def record_response(
        self,
        *,
        response_id: str,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        activity_id: str,
        activity_prompt: str,
        response_text: str,
        submitted_at: datetime,
    ) -> StoredCourseLearningResponseV01:
        """
        Persist the first response to an activity.

        An exact repeated request returns the existing record.
        A changed answer, prompt, or identity is a conflict.

        Caller-supplied text is not independently verified
        as authentic student input by this internal prototype.
        """

        for name, value in (
            ("response_id", response_id),
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
            ("activity_id", activity_id),
        ):
            self._identifier(value, name)

        self._text(
            activity_prompt,
            "activity_prompt",
            2000,
        )

        self._text(
            response_text,
            "response_text",
            4000,
        )

        submitted_at_utc = self._aware_utc(
            submitted_at,
            "submitted_at",
        )

        delivery = self._presentations.load_state(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        self._require_presented(delivery)

        presentation = delivery.presentation

        if submitted_at_utc < presentation.reported_at:
            raise ValueError(
                "Student response cannot precede "
                "the Presentation Event."
            )

        expected = {
            "response_id": response_id,
            "trace_id": trace_id,
            "presentation_event_id": presentation.event_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "activity_id": activity_id,
            "activity_prompt": activity_prompt,
            "activity_prompt_sha256": (
                self._prompt_digest(activity_prompt)
            ),
            "response_text": response_text,
            "submitted_at_utc": (
                submitted_at_utc.isoformat()
            ),
        }

        with self._session_factory() as session:
            with session.begin():
                session.execute(
                    sqlite_insert(
                        course_learning_responses_v01
                    )
                    .values(**expected)
                    .on_conflict_do_nothing()
                )

                row = session.execute(
                    select(course_learning_responses_v01)
                    .where(
                        course_learning_responses_v01.c.response_id
                        == response_id
                    )
                ).mappings().one_or_none()

                if row is None:
                    raise ValueError(
                        "This Teaching Trace already has "
                        "a response for the activity, or "
                        "the response ID is in conflict."
                    )

                if any(
                    row[name] != value
                    for name, value in expected.items()
                ):
                    raise ValueError(
                        "Student response conflicts with "
                        "the original submitted record."
                    )

        return self.load(
            response_id=response_id,
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

    def load(
        self,
        *,
        response_id: str,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> StoredCourseLearningResponseV01:
        """
        Recover one response under explicit expected scope.

        Scope matching does not authenticate the caller.
        """

        for name, value in (
            ("response_id", response_id),
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
        ):
            self._identifier(value, name)

        with self._session_factory() as session:
            row = session.execute(
                select(course_learning_responses_v01)
                .where(
                    course_learning_responses_v01.c.response_id
                    == response_id
                )
            ).mappings().one_or_none()

        if row is None:
            raise LookupError(
                "Student response was not found."
            )

        if (
            row["trace_id"] != trace_id
            or row["student_id"] != student_id
            or row["course_id"] != course_id
            or row["objective_id"] != objective_id
        ):
            raise ValueError(
                "Student response scope mismatch."
            )

        delivery = self._presentations.load_state(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        return self._decode(row, delivery)

"""
URPP Implementation 14B-2B-2.

Persist an application-reported presentation event for an
already stored, generated, course-grounded Professor turn.

This module:
- never generates teaching content;
- never edits the original generated Trace;
- never updates Student State or Assessment Evidence;
- does not authenticate the caller or verify actual display;
- does not create an Engine or production database schema.

presentation_reported means that a caller reported display.
It is not proof of student viewing, reading, or learning.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Table,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.repositories.course_teaching_trace_v01 import (
    CourseTeachingTraceRepositoryV01,
    StoredCourseTeachingTraceV01,
    course_teaching_traces_v01,
)


# Reuse the Teaching Trace metadata, NOT the Numeric
# Assessment Base.metadata. This allows an explicit FK
# to the existing generated Trace without adding a table
# to the Numeric schema initialization or readiness checks.
course_teaching_presentations_v01 = Table(
    "course_teaching_presentations_v01",
    course_teaching_traces_v01.metadata,

    Column(
        "trace_id",
        String(128),
        ForeignKey(
            "course_teaching_traces_v01.trace_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    ),
    Column(
        "event_id",
        String(128),
        nullable=False,
        unique=True,
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
        "reported_at_utc",
        String(48),
        nullable=False,
    ),
    Column(
        "surface",
        String(128),
        nullable=False,
    ),
    Column(
        "content_sha256",
        String(64),
        nullable=False,
    ),
)


@dataclass(frozen=True)
class StoredPresentationEventV01:
    """
    Durable statement supplied by an application caller.

    The event records what the application reported.
    It is not independently verified display telemetry.
    """

    event_id: str
    trace_id: str

    student_id: str
    course_id: str
    objective_id: str

    reported_at: datetime
    surface: str
    content_sha256: str


@dataclass(frozen=True)
class CourseTeachingDeliveryStateV01:
    """
    Recovered generation and presentation-report status.

    The original generated content remains inside trace.
    """

    trace: StoredCourseTeachingTraceV01

    status: Literal[
        "generated",
        "presentation_reported",
    ]

    presentation: StoredPresentationEventV01 | None


class CourseTeachingPresentationRepositoryV01:
    """
    Add one presentation report to an immutable generated Trace.

    The caller owns Engine lifecycle, database schema
    provisioning, authentication, and authorization.
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

        self._traces = CourseTeachingTraceRepositoryV01(
            session_factory
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
    def _content_digest(
        trace: StoredCourseTeachingTraceV01,
    ) -> str:
        return sha256(
            trace.result.completed_turn.content.encode("utf-8")
        ).hexdigest()

    def _decode_event(
        self,
        row,
        trace: StoredCourseTeachingTraceV01,
    ) -> StoredPresentationEventV01:
        """
        Check the stored event against the original Trace.

        An event is not allowed to change the associated
        student/course/objective or generated content.
        """

        if (
            row["trace_id"] != trace.trace_id
            or row["student_id"] != trace.student_id
            or row["course_id"] != trace.course_id
            or row["objective_id"] != trace.objective_id
        ):
            raise ValueError(
                "Presentation event scope does not match Trace."
            )

        if row["content_sha256"] != self._content_digest(trace):
            raise ValueError(
                "Presentation event content digest mismatch."
            )

        reported_at = self._aware_utc(
            datetime.fromisoformat(row["reported_at_utc"]),
            "reported_at",
        )

        if reported_at < trace.generated_at.astimezone(timezone.utc):
            raise ValueError(
                "Presentation event precedes generated Trace."
            )

        return StoredPresentationEventV01(
            event_id=row["event_id"],
            trace_id=row["trace_id"],
            student_id=row["student_id"],
            course_id=row["course_id"],
            objective_id=row["objective_id"],
            reported_at=reported_at,
            surface=row["surface"],
            content_sha256=row["content_sha256"],
        )

    def load_state(
        self,
        *,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> CourseTeachingDeliveryStateV01:
        """
        Recover a generated Trace and optional presentation event.

        Identifiers enforce matching scope, but do not
        authenticate the requesting caller.
        """

        trace = self._traces.load(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        with self._session_factory() as session:
            row = session.execute(
                select(course_teaching_presentations_v01)
                .where(
                    course_teaching_presentations_v01.c.trace_id
                    == trace_id
                )
            ).mappings().one_or_none()

        if row is None:
            return CourseTeachingDeliveryStateV01(
                trace=trace,
                status="generated",
                presentation=None,
            )

        event = self._decode_event(row, trace)

        return CourseTeachingDeliveryStateV01(
            trace=trace,
            status="presentation_reported",
            presentation=event,
        )

    def record_presentation(
        self,
        *,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        event_id: str,
        reported_at: datetime,
        surface: str,
    ) -> CourseTeachingDeliveryStateV01:
        """
        Record one application-reported presentation event.

        Same event ID and exact metadata: idempotent retry.
        Same Trace with changed metadata: reject conflict.
        Same event ID for another Trace: reject conflict.

        This method must only be called after the application
        has actually attempted to present the stored content.
        It cannot itself verify whether display occurred.
        """

        for name, value in (
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
            ("event_id", event_id),
            ("surface", surface),
        ):
            self._identifier(value, name)

        reported_at_utc = self._aware_utc(
            reported_at,
            "reported_at",
        )

        # A generated Trace is a prerequisite. This rejects
        # missing or mismatched student/course/objective scope.
        trace = self._traces.load(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        if reported_at_utc < trace.generated_at.astimezone(timezone.utc):
            raise ValueError(
                "Presentation cannot precede generation."
            )

        expected = {
            "trace_id": trace_id,
            "event_id": event_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "reported_at_utc": reported_at_utc.isoformat(),
            "surface": surface,
            "content_sha256": self._content_digest(trace),
        }

        # The Trace has one presentation event at most.
        # SQLite's unique constraints handle competing inserts.
        # A conflict is followed by checking the persisted row
        # rather than overwriting it.
        with self._session_factory() as session:
            with session.begin():
                session.execute(
                    sqlite_insert(
                        course_teaching_presentations_v01
                    )
                    .values(**expected)
                    .on_conflict_do_nothing()
                )

                row = session.execute(
                    select(course_teaching_presentations_v01)
                    .where(
                        course_teaching_presentations_v01.c.trace_id
                        == trace_id
                    )
                ).mappings().one_or_none()

                if row is None:
                    raise ValueError(
                        "Presentation event ID is already "
                        "used for another Trace."
                    )

                if any(
                    row[name] != value
                    for name, value in expected.items()
                ):
                    raise ValueError(
                        "Presentation event conflicts with "
                        "the original reported event."
                    )

        # Re-read from storage; do not return a fabricated
        # success result from the caller's in-memory values.
        return self.load_state(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

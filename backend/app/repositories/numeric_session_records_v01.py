"""
URPP Design 01D — Persistent Numeric Session Records V0.1.

Stores durable session identity.

Assignment and Attempt records remain the source of truth
for session progress.

This is an internal persistence prototype. It does not
authenticate users, authorize access, or implement migrations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import String, select

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)


class NumericTeachingSessionRowV01(Base):
    __tablename__ = "numeric_teaching_sessions_v01"

    session_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    student_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    course_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    objective_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    started_at_utc: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
    )


@dataclass(frozen=True)
class StoredNumericSessionV01:
    session_id: str
    student_id: str
    course_id: str
    objective_id: str
    started_at: datetime


class NumericSessionRecordRepositoryV01:
    """
    Persist and retrieve a session's identity.

    Session progress is reconstructed from stored Assignment
    records rather than maintained as a second mutable list.
    """

    def __init__(
        self,
        assessment_repository: AssessmentRecordRepositoryV02,
    ) -> None:
        self._session_factory = (
            assessment_repository._session_factory
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
    def _aware(value: datetime, name: str) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} must be timezone-aware."
            )

        return value

    @staticmethod
    def _record(
        row: NumericTeachingSessionRowV01,
    ) -> StoredNumericSessionV01:
        return StoredNumericSessionV01(
            session_id=row.session_id,
            student_id=row.student_id,
            course_id=row.course_id,
            objective_id=row.objective_id,
            started_at=datetime.fromisoformat(
                row.started_at_utc
            ),
        )

    def register(
        self,
        *,
        session_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        started_at: datetime,
    ) -> StoredNumericSessionV01:
        """
        Create a durable session or return an existing one
        with exactly the same identity and scope.
        """

        values = {
            "session_id": session_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
        }

        for name, value in values.items():
            self._identifier(value, name)

        started_at_utc = self._aware(
            started_at,
            "started_at",
        ).astimezone(timezone.utc).isoformat()

        with self._session_factory() as session:
            with session.begin():
                row = session.get(
                    NumericTeachingSessionRowV01,
                    session_id,
                )

                if row is None:
                    row = NumericTeachingSessionRowV01(
                        session_id=session_id,
                        student_id=student_id,
                        course_id=course_id,
                        objective_id=objective_id,
                        started_at_utc=started_at_utc,
                    )

                    session.add(row)
                    session.flush()

                if (
                    row.student_id != student_id
                    or row.course_id != course_id
                    or row.objective_id != objective_id
                ):
                    raise ValueError(
                        "Existing session has a different "
                        "student, course, or objective."
                    )

                record = self._record(row)

        return record

    def load(
        self,
        *,
        session_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> StoredNumericSessionV01:
        """
        Load a session and verify its requested scope.

        The scope arguments are not proof of authentication.
        """

        for name, value in (
            ("session_id", session_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
        ):
            self._identifier(value, name)

        with self._session_factory() as session:
            row = session.get(
                NumericTeachingSessionRowV01,
                session_id,
            )

            if row is None:
                raise LookupError(
                    "Numeric teaching session was not found."
                )

            if (
                row.student_id != student_id
                or row.course_id != course_id
                or row.objective_id != objective_id
            ):
                raise ValueError(
                    "Stored session does not match "
                    "the requested scope."
                )

            return self._record(row)

    def list_assignment_ids(
        self,
        *,
        session_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> tuple[str, ...]:
        """
        List assignment IDs belonging to this stored session.

        Sorting is deterministic so state reconstruction uses
        the same input ordering after a process restart.
        """

        self.load(
            session_id=session_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        with self._session_factory() as session:
            statement = (
                select(NumericAssignmentRow.assignment_id)
                .where(
                    NumericAssignmentRow.session_id == session_id,
                    NumericAssignmentRow.student_id == student_id,
                    NumericAssignmentRow.course_id == course_id,
                    NumericAssignmentRow.objective_id == objective_id,
                )
                .order_by(
                    NumericAssignmentRow.assigned_at_utc,
                    NumericAssignmentRow.assignment_id,
                )
            )

            return tuple(
                session.scalars(statement).all()
            )

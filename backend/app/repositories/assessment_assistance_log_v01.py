"""
URPP Implementation 13E-3A.

Assessment Assistance Event Log V0.1.

Record application-reported provision of assessment
help while a Numeric Assignment is pending.

This module does NOT:
- authenticate the application caller;
- prove that a student actually saw the content;
- establish absence of external help;
- assign an assistance_level to a Student Attempt;
- create eligible mastery evidence.

The application must eventually own and protect the
entry point that calls record_application_assistance().
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    select,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.repositories.assessment_records_v02 import Base

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)


class AssessmentAssistanceKindV01(str, Enum):
    HINT = "hint"
    SOLUTION = "solution"


@dataclass(frozen=True)
class RecordedAssessmentAssistanceV01:
    """
    An application-reported assistance event.

    source='application_reported' describes the current
    provenance limitation; it is not a trust certificate.
    """

    event_id: str
    assignment_id: str
    student_id: str
    session_id: str

    kind: AssessmentAssistanceKindV01

    content_sha256: str
    occurred_at: datetime

    source: str = "application_reported"


class AssessmentAssistanceRowV01(Base):
    __tablename__ = "assessment_assistance_events_v01"

    event_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    assignment_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey(
            "numeric_assignments_v01.assignment_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    student_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    session_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    occurred_at_utc: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('hint', 'solution')",
            name="assessment_assistance_kind_v01",
        ),
        CheckConstraint(
            "source = 'application_reported'",
            name="assessment_assistance_source_v01",
        ),
    )


class AssessmentAssistanceLogRepositoryV01:
    """
    Internal persistence for application-reported help.

    This repository is not a public or authenticated API.
    Caller identity and actual content presentation must
    be established by a future application integration.
    """

    def __init__(
        self,
        session_factory,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory

        self._clock = (
            clock
            if clock is not None
            else lambda: datetime.now(timezone.utc)
        )

    @staticmethod
    def _require_identifier(
        value: str,
        *,
        name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{name} must be a nonempty string."
            )

        return value

    @staticmethod
    def _require_assignment_scope(
        assignment: NumericAssignmentRow | None,
        *,
        student_id: str,
        session_id: str,
    ) -> NumericAssignmentRow:
        if assignment is None:
            raise LookupError(
                "Numeric Assignment was not found."
            )

        if (
            assignment.student_id != student_id
            or assignment.session_id != session_id
        ):
            raise ValueError(
                "Assistance event does not match "
                "the Assignment student and session."
            )

        return assignment

    @staticmethod
    def _from_row(
        row: AssessmentAssistanceRowV01,
    ) -> RecordedAssessmentAssistanceV01:
        return RecordedAssessmentAssistanceV01(
            event_id=row.event_id,
            assignment_id=row.assignment_id,
            student_id=row.student_id,
            session_id=row.session_id,
            kind=AssessmentAssistanceKindV01(
                row.kind
            ),
            content_sha256=row.content_sha256,
            occurred_at=datetime.fromisoformat(
                row.occurred_at_utc
            ),
            source=row.source,
        )

    def record_application_assistance(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
        kind: AssessmentAssistanceKindV01,
        content: str,
    ) -> RecordedAssessmentAssistanceV01:
        """
        Record help explicitly reported by the application.

        The caller must invoke this method only after its
        own presentation operation. This repository cannot
        establish that presentation actually occurred.

        An event cannot be added through this method
        after the Assignment has been completed.
        """

        assignment_id = self._require_identifier(
            assignment_id,
            name="assignment_id",
        )

        student_id = self._require_identifier(
            student_id,
            name="student_id",
        )

        session_id = self._require_identifier(
            session_id,
            name="session_id",
        )

        if not isinstance(
            kind,
            AssessmentAssistanceKindV01,
        ):
            raise TypeError(
                "kind must be AssessmentAssistanceKindV01."
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                "Assistance content must be a nonempty string."
            )

        occurred_at = self._clock()

        if (
            not isinstance(occurred_at, datetime)
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise ValueError(
                "Assistance clock must return "
                "a timezone-aware datetime."
            )

        with self._session_factory() as session:
            with session.begin():
                assignment = self._require_assignment_scope(
                    session.get(
                        NumericAssignmentRow,
                        assignment_id,
                    ),
                    student_id=student_id,
                    session_id=session_id,
                )

                if (
                    assignment.status != "pending"
                    or assignment.completed_attempt_id is not None
                ):
                    raise ValueError(
                        "Assistance cannot be recorded "
                        "after Assignment completion."
                    )

                assigned_at = datetime.fromisoformat(
                    assignment.assigned_at_utc
                )

                if occurred_at < assigned_at:
                    raise ValueError(
                        "Assistance time predates Assignment."
                    )

                record = RecordedAssessmentAssistanceV01(
                    event_id=uuid4().hex,
                    assignment_id=assignment_id,
                    student_id=student_id,
                    session_id=session_id,
                    kind=kind,
                    content_sha256=sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    occurred_at=occurred_at,
                )

                session.add(
                    AssessmentAssistanceRowV01(
                        event_id=record.event_id,
                        assignment_id=record.assignment_id,
                        student_id=record.student_id,
                        session_id=record.session_id,
                        kind=record.kind.value,
                        content_sha256=record.content_sha256,
                        occurred_at_utc=(
                            record.occurred_at.isoformat()
                        ),
                        source=record.source,
                    )
                )

        return record

    def list_assistance_for_assignment(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
    ) -> tuple[RecordedAssessmentAssistanceV01, ...]:
        """
        Recover historical assistance reports for one
        Assignment within the supplied student/session scope.

        Reading records does not turn them into
        eligible student-performance evidence.
        """

        assignment_id = self._require_identifier(
            assignment_id,
            name="assignment_id",
        )

        student_id = self._require_identifier(
            student_id,
            name="student_id",
        )

        session_id = self._require_identifier(
            session_id,
            name="session_id",
        )

        with self._session_factory() as session:
            self._require_assignment_scope(
                session.get(
                    NumericAssignmentRow,
                    assignment_id,
                ),
                student_id=student_id,
                session_id=session_id,
            )

            rows = session.scalars(
                select(AssessmentAssistanceRowV01)
                .where(
                    AssessmentAssistanceRowV01.assignment_id
                    == assignment_id
                )
            ).all()

            result = tuple(
                sorted(
                    (
                        self._from_row(row)
                        for row in rows
                    ),
                    key=lambda record: (
                        record.occurred_at,
                        record.event_id,
                    ),
                )
            )

            return result

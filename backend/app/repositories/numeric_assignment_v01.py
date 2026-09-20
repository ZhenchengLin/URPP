"""
URPP Design 01D — Persistent Numeric Assignment V0.1.

Stores an assessment assignment and its submitted attempt.

The assignment is linked to:
- one student and teaching session;
- one course and objective;
- one assessment item and immutable item revision;
- at most one completed student attempt.

Submission inserts the attempt and marks the assignment complete
inside the same database transaction.

This is an INTERNAL persistence service.

It does not authenticate callers, prove student authorship,
or provide a public submission API.

The caller must supply an AssessmentDeliveryV01 created by the
trusted, internal teaching-turn workflow. This module cannot
independently prove that a caller supplied a genuine delivery.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    update,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.repositories.assessment_records_v02 import (
    AssessmentItemRow,
    AssessmentRecordRepositoryV02,
    Base,
    StudentAttemptRow,
)

from app.repositories.numeric_session_records_v01 import (
    NumericTeachingSessionRowV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    StudentAttemptV02,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    AssessmentDeliveryV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
)


class NumericAssignmentRow(Base):
    __tablename__ = "numeric_assignments_v01"

    assignment_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    decision_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
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

    session_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    assessment_item_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    item_revision: Mapped[int] = mapped_column(
        nullable=False,
    )

    assigned_at_utc: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    # Non-NULL only while this assignment is pending.
    # UNIQUE allows many completed rows with NULL here,
    # but only one pending row for each session.
    pending_session_key: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        nullable=True,
    )

    # NULL remains representable for historical database rows.
    # New Assignments always use a registered Session.
    # Strict assignments populate this with session_id.
    registered_session_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    completed_attempt_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey(
            "student_attempts_v02.attempt_id",
            ondelete="RESTRICT",
        ),
        unique=True,
        nullable=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [
                'registered_session_id',
                'student_id',
                'course_id',
                'objective_id',
            ],
            [
                'numeric_teaching_sessions_v01.session_id',
                'numeric_teaching_sessions_v01.student_id',
                'numeric_teaching_sessions_v01.course_id',
                'numeric_teaching_sessions_v01.objective_id',
            ],
            ondelete='RESTRICT',
            onupdate='RESTRICT',
            name='numeric_assignment_registered_session_fk_v01',
        ),
        CheckConstraint(
            'registered_session_id IS NULL '
            'OR registered_session_id = session_id',
            name='numeric_assignment_registered_session_match_v01',
        ),
        UniqueConstraint(
            'session_id',
            'decision_id',
            name='numeric_assignment_session_decision_unique',
        ),
        ForeignKeyConstraint(
            [
                "assessment_item_id",
                "item_revision",
            ],
            [
                "assessment_items_v02.assessment_item_id",
                "assessment_items_v02.revision",
            ],
        ),
        CheckConstraint(
            "("
            "status = 'pending' "
            "AND completed_attempt_id IS NULL "
            "AND pending_session_key IS NOT NULL "
            "AND pending_session_key = session_id"
            ") OR ("
            "status = 'completed' "
            "AND completed_attempt_id IS NOT NULL "
            "AND pending_session_key IS NULL"
            ")",
            name="numeric_assignment_status_consistency",
        ),
    )


@dataclass(frozen=True)
class StoredNumericAssignmentV01:
    assignment_id: str
    decision_id: str

    student_id: str
    course_id: str
    objective_id: str
    session_id: str

    assessment_item_id: str
    item_revision: int

    assigned_at: datetime

    status: str
    completed_attempt_id: str | None


class NumericAssignmentRepositoryV01:
    """
    Persist assignments and accept exactly one response per assignment.

    All writes are performed using the same SQLAlchemy session and
    database transaction.

    The student_id and session_id arguments are INTERNAL scope
    parameters. A future authenticated application layer must derive
    them from verified server-side session context.
    """

    def __init__(
        self,
        assessment_repository: AssessmentRecordRepositoryV02,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:

        self._assessment_repository = assessment_repository

        # The existing repository owns the SQLAlchemy sessionmaker.
        # Reusing it ensures assignments and attempts are written
        # to the same database and can share one transaction.
        self._session_factory = (
            assessment_repository._session_factory
        )

        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

    @staticmethod
    def _require_identifier(
        value: str,
        *,
        name: str,
    ) -> str:

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{name} must be a non-empty string."
            )

        return value

    @staticmethod
    def _require_aware_time(
        value: datetime,
        *,
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

        return value

    @classmethod
    def _as_utc_iso(
        cls,
        value: datetime,
        *,
        name: str,
    ) -> str:

        aware = cls._require_aware_time(
            value,
            name=name,
        )

        return aware.astimezone(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _to_record(
        row: NumericAssignmentRow,
    ) -> StoredNumericAssignmentV01:

        return StoredNumericAssignmentV01(
            assignment_id=row.assignment_id,
            decision_id=row.decision_id,
            student_id=row.student_id,
            course_id=row.course_id,
            objective_id=row.objective_id,
            session_id=row.session_id,
            assessment_item_id=row.assessment_item_id,
            item_revision=row.item_revision,
            assigned_at=datetime.fromisoformat(
                row.assigned_at_utc
            ),
            status=row.status,
            completed_attempt_id=row.completed_attempt_id,
        )

    def issue_assignment(
        self,
        delivery: AssessmentDeliveryV01,
        *,
        student_id: str,
        course_id: str,
        objective_id: str,
        session_id: str,
    ) -> StoredNumericAssignmentV01:
        """
        Persist an internally produced structured assessment delivery.

        The item and prompt are checked against the stored revision.

        This method does not authenticate the caller or attest that
        the delivery was genuinely issued by an Orchestrator.
        """

        if not isinstance(
            delivery,
            AssessmentDeliveryV01,
        ):
            raise TypeError(
                "delivery must be AssessmentDeliveryV01."
            )

        student_id = self._require_identifier(
            student_id,
            name="student_id",
        )

        course_id = self._require_identifier(
            course_id,
            name="course_id",
        )

        objective_id = self._require_identifier(
            objective_id,
            name="objective_id",
        )

        session_id = self._require_identifier(
            session_id,
            name="session_id",
        )

        if delivery.selected_action not in ASSESSMENT_ACTIONS:
            raise ValueError(
                "Delivery must contain an assessment action."
            )

        assigned_at_utc = self._as_utc_iso(
            delivery.assigned_at,
            name="assigned_at",
        )

        with self._session_factory() as session:
            with session.begin():

                # Local import avoids the module import cycle:
                # the Session Repository already imports
                # NumericAssignmentRow from this module.
                from app.repositories.numeric_session_records_v01 import (
                    NumericTeachingSessionRowV01,
                )

                registered = session.get(
                    NumericTeachingSessionRowV01,
                    session_id,
                )

                if registered is None:
                    raise LookupError(
                        "Registered teaching session was not found."
                    )

                if (
                    registered.student_id != student_id
                    or registered.course_id != course_id
                    or registered.objective_id != objective_id
                ):
                    raise ValueError(
                        "Registered teaching session scope "
                        "does not match the assignment."
                    )

                session_started_at = datetime.fromisoformat(
                    registered.started_at_utc
                )

                if delivery.assigned_at < session_started_at:
                    raise ValueError(
                        "Assignment predates its registered "
                        "teaching session."
                    )

                item_row = session.get(
                    AssessmentItemRow,
                    (
                        delivery.assessment_item_id,
                        delivery.item_revision,
                    ),
                )

                if item_row is None:
                    raise LookupError(
                        "Assigned assessment item revision was not found."
                    )

                if item_row.item_type != "numeric":
                    raise TypeError(
                        "Only numeric assessment items can be assigned."
                    )

                item = AssessmentItemV02.model_validate(
                    item_row.payload
                )

                if (
                    item.course_id != course_id
                    or item.objective_id != objective_id
                    or item.assessment_item_id
                    != delivery.assessment_item_id
                ):
                    raise ValueError(
                        "Assignment does not match "
                        "the stored assessment scope."
                    )

                if not item.alignment_verified:
                    raise ValueError(
                        "Assessment objective alignment is not verified."
                    )

                if item.prompt != delivery.prompt:
                    raise ValueError(
                        "Delivery prompt does not match the stored item."
                    )

                if session.get(
                    NumericAssignmentRow,
                    delivery.assignment_id,
                ) is not None:
                    raise ValueError(
                        "Assignment ID already exists."
                    )

                row = NumericAssignmentRow(
                    assignment_id=delivery.assignment_id,
                    decision_id=delivery.decision_id,
                    student_id=student_id,
                    course_id=course_id,
                    objective_id=objective_id,
                    session_id=session_id,
                    assessment_item_id=delivery.assessment_item_id,
                    item_revision=delivery.item_revision,
                    assigned_at_utc=assigned_at_utc,
                    status="pending",
                    pending_session_key=session_id,
                    registered_session_id=session_id,
                    completed_attempt_id=None,
                )

                session.add(row)

                session.flush()

                record = self._to_record(row)

        return record

    def load_assignment(
        self,
        assignment_id: str,
    ) -> StoredNumericAssignmentV01:

        assignment_id = self._require_identifier(
            assignment_id,
            name="assignment_id",
        )

        with self._session_factory() as session:

            row = session.get(
                NumericAssignmentRow,
                assignment_id,
            )

            if row is None:
                raise LookupError(
                    "Numeric assignment was not found."
                )

            return self._to_record(row)

    def submit_numeric_response(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
        response_text: str,
    ) -> StudentAttemptV02:
        """
        Atomically save one attempt and complete its assignment.

        The caller supplies only:
        - assignment ID;
        - internal student/session scope;
        - response text.

        Course, objective, item revision, attempt ID, source message
        ID, response group, and submission time are server-generated
        or derived from the stored assignment.

        Assistance level and prior solution exposure are UNKNOWN
        rather than falsely asserted as independent work.
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

        if (
            not isinstance(response_text, str)
            or not response_text.strip()
        ):
            raise ValueError(
                "response_text must be a non-empty string."
            )

        with self._session_factory() as session:
            with session.begin():

                assignment = session.get(
                    NumericAssignmentRow,
                    assignment_id,
                )

                if assignment is None:
                    raise LookupError(
                        "Numeric assignment was not found."
                    )

                if (
                    assignment.student_id != student_id
                    or assignment.session_id != session_id
                ):
                    raise ValueError(
                        "Assignment does not match "
                        "the requested student and session."
                    )

                if (
                    assignment.status != "pending"
                    or assignment.completed_attempt_id is not None
                ):
                    raise ValueError(
                        "Assignment has already been completed."
                    )

                submitted_at = self._require_aware_time(
                    self._clock(),
                    name="submitted_at",
                )

                assigned_at = datetime.fromisoformat(
                    assignment.assigned_at_utc
                )

                if submitted_at < assigned_at:
                    raise ValueError(
                        "Submission time predates assignment."
                    )

                attempt_id = uuid4().hex

                attempt = StudentAttemptV02(
                    attempt_id=attempt_id,
                    student_id=assignment.student_id,
                    course_id=assignment.course_id,
                    session_id=assignment.session_id,
                    objective_id=assignment.objective_id,
                    assessment_item_id=(
                        assignment.assessment_item_id
                    ),
                    source_message_id=(
                        f"submission-{uuid4().hex}"
                    ),
                    response_group_id=(
                        f"assignment-{assignment.assignment_id}"
                    ),
                    response_text=response_text,
                    assistance_level=None,
                    prior_solution_exposure=None,
                    novelty="unknown",
                    submitted_at=submitted_at,
                )

                session.add(
                    StudentAttemptRow(
                        attempt_id=attempt.attempt_id,
                        assessment_item_id=(
                            assignment.assessment_item_id
                        ),
                        item_revision=assignment.item_revision,
                        payload=attempt.model_dump(
                            mode="json"
                        ),
                    )
                )

                # Insert first so the completed_attempt_id foreign
                # key can reference an existing attempt.
                # This insert is not committed independently.
                session.flush()

                # Conditional UPDATE is the database-level
                # claim on this pending assignment.
                #
                # If another transaction has already completed
                # the assignment, this UPDATE cannot succeed.
                result = session.execute(
                    update(NumericAssignmentRow)
                    .where(
                        NumericAssignmentRow.assignment_id
                        == assignment_id,
                        NumericAssignmentRow.status
                        == "pending",
                        NumericAssignmentRow.completed_attempt_id
                        .is_(None),
                    )
                    .values(
                        status="completed",
                        pending_session_key=None,
                        completed_attempt_id=attempt.attempt_id,
                    )
                )

                if result.rowcount != 1:
                    raise ValueError(
                        "Assignment was completed by "
                        "another submission."
                    )

                # The transaction commits only after both
                # the attempt INSERT and assignment UPDATE succeed.

        return attempt

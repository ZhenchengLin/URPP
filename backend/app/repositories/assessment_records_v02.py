"""
URPP Design 01C — Versioned Assessment Repository V0.2.

Stores immutable assessment-item revisions and student attempts.

This is an internal persistence prototype. It does not
authenticate users, authorize reviewers, or verify that submitted
records came from trusted application services.

Schema migrations and PostgreSQL deployment are separate tasks.
"""

from sqlalchemy import (
    JSON,
    ForeignKeyConstraint,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    StudentAttemptV02,
)

from app.services.assessment.open_response_models_v02 import (
    OpenResponseAssessmentItemV02,
)


AssessmentItemType = (
    AssessmentItemV02 | OpenResponseAssessmentItemV02
)


class Base(DeclarativeBase):
    pass


class AssessmentItemRow(Base):
    __tablename__ = "assessment_items_v02"

    assessment_item_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    revision: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )


class StudentAttemptRow(Base):
    __tablename__ = "student_attempts_v02"

    attempt_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    assessment_item_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    item_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["assessment_item_id", "item_revision"],
            [
                "assessment_items_v02.assessment_item_id",
                "assessment_items_v02.revision",
            ],
        ),
    )


class AssessmentRecordRepositoryV02:
    """
    Store versioned items and attempts.

    The caller supplies a SQLAlchemy sessionmaker.
    Authentication and authorization are the responsibility
    of a future trusted application-service layer.
    """

    def __init__(self, session_factory):
        self._session_factory = session_factory

    @staticmethod
    def _validate_revision(revision: int) -> None:
        if type(revision) is not int or revision < 1:
            raise ValueError(
                "Assessment revision must be a positive integer."
            )

    def save_item(
        self,
        item: AssessmentItemType,
        *,
        revision: int,
    ) -> None:
        """
        Save a new item revision.

        An existing revision cannot be overwritten.
        A revised rubric must use a new revision number.
        """

        self._validate_revision(revision)

        if isinstance(item, AssessmentItemV02):
            item_type = "numeric"
        elif isinstance(item, OpenResponseAssessmentItemV02):
            item_type = "open_response"
        else:
            raise TypeError("Unsupported assessment item type.")

        with self._session_factory() as session:
            existing = session.get(
                AssessmentItemRow,
                (item.assessment_item_id, revision),
            )

            if existing is not None:
                raise ValueError(
                    "Assessment item revision already exists "
                    "and cannot be overwritten."
                )

            session.add(
                AssessmentItemRow(
                    assessment_item_id=item.assessment_item_id,
                    revision=revision,
                    item_type=item_type,
                    payload=item.model_dump(mode="json"),
                )
            )

            session.commit()

    def load_item(
        self,
        assessment_item_id: str,
        *,
        revision: int,
    ) -> AssessmentItemType:
        """Load the exact saved version of an assessment item."""

        self._validate_revision(revision)

        with self._session_factory() as session:
            row = session.get(
                AssessmentItemRow,
                (assessment_item_id, revision),
            )

            if row is None:
                raise LookupError(
                    "Assessment item revision was not found."
                )

            if row.item_type == "numeric":
                return AssessmentItemV02.model_validate(
                    row.payload
                )

            if row.item_type == "open_response":
                return OpenResponseAssessmentItemV02.model_validate(
                    row.payload
                )

            raise ValueError(
                "Stored assessment item has an unknown type."
            )

    def save_attempt(
        self,
        attempt: StudentAttemptV02,
        *,
        item_revision: int,
    ) -> None:
        """
        Save an attempt linked to a specific item revision.

        The stored revision cannot later be changed by saving
        another attempt with the same attempt_id.
        """

        self._validate_revision(item_revision)

        item = self.load_item(
            attempt.assessment_item_id,
            revision=item_revision,
        )

        if (
            item.course_id != attempt.course_id
            or item.objective_id != attempt.objective_id
            or item.assessment_item_id
            != attempt.assessment_item_id
        ):
            raise ValueError(
                "Attempt does not match the stored assessment item."
            )

        with self._session_factory() as session:
            if session.get(
                StudentAttemptRow,
                attempt.attempt_id,
            ) is not None:
                raise ValueError(
                    "Attempt ID already exists and cannot be reused."
                )

            session.add(
                StudentAttemptRow(
                    attempt_id=attempt.attempt_id,
                    assessment_item_id=attempt.assessment_item_id,
                    item_revision=item_revision,
                    payload=attempt.model_dump(mode="json"),
                )
            )

            session.commit()

    def load_attempt(
        self,
        attempt_id: str,
    ) -> tuple[StudentAttemptV02, int]:
        """Return the original attempt and its bound item revision."""

        with self._session_factory() as session:
            row = session.get(
                StudentAttemptRow,
                attempt_id,
            )

            if row is None:
                raise LookupError("Student attempt was not found.")

            attempt = StudentAttemptV02.model_validate(
                row.payload
            )

            return attempt, row.item_revision

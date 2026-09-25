"""
URPP Implementation 13D-1C3.

Internal SQLite-compatible Transfer Review Decision Repository.

The repository records claims; it does not authenticate
reviewers or grant Transfer Assessment delivery permission.

Existing decision IDs cannot be overwritten through this API.
There is no update, delete, or is_approved method.
"""

from sqlalchemy import (
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    select,
)

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.repositories.assessment_records_v02 import (
    AssessmentItemRow,
    Base,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    fingerprint_assessment_item_v01,
)

from app.services.assessment.transfer_review_decision_v01 import (
    TransferReviewDecisionV01,
)


class TransferReviewDecisionRow(Base):
    __tablename__ = "transfer_review_decisions_v01"

    decision_id: Mapped[str] = mapped_column(
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
            ondelete="RESTRICT",
        ),
    )


class TransferReviewDecisionRepositoryV01:
    """
    Append-only repository for internal review-decision records.

    The supplied session factory must use a database where
    the existing assessment-item tables and this table exist.
    """

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def save_decision(
        self,
        decision: TransferReviewDecisionV01,
    ) -> None:
        """
        Save a new decision only if its referenced item
        revision exists and matches the recorded fingerprint.

        This method does not verify reviewer authority.
        """

        if not isinstance(
            decision,
            TransferReviewDecisionV01,
        ):
            raise TypeError(
                "decision must be TransferReviewDecisionV01."
            )

        with self._session_factory() as session:
            existing = session.get(
                TransferReviewDecisionRow,
                decision.decision_id,
            )

            if existing is not None:
                raise ValueError(
                    "Transfer review decision ID already exists "
                    "and cannot be overwritten."
                )

            item_row = session.get(
                AssessmentItemRow,
                (
                    decision.assessment_item_id,
                    decision.item_revision,
                ),
            )

            if item_row is None:
                raise LookupError(
                    "Referenced Assessment Item revision "
                    "was not found."
                )

            if item_row.item_type != "numeric":
                raise ValueError(
                    "Transfer review decision requires "
                    "a numeric Assessment Item."
                )

            item = AssessmentItemV02.model_validate(
                item_row.payload
            )

            if (
                item.course_id != decision.course_id
                or item.objective_id != decision.objective_id
            ):
                raise ValueError(
                    "Transfer review decision does not match "
                    "the stored Assessment Item scope."
                )

            if (
                fingerprint_assessment_item_v01(item)
                != decision.item_content_sha256
            ):
                raise ValueError(
                    "Transfer review decision does not match "
                    "the stored Assessment Item content."
                )

            session.add(
                TransferReviewDecisionRow(
                    decision_id=decision.decision_id,
                    assessment_item_id=(
                        decision.assessment_item_id
                    ),
                    item_revision=decision.item_revision,
                    payload=decision.model_dump(mode="json"),
                )
            )

            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()

                raise ValueError(
                    "Transfer review decision could not be "
                    "inserted; duplicate ID or invalid item "
                    "reference."
                ) from exc

    def load_decision(
        self,
        decision_id: str,
    ) -> TransferReviewDecisionV01:
        """Load one recorded decision by its immutable ID."""

        with self._session_factory() as session:
            row = session.get(
                TransferReviewDecisionRow,
                decision_id,
            )

            if row is None:
                raise LookupError(
                    "Transfer review decision was not found."
                )

            return TransferReviewDecisionV01.model_validate(
                row.payload
            )

    def list_decisions_for_item(
        self,
        assessment_item_id: str,
        *,
        item_revision: int,
    ) -> tuple[TransferReviewDecisionV01, ...]:
        """
        Return recorded decisions for one exact item revision.

        This is historical retrieval, NOT an approval lookup.
        An APPROVE outcome alone must not enable delivery.
        """

        if type(item_revision) is not int or item_revision < 1:
            raise ValueError(
                "Assessment revision must be a positive integer."
            )

        with self._session_factory() as session:
            rows = session.scalars(
                select(TransferReviewDecisionRow)
                .where(
                    TransferReviewDecisionRow.assessment_item_id
                    == assessment_item_id,
                    TransferReviewDecisionRow.item_revision
                    == item_revision,
                )
                .order_by(TransferReviewDecisionRow.decision_id)
            ).all()

            decisions = [
                TransferReviewDecisionV01.model_validate(
                    row.payload
                )
                for row in rows
            ]

            decisions.sort(
                key=lambda decision: (
                    decision.decided_at,
                    decision.decision_id,
                )
            )

            return tuple(decisions)

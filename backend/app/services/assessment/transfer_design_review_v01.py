"""
URPP Implementation 13D-1B.

A content-bound Transfer Design Review draft.

This module records the information needed for a future
review. It does not approve an item, authenticate a
reviewer, or grant eligibility for Transfer Assessment.
"""

from datetime import datetime
from hashlib import sha256
import json
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)


NonBlankTextV01 = Annotated[
    str,
    Field(min_length=1),
]


class TransferDesignReviewDraftV01(BaseModel):
    """
    An unapproved design-review draft for one item revision.

    The item fingerprint binds this draft to the complete
    serialized AssessmentItemV02 at the time of creation.

    This record cannot establish approval or reviewer authority.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    assessment_item_id: NonBlankTextV01

    item_revision: int = Field(
        ge=1,
        strict=True,
    )

    course_id: NonBlankTextV01

    objective_id: NonBlankTextV01

    item_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    # The learner's prior instructional or practice setting.
    source_learning_context: NonBlankTextV01

    # The setting in which the proposed transfer item is used.
    target_application_context: NonBlankTextV01

    # Specific differences between the source and target tasks.
    changed_context_factors: tuple[
        NonBlankTextV01,
        ...
    ] = Field(min_length=1)

    # Knowledge or principle that should remain applicable.
    invariant_knowledge: NonBlankTextV01

    # Reasoning required to recognize and apply that principle.
    required_transfer_reasoning: NonBlankTextV01

    # How the learner might answer without demonstrating transfer.
    plausible_non_transfer_path: NonBlankTextV01

    # Questions a future reviewer must resolve.
    review_questions: tuple[
        NonBlankTextV01,
        ...
    ] = Field(min_length=1)

    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_timezone(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "created_at must be timezone-aware."
            )

        return value


def fingerprint_assessment_item_v01(
    item: AssessmentItemV02,
) -> str:
    """
    Compute a deterministic fingerprint of the complete
    current AssessmentItemV02 content.

    This is a change-detection fingerprint, not a
    digital signature or proof of trusted item origin.
    """

    if not isinstance(item, AssessmentItemV02):
        raise TypeError(
            "item must be AssessmentItemV02."
        )

    serialized = json.dumps(
        item.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def create_transfer_design_review_draft_v01(
    *,
    item: AssessmentItemV02,
    item_revision: int,
    source_learning_context: str,
    target_application_context: str,
    changed_context_factors: tuple[str, ...],
    invariant_knowledge: str,
    required_transfer_reasoning: str,
    plausible_non_transfer_path: str,
    review_questions: tuple[str, ...],
    created_at: datetime,
) -> TransferDesignReviewDraftV01:
    """
    Construct an unapproved draft for a transfer-tagged
    Assessment Item.

    The supplied item and revision must eventually come
    from an authoritative item repository. This function
    does not independently verify their database origin.
    """

    if not isinstance(item, AssessmentItemV02):
        raise TypeError(
            "item must be AssessmentItemV02."
        )

    if item.evidence_type != EvidenceType.TRANSFER_ATTEMPT:
        raise ValueError(
            "Transfer design review requires "
            "a transfer-tagged Assessment Item."
        )

    if not item.alignment_verified:
        raise ValueError(
            "Assessment objective alignment is not verified."
        )

    return TransferDesignReviewDraftV01(
        assessment_item_id=item.assessment_item_id,
        item_revision=item_revision,
        course_id=item.course_id,
        objective_id=item.objective_id,
        item_content_sha256=(
            fingerprint_assessment_item_v01(item)
        ),
        source_learning_context=source_learning_context,
        target_application_context=target_application_context,
        changed_context_factors=changed_context_factors,
        invariant_knowledge=invariant_knowledge,
        required_transfer_reasoning=required_transfer_reasoning,
        plausible_non_transfer_path=plausible_non_transfer_path,
        review_questions=review_questions,
        created_at=created_at,
    )


def require_current_transfer_review_binding_v01(
    *,
    draft: TransferDesignReviewDraftV01,
    item: AssessmentItemV02,
    item_revision: int,
) -> None:
    """
    Reject a draft that does not describe this exact item
    content and revision.

    A successful check means only that the draft is still
    bound to the supplied item snapshot. It does NOT mean
    that the item has passed Transfer Design Review.
    """

    if not isinstance(
        draft,
        TransferDesignReviewDraftV01,
    ):
        raise TypeError(
            "draft must be TransferDesignReviewDraftV01."
        )

    if not isinstance(item, AssessmentItemV02):
        raise TypeError(
            "item must be AssessmentItemV02."
        )

    if (
        draft.assessment_item_id != item.assessment_item_id
        or draft.item_revision != item_revision
        or draft.course_id != item.course_id
        or draft.objective_id != item.objective_id
    ):
        raise ValueError(
            "Transfer review draft does not match "
            "the Assessment Item identity or revision."
        )

    if (
        draft.item_content_sha256
        != fingerprint_assessment_item_v01(item)
    ):
        raise ValueError(
            "Assessment Item content has changed "
            "since the Transfer review draft was created."
        )

    if (
        item.evidence_type != EvidenceType.TRANSFER_ATTEMPT
        or not item.alignment_verified
    ):
        raise ValueError(
            "The current Assessment Item does not satisfy "
            "the Transfer review draft prerequisites."
        )

"""
URPP Implementation 13D-1C3.

Persistable Transfer Design Review Decision contract.

A decision can record approve or reject, but the record
does not independently establish reviewer authentication,
authorization, or permission to issue a Transfer Assessment.

Only a future trusted application service may promote a
review decision into an authoritative delivery approval.
"""

from datetime import datetime
from enum import Enum
from hashlib import sha256
import json

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    TransferDesignReviewDraftV01,
    require_current_transfer_review_binding_v01,
)


class TransferReviewOutcomeV01(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REVOKE = "revoke"


class TransferReviewDecisionV01(BaseModel):
    """
    A recorded review decision, not a trusted approval token.

    The reviewer identity fields are recorded claims until
    a trusted application service verifies their provenance.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    decision_id: str = Field(min_length=1)

    assessment_item_id: str = Field(min_length=1)

    item_revision: int = Field(
        ge=1,
        strict=True,
    )

    course_id: str = Field(min_length=1)

    objective_id: str = Field(min_length=1)

    item_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    draft_content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    reviewer_id: str = Field(min_length=1)

    reviewer_identity_issuer: str = Field(min_length=1)

    outcome: TransferReviewOutcomeV01

    rationale: str = Field(min_length=1)

    decided_at: datetime

    @field_validator("decided_at")
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
                "decided_at must be timezone-aware."
            )

        return value


def fingerprint_transfer_review_draft_v01(
    draft: TransferDesignReviewDraftV01,
) -> str:
    """
    Fingerprint the complete review draft.

    The hash detects a changed draft snapshot.
    It is not a reviewer signature or proof of authority.
    """

    if not isinstance(
        draft,
        TransferDesignReviewDraftV01,
    ):
        raise TypeError(
            "draft must be TransferDesignReviewDraftV01."
        )

    serialized = json.dumps(
        draft.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def create_transfer_review_decision_v01(
    *,
    decision_id: str,
    draft: TransferDesignReviewDraftV01,
    item: AssessmentItemV02,
    item_revision: int,
    reviewer_id: str,
    reviewer_identity_issuer: str,
    outcome: TransferReviewOutcomeV01,
    rationale: str,
    decided_at: datetime,
) -> TransferReviewDecisionV01:
    """
    Create a record from a draft bound to the supplied item.

    This is a data-construction function, not an approval
    endpoint. Caller-supplied reviewer fields are not trusted.
    """

    require_current_transfer_review_binding_v01(
        draft=draft,
        item=item,
        item_revision=item_revision,
    )

    return TransferReviewDecisionV01(
        decision_id=decision_id,
        assessment_item_id=draft.assessment_item_id,
        item_revision=draft.item_revision,
        course_id=draft.course_id,
        objective_id=draft.objective_id,
        item_content_sha256=draft.item_content_sha256,
        draft_content_sha256=(
            fingerprint_transfer_review_draft_v01(draft)
        ),
        reviewer_id=reviewer_id,
        reviewer_identity_issuer=reviewer_identity_issuer,
        outcome=outcome,
        rationale=rationale,
        decided_at=decided_at,
    )

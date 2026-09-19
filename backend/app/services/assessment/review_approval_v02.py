"""
URPP Design 01C — Signed Review Approval V0.2.

A signed approval binds an assessment item, student attempt,
structured review, reviewer identity, and approval timestamp.

SECURITY BOUNDARY:
issue_review_approval must only be called by a backend service
AFTER that service has authenticated and authorized the reviewer.

This module verifies a signed record. It does not authenticate
human users or establish the semantic correctness of a review.
"""

from datetime import datetime
import hashlib
import hmac
import json
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.domain.learning.state_v02 import EvidenceEventV02

from app.services.assessment.models_v02 import (
    StudentAttemptV02,
)

from app.services.assessment.open_response_models_v02 import (
    OpenResponseAssessmentItemV02,
    OpenResponseReviewV02,
)

from app.services.assessment.open_response_scoring_v02 import (
    preview_open_response_review,
)


APPROVAL_POLICY_VERSION = "open-response-approval-v0.2"


class ReviewApprovalV02(BaseModel):
    """An integrity-protected approval record."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    review_id: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    approved_at: datetime

    # Explicit reviewer-assigned confidence in this review.
    # This is NOT a calibrated mastery probability.
    scoring_confidence: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )

    approval_policy_version: Literal[
        "open-response-approval-v0.2"
    ] = APPROVAL_POLICY_VERSION

    signature: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("approved_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Approval timestamp must be timezone-aware."
            )
        return value


def _approval_message(
    item: OpenResponseAssessmentItemV02,
    attempt: StudentAttemptV02,
    review: OpenResponseReviewV02,
    *,
    approved_by: str,
    approved_at: datetime,
    scoring_confidence: float,
) -> bytes:
    """Bind the complete source records to one approval."""

    payload = {
        "item": item.model_dump(mode="json"),
        "attempt": attempt.model_dump(mode="json"),
        "review": review.model_dump(mode="json"),
        "approved_by": approved_by,
        "approved_at": approved_at.isoformat(),
        "scoring_confidence": scoring_confidence,
        "approval_policy_version": APPROVAL_POLICY_VERSION,
    }

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sign(message: bytes, key: bytes) -> str:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError(
            "Approval signing key must contain at least 32 bytes."
        )

    return hmac.new(
        key,
        message,
        hashlib.sha256,
    ).hexdigest()


def issue_review_approval(
    item: OpenResponseAssessmentItemV02,
    attempt: StudentAttemptV02,
    review: OpenResponseReviewV02,
    *,
    authenticated_reviewer_id: str,
    approved_at: datetime,
    scoring_confidence: float,
    signing_key: bytes,
) -> ReviewApprovalV02:
    """
    SERVER-SIDE ONLY.

    Caller must already have authenticated and authorized
    authenticated_reviewer_id. This function does not do that.
    """

    preview = preview_open_response_review(
        item,
        attempt,
        review,
    )

    if preview.status != "requires_reviewer_confirmation":
        raise ValueError(
            "Unscorable reviews cannot be approved as evidence."
        )

    if authenticated_reviewer_id != review.reviewer_id:
        raise ValueError(
            "Authenticated reviewer does not match the review."
        )

    if (
        approved_at.tzinfo is None
        or approved_at.utcoffset() is None
    ):
        raise ValueError(
            "Approval timestamp must be timezone-aware."
        )

    if approved_at < review.reviewed_at:
        raise ValueError(
            "Approval cannot precede the review."
        )

    # Validate all approval fields before creating its signature.
    unsigned = ReviewApprovalV02(
        review_id=review.review_id,
        approved_by=authenticated_reviewer_id,
        approved_at=approved_at,
        scoring_confidence=scoring_confidence,
        signature="0" * 64,
    )

    message = _approval_message(
        item,
        attempt,
        review,
        approved_by=unsigned.approved_by,
        approved_at=unsigned.approved_at,
        scoring_confidence=unsigned.scoring_confidence,
    )

    return unsigned.model_copy(
        update={"signature": _sign(message, signing_key)}
    )


def finalize_approved_review(
    item: OpenResponseAssessmentItemV02,
    attempt: StudentAttemptV02,
    review: OpenResponseReviewV02,
    approval: ReviewApprovalV02,
    *,
    verification_key: bytes,
) -> EvidenceEventV02:
    """Convert a valid signed approval into structured evidence."""

    preview = preview_open_response_review(
        item,
        attempt,
        review,
    )

    if preview.status != "requires_reviewer_confirmation":
        raise ValueError(
            "This review is not eligible for finalization."
        )

    if (
        approval.review_id != review.review_id
        or approval.approved_by != review.reviewer_id
    ):
        raise ValueError(
            "Approval identity does not match its review."
        )

    if approval.approved_at < review.reviewed_at:
        raise ValueError(
            "Approval cannot precede the review."
        )

    message = _approval_message(
        item,
        attempt,
        review,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        scoring_confidence=approval.scoring_confidence,
    )

    expected = _sign(message, verification_key)

    if not hmac.compare_digest(
        approval.signature,
        expected,
    ):
        raise ValueError(
            "Approval signature verification failed."
        )

    return EvidenceEventV02(
        evidence_id=f"approved-review-v02:{review.review_id}",
        student_id=attempt.student_id,
        course_id=attempt.course_id,
        session_id=attempt.session_id,
        objective_id=attempt.objective_id,
        source_message_id=attempt.source_message_id,
        assessment_item_id=attempt.assessment_item_id,
        response_group_id=attempt.response_group_id,
        evidence_type=item.evidence_type,
        observation=(
            "Criterion-based open-response review finalized "
            f"under approval record {review.review_id}."
        ),
        objective_alignment="direct",
        assessment_validity="valid",
        outcome=preview.outcome,
        correctness=preview.correctness,
        assistance_level=attempt.assistance_level,
        prior_solution_exposure=attempt.prior_solution_exposure,
        novelty=attempt.novelty,
        transfer_distance="none",
        retrieval_delay_hours=None,
        model_confidence=approval.scoring_confidence,
        scoring_policy_version=APPROVAL_POLICY_VERSION,

        # The evidence becomes available upon approval.
        # A later schema revision should distinguish
        # original attempt time from approval/recording time.
        created_at=approval.approved_at,
    )

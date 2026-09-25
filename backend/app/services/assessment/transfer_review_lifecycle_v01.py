"""
URPP Implementation 13D-1C4.

Interpret historical, untrusted Transfer Review Decisions
for one exact Assessment Item revision.

This policy does not authenticate reviewers, verify the
origin of timestamps, or grant Assignment delivery authority.

Even APPROVE_RECORDED is only a description of the
supplied historical records.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    fingerprint_assessment_item_v01,
)

from app.services.assessment.transfer_review_decision_v01 import (
    TransferReviewDecisionV01,
    TransferReviewOutcomeV01,
)


class TransferReviewLifecycleStatusV01(str, Enum):
    NO_DECISION = "no_decision"

    APPROVE_RECORDED = "approve_recorded"

    REJECT_RECORDED = "reject_recorded"

    REVOKE_RECORDED = "revoke_recorded"

    AMBIGUOUS = "ambiguous"

    INVALID_HISTORY = "invalid_history"


@dataclass(frozen=True)
class TransferReviewLifecycleResultV01:
    """
    Description of the supplied review history.

    This is NOT an approval token, reviewer authorization,
    or permission to issue a Transfer Assessment.
    """

    status: TransferReviewLifecycleStatusV01

    reason: str

    current_decision_id: str | None

    considered_decision_ids: tuple[str, ...]


def _result(
    *,
    status: TransferReviewLifecycleStatusV01,
    reason: str,
    current_decision_id: str | None,
    decision_ids: tuple[str, ...],
) -> TransferReviewLifecycleResultV01:
    return TransferReviewLifecycleResultV01(
        status=status,
        reason=reason,
        current_decision_id=current_decision_id,
        considered_decision_ids=decision_ids,
    )


def evaluate_transfer_review_lifecycle_v01(
    *,
    item: AssessmentItemV02,
    item_revision: int,
    decisions: Sequence[TransferReviewDecisionV01],
    as_of: datetime,
) -> TransferReviewLifecycleResultV01:
    """
    Interpret recorded decisions for one item revision.

    Rules:

    1. All decisions must concern the exact supplied item,
       revision, scope, and content fingerprint.

    2. Duplicate decision IDs or future-dated decisions
       invalidate the supplied history.

    3. If two different decisions share the latest
       timestamp, their ordering is ambiguous.

    4. Otherwise, the latest recorded outcome determines
       the descriptive lifecycle status.

    The records remain untrusted. This function must
    never be used directly as a delivery authorization.
    """

    if not isinstance(item, AssessmentItemV02):
        raise TypeError(
            "item must be AssessmentItemV02."
        )

    if type(item_revision) is not int or item_revision < 1:
        raise ValueError(
            "item_revision must be a positive integer."
        )

    if (
        not isinstance(as_of, datetime)
        or as_of.tzinfo is None
        or as_of.utcoffset() is None
    ):
        raise ValueError(
            "as_of must be a timezone-aware datetime."
        )

    if isinstance(decisions, (str, bytes)):
        raise TypeError(
            "decisions must be a sequence of review decisions."
        )

    if not isinstance(decisions, Sequence):
        raise TypeError(
            "decisions must be a sequence of review decisions."
        )

    for decision in decisions:
        if not isinstance(
            decision,
            TransferReviewDecisionV01,
        ):
            raise TypeError(
                "Every decision must be "
                "TransferReviewDecisionV01."
            )

    decision_ids = tuple(
        decision.decision_id
        for decision in decisions
    )

    if not decisions:
        return _result(
            status=TransferReviewLifecycleStatusV01.NO_DECISION,
            reason="No review decisions were supplied.",
            current_decision_id=None,
            decision_ids=(),
        )

    # Duplicate identities make the historical record invalid,
    # even if the duplicate rows contain identical information.
    if len(decision_ids) != len(set(decision_ids)):
        return _result(
            status=TransferReviewLifecycleStatusV01.INVALID_HISTORY,
            reason="Duplicate review decision IDs.",
            current_decision_id=None,
            decision_ids=decision_ids,
        )

    item_fingerprint = fingerprint_assessment_item_v01(
        item
    )

    for decision in decisions:
        if (
            decision.assessment_item_id
            != item.assessment_item_id

            or decision.item_revision
            != item_revision

            or decision.course_id
            != item.course_id

            or decision.objective_id
            != item.objective_id

            or decision.item_content_sha256
            != item_fingerprint
        ):
            return _result(
                status=(
                    TransferReviewLifecycleStatusV01
                    .INVALID_HISTORY
                ),
                reason=(
                    "Review history contains a decision "
                    "for a different item, revision, "
                    "scope, or content fingerprint."
                ),
                current_decision_id=None,
                decision_ids=decision_ids,
            )

        if decision.decided_at > as_of:
            return _result(
                status=(
                    TransferReviewLifecycleStatusV01
                    .INVALID_HISTORY
                ),
                reason=(
                    "Review history contains a decision "
                    "dated after the evaluation time."
                ),
                current_decision_id=None,
                decision_ids=decision_ids,
            )

    ordered = sorted(
        decisions,
        key=lambda decision: (
            decision.decided_at,
            decision.decision_id,
        ),
    )

    latest = ordered[-1]

    # Do not use decision_id, insertion order, or database
    # return order to break a tie in the decision timestamp.
    latest_timestamp_count = sum(
        decision.decided_at == latest.decided_at
        for decision in ordered
    )

    if latest_timestamp_count != 1:
        return _result(
            status=TransferReviewLifecycleStatusV01.AMBIGUOUS,
            reason=(
                "Multiple review decisions share the "
                "latest decision timestamp."
            ),
            current_decision_id=None,
            decision_ids=decision_ids,
        )

    status_by_outcome = {
        TransferReviewOutcomeV01.APPROVE: (
            TransferReviewLifecycleStatusV01
            .APPROVE_RECORDED
        ),

        TransferReviewOutcomeV01.REJECT: (
            TransferReviewLifecycleStatusV01
            .REJECT_RECORDED
        ),

        TransferReviewOutcomeV01.REVOKE: (
            TransferReviewLifecycleStatusV01
            .REVOKE_RECORDED
        ),
    }

    status = status_by_outcome.get(
        latest.outcome
    )

    if status is None:
        return _result(
            status=(
                TransferReviewLifecycleStatusV01
                .INVALID_HISTORY
            ),
            reason="Review history contains an unknown outcome.",
            current_decision_id=None,
            decision_ids=decision_ids,
        )

    return _result(
        status=status,
        reason=(
            "Latest recorded review outcome. "
            "Reviewer authorization and decision "
            "provenance have not been verified."
        ),
        current_decision_id=latest.decision_id,
        decision_ids=decision_ids,
    )

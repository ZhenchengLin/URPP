"""
URPP Implementation 13D-1C5.

Transfer Review Application Service V0.1.

Coordinates an internal review-writing workflow:

    Load authoritative item revision.
    Check the review draft.
    Consult configured reviewer authorization providers.
    Generate a review decision.
    Persist that decision.

This is an application-service prototype, not a deployed
authentication or authorization security boundary.

The caller must not control the provider implementations
or the service's clock in a future production deployment.

Recorded APPROVE decisions do not enable Transfer Delivery.
"""

from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Callable

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.transfer_review_decisions_v01 import (
    TransferReviewDecisionRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    TransferDesignReviewDraftV01,
)

from app.services.assessment.transfer_review_decision_v01 import (
    TransferReviewDecisionV01,
    TransferReviewOutcomeV01,
    create_transfer_review_decision_v01,
)

from app.services.assessment.transfer_reviewer_authorization_v01 import (
    ReviewerAccessCheckV01,
    TransferReviewerAuthorizationServiceV01,
)


class TransferReviewApplicationServiceV01:
    """
    Construct and persist a review decision after checking
    the stored item and configured authorization providers.

    This service never accepts a reviewer ID, issuer,
    authorization result, or decision timestamp as
    individual arguments to submit_review().
    """

    def __init__(
        self,
        *,
        assessment_repository: AssessmentRecordRepositoryV02,
        decision_repository: TransferReviewDecisionRepositoryV01,
        authorization_service: TransferReviewerAuthorizationServiceV01,
        clock: Callable[[], datetime] | None = None,
    ):
        self._assessments = assessment_repository

        self._decisions = decision_repository

        self._authorization = authorization_service

        self._clock = (
            clock
            if clock is not None
            else lambda: datetime.now(timezone.utc)
        )

    def submit_review(
        self,
        *,
        draft: TransferDesignReviewDraftV01,
        outcome: TransferReviewOutcomeV01,
        rationale: str,
    ) -> TransferReviewDecisionV01:
        """
        Record an internal Transfer Design Review decision.

        This does not grant approval-delivery authority.

        The actual identity/permission trustworthiness
        depends on the application-owned providers.
        """

        if not isinstance(
            draft,
            TransferDesignReviewDraftV01,
        ):
            raise TypeError(
                "draft must be TransferDesignReviewDraftV01."
            )

        if not isinstance(
            outcome,
            TransferReviewOutcomeV01,
        ):
            raise TypeError(
                "outcome must be TransferReviewOutcomeV01."
            )

        if not isinstance(rationale, str):
            raise TypeError(
                "rationale must be a string."
            )

        if not rationale.strip():
            raise ValueError(
                "Review rationale must not be blank."
            )

        item_revision = draft.item_revision

        # Load the actual stored item. The caller does not
        # supply an arbitrary item object to this operation.
        item = self._assessments.load_item(
            draft.assessment_item_id,
            revision=item_revision,
        )

        if not isinstance(
            item,
            AssessmentItemV02,
        ):
            raise ValueError(
                "Transfer review requires a stored "
                "numeric Assessment Item."
            )

        # The clock is supplied by application composition,
        # not by the review request.
        decided_at = self._clock()

        if (
            not isinstance(decided_at, datetime)
            or decided_at.tzinfo is None
            or decided_at.utcoffset() is None
        ):
            raise ValueError(
                "Review application clock must return "
                "a timezone-aware datetime."
            )

        if draft.created_at > decided_at:
            raise ValueError(
                "Transfer review draft cannot be created "
                "after the review decision time."
            )

        # This service requests authorization itself.
        # The caller cannot submit a previously constructed
        # ReviewerAccessCheckV01 as proof of permission.
        access_check = (
            self._authorization.require_reviewer_for_draft(
                draft=draft,
                item=item,
                item_revision=item_revision,
                as_of=decided_at,
            )
        )

        if not isinstance(
            access_check,
            ReviewerAccessCheckV01,
        ):
            raise TypeError(
                "Authorization service did not return "
                "ReviewerAccessCheckV01."
            )

        # Defensive consistency check for the returned
        # access result. This does not authenticate its source.
        if (
            access_check.assessment_item_id
            != item.assessment_item_id

            or access_check.item_revision
            != item_revision

            or access_check.item_content_sha256
            != draft.item_content_sha256

            or access_check.checked_at
            != decided_at
        ):
            raise ValueError(
                "Reviewer access check does not match "
                "the current review operation."
            )

        # The service generates the record identity.
        # A caller cannot select an existing decision ID.
        decision_id = token_urlsafe(24)

        decision = create_transfer_review_decision_v01(
            decision_id=decision_id,
            draft=draft,
            item=item,
            item_revision=item_revision,
            reviewer_id=access_check.reviewer_id,
            reviewer_identity_issuer=access_check.issuer,
            outcome=outcome,
            rationale=rationale,
            decided_at=decided_at,
        )

        # The existing repository performs its own stored
        # item revision and content-fingerprint checks.
        #
        # Authorization and persistence are not currently
        # one atomic transaction. The future trusted review
        # system must address revocation/concurrency races.
        self._decisions.save_decision(decision)

        return decision

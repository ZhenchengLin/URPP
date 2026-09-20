"""
URPP Implementation 13D-1C2.

Transfer Design Reviewer Authorization Contract V0.1.

This module defines the boundary between a future trusted
application layer and Transfer Design Review.

It does not implement authentication, persist approvals,
or authorize Transfer Assessment delivery.

The application must eventually provide trusted identity
and permission implementations. An arbitrary caller-supplied
implementation is not a security boundary.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.services.assessment.models_v02 import AssessmentItemV02

from app.services.assessment.transfer_design_review_v01 import (
    TransferDesignReviewDraftV01,
    require_current_transfer_review_binding_v01,
)


class ReviewerAuthorizationError(PermissionError):
    """The requested Transfer Design Review is not authorized."""


@dataclass(frozen=True)
class ReviewerIdentityAssertionV01:
    """
    Identity information returned by a configured provider.

    This data object is NOT authentication proof by itself.

    Its authenticity depends entirely on the provider
    and the application's control of that provider.
    """

    reviewer_id: str
    issuer: str
    verified_at: datetime

    def __post_init__(self):
        if not isinstance(self.reviewer_id, str):
            raise TypeError("reviewer_id must be a string.")

        if not self.reviewer_id.strip():
            raise ValueError("reviewer_id must not be blank.")

        if not isinstance(self.issuer, str):
            raise TypeError("issuer must be a string.")

        if not self.issuer.strip():
            raise ValueError("issuer must not be blank.")

        if not isinstance(self.verified_at, datetime):
            raise TypeError("verified_at must be a datetime.")

        if (
            self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
        ):
            raise ValueError(
                "verified_at must be timezone-aware."
            )


class ReviewerIdentityProviderV01(Protocol):
    """
    Future application-owned identity provider.

    A student request or LLM response is not a valid
    implementation of this identity boundary.
    """

    def current_reviewer(
        self,
    ) -> ReviewerIdentityAssertionV01 | None:
        ...


class TransferReviewPermissionProviderV01(Protocol):
    """
    Future application-owned reviewer permission provider.

    Permissions are scoped to the Course and Objective
    being reviewed.
    """

    def may_approve_transfer(
        self,
        *,
        reviewer_id: str,
        issuer: str,
        course_id: str,
        objective_id: str,
    ) -> bool:
        ...


@dataclass(frozen=True)
class ReviewerAccessCheckV01:
    """
    Result of a successful check against configured providers.

    This is NOT a signed capability, Approval Record,
    or transferable permission to issue an Assignment.
    """

    reviewer_id: str
    issuer: str

    assessment_item_id: str
    item_revision: int
    item_content_sha256: str

    checked_at: datetime


class TransferReviewerAuthorizationServiceV01:
    """
    Validate draft binding and consult configured providers.

    The service fails closed when providers are absent,
    return unexpected values, reject access, or raise errors.

    Its security depends on trusted application composition.
    Injecting a fake permissive provider does not establish
    real reviewer authorization.
    """

    MAX_IDENTITY_AGE = timedelta(minutes=15)

    def __init__(
        self,
        *,
        expected_identity_issuer: str,
        identity_provider: ReviewerIdentityProviderV01 | None = None,
        permission_provider: TransferReviewPermissionProviderV01 | None = None,
    ):
        if (
            not isinstance(expected_identity_issuer, str)
            or not expected_identity_issuer.strip()
        ):
            raise ValueError(
                "expected_identity_issuer must not be blank."
            )

        self._expected_identity_issuer = (
            expected_identity_issuer
        )

        self._identity_provider = identity_provider

        self._permission_provider = permission_provider

    def require_reviewer_for_draft(
        self,
        *,
        draft: TransferDesignReviewDraftV01,
        item: AssessmentItemV02,
        item_revision: int,
        as_of: datetime,
    ) -> ReviewerAccessCheckV01:
        """
        Check the exact draft/item binding, authenticated
        identity assertion, freshness, and review permission.

        This method does not approve the draft.
        """

        if not isinstance(as_of, datetime):
            raise TypeError("as_of must be a datetime.")

        if (
            as_of.tzinfo is None
            or as_of.utcoffset() is None
        ):
            raise ValueError(
                "as_of must be timezone-aware."
            )

        # An invalid or stale draft must not proceed to
        # reviewer authorization.
        require_current_transfer_review_binding_v01(
            draft=draft,
            item=item,
            item_revision=item_revision,
        )

        if (
            self._identity_provider is None
            or self._permission_provider is None
        ):
            raise ReviewerAuthorizationError(
                "Trusted reviewer authorization providers "
                "are not configured."
            )

        try:
            identity = self._identity_provider.current_reviewer()
        except Exception as exc:
            raise ReviewerAuthorizationError(
                "Reviewer identity verification is unavailable."
            ) from exc

        if not isinstance(
            identity,
            ReviewerIdentityAssertionV01,
        ):
            raise ReviewerAuthorizationError(
                "No valid reviewer identity assertion is available."
            )

        if identity.issuer != self._expected_identity_issuer:
            raise ReviewerAuthorizationError(
                "Reviewer identity issuer does not match "
                "the configured issuer."
            )

        identity_age = as_of - identity.verified_at

        if (
            identity_age < timedelta(0)
            or identity_age > self.MAX_IDENTITY_AGE
        ):
            raise ReviewerAuthorizationError(
                "Reviewer identity verification is stale "
                "or occurs after the authorization check."
            )

        try:
            permitted = (
                self._permission_provider.may_approve_transfer(
                    reviewer_id=identity.reviewer_id,
                    issuer=identity.issuer,
                    course_id=item.course_id,
                    objective_id=item.objective_id,
                )
            )
        except Exception as exc:
            raise ReviewerAuthorizationError(
                "Transfer review permission verification "
                "is unavailable."
            ) from exc

        # Reject truthy strings, integers, and other
        # ambiguous responses.
        if permitted is not True:
            raise ReviewerAuthorizationError(
                "Reviewer is not authorized to approve "
                "Transfer Design for this Course and Objective."
            )

        return ReviewerAccessCheckV01(
            reviewer_id=identity.reviewer_id,
            issuer=identity.issuer,
            assessment_item_id=item.assessment_item_id,
            item_revision=item_revision,
            item_content_sha256=draft.item_content_sha256,
            checked_at=as_of,
        )

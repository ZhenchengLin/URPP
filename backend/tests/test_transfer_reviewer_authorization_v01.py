"""
URPP Implementation 13D-1C2.

Tests use controlled provider doubles.

Passing these tests does not establish that URPP has
a real reviewer authentication or authorization system.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    create_transfer_design_review_draft_v01,
)

from app.services.assessment.transfer_reviewer_authorization_v01 import (
    ReviewerAuthorizationError,
    ReviewerIdentityAssertionV01,
    TransferReviewerAuthorizationServiceV01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


class FakeIdentityProvider:
    def __init__(self, identity=None, *, error=None):
        self.identity = identity
        self.error = error
        self.calls = 0

    def current_reviewer(self):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.identity


class FakePermissionProvider:
    def __init__(self, result=False, *, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def may_approve_transfer(
        self,
        *,
        reviewer_id,
        issuer,
        course_id,
        objective_id,
    ):
        self.calls.append(
            (
                reviewer_id,
                issuer,
                course_id,
                objective_id,
            )
        )

        if self.error is not None:
            raise self.error

        return self.result


def make_item():
    return AssessmentItemV02(
        assessment_item_id="transfer-item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="Apply the principle in a new context.",
        evidence_type=EvidenceType.TRANSFER_ATTEMPT,
        rubric=NumericRubricV02(
            expected_value=5.0,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_draft(item):
    return create_transfer_design_review_draft_v01(
        item=item,
        item_revision=1,
        source_learning_context="Previously taught setting.",
        target_application_context="New application setting.",
        changed_context_factors=(
            "Different contextual cues.",
        ),
        invariant_knowledge="The same underlying principle.",
        required_transfer_reasoning=(
            "Recognize and apply that principle."
        ),
        plausible_non_transfer_path=(
            "Repeating a memorized procedure."
        ),
        review_questions=(
            "Does this task genuinely require transfer?",
        ),
        created_at=NOW,
    )


def make_identity(
    *,
    issuer="trusted-test-issuer",
    verified_at=NOW,
):
    return ReviewerIdentityAssertionV01(
        reviewer_id="reviewer-001",
        issuer=issuer,
        verified_at=verified_at,
    )


def make_service(
    *,
    identity_provider=None,
    permission_provider=None,
):
    return TransferReviewerAuthorizationServiceV01(
        expected_identity_issuer="trusted-test-issuer",
        identity_provider=identity_provider,
        permission_provider=permission_provider,
    )


def check(
    service,
    *,
    item=None,
    draft=None,
    item_revision=1,
    as_of=NOW,
):
    if item is None:
        item = make_item()

    if draft is None:
        draft = make_draft(item)

    return service.require_reviewer_for_draft(
        draft=draft,
        item=item,
        item_revision=item_revision,
        as_of=as_of,
    )


def test_missing_providers_fail_closed():
    service = make_service()

    with pytest.raises(
        ReviewerAuthorizationError,
        match="not configured",
    ):
        check(service)


def test_missing_identity_fails_closed_before_permission_check():
    identity_provider = FakeIdentityProvider(None)
    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=identity_provider,
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="No valid reviewer identity",
    ):
        check(service)

    assert identity_provider.calls == 1
    assert permission_provider.calls == []


def test_unexpected_identity_response_is_rejected():
    service = make_service(
        identity_provider=FakeIdentityProvider(
            "reviewer-001"
        ),
        permission_provider=FakePermissionProvider(True),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="No valid reviewer identity",
    ):
        check(service)


def test_wrong_identity_issuer_is_rejected():
    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity(issuer="unrecognized-issuer")
        ),
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="issuer does not match",
    ):
        check(service)

    assert permission_provider.calls == []


@pytest.mark.parametrize(
    "verified_at",
    [
        NOW - timedelta(minutes=16),
        NOW + timedelta(seconds=1),
    ],
)
def test_stale_or_future_identity_is_rejected(
    verified_at,
):
    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity(verified_at=verified_at)
        ),
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="stale or occurs after",
    ):
        check(service)

    assert permission_provider.calls == []


def test_permission_denial_blocks_review():
    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity()
        ),
        permission_provider=FakePermissionProvider(False),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="not authorized",
    ):
        check(service)


@pytest.mark.parametrize(
    "unexpected_permission",
    [
        "yes",
        1,
        None,
    ],
)
def test_ambiguous_permission_response_is_rejected(
    unexpected_permission,
):
    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity()
        ),
        permission_provider=FakePermissionProvider(
            unexpected_permission
        ),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="not authorized",
    ):
        check(service)


def test_identity_provider_failure_is_denied():
    service = make_service(
        identity_provider=FakeIdentityProvider(
            error=RuntimeError("identity provider unavailable")
        ),
        permission_provider=FakePermissionProvider(True),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="identity verification is unavailable",
    ):
        check(service)


def test_permission_provider_failure_is_denied():
    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity()
        ),
        permission_provider=FakePermissionProvider(
            error=RuntimeError("permission provider unavailable")
        ),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="permission verification is unavailable",
    ):
        check(service)


def test_stale_draft_rejected_before_identity_or_permission():
    original_item = make_item()
    draft = make_draft(original_item)

    changed_item = original_item.model_copy(
        update={
            "prompt": "A revised assessment question.",
        }
    )

    identity_provider = FakeIdentityProvider(
        make_identity()
    )

    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=identity_provider,
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ValueError,
        match="content has changed",
    ):
        check(
            service,
            item=changed_item,
            draft=draft,
        )

    assert identity_provider.calls == 0
    assert permission_provider.calls == []


def test_revision_mismatch_rejected_before_permission():
    item = make_item()
    draft = make_draft(item)

    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity()
        ),
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ValueError,
        match="identity or revision",
    ):
        check(
            service,
            item=item,
            draft=draft,
            item_revision=2,
        )

    assert permission_provider.calls == []


def test_configured_test_providers_return_scoped_access_check():
    item = make_item()
    draft = make_draft(item)

    permission_provider = FakePermissionProvider(True)

    service = make_service(
        identity_provider=FakeIdentityProvider(
            make_identity()
        ),
        permission_provider=permission_provider,
    )

    result = check(
        service,
        item=item,
        draft=draft,
    )

    assert result.reviewer_id == "reviewer-001"
    assert result.issuer == "trusted-test-issuer"

    assert result.assessment_item_id == item.assessment_item_id
    assert result.item_revision == 1
    assert result.item_content_sha256 == draft.item_content_sha256

    assert permission_provider.calls == [
        (
            "reviewer-001",
            "trusted-test-issuer",
            "course-001",
            "objective-001",
        )
    ]


def test_identity_assertion_does_not_accept_naive_timestamp():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        make_identity(
            verified_at=datetime(2026, 9, 20)
        )


def test_request_time_must_be_timezone_aware():
    service = make_service()

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        check(
            service,
            as_of=datetime(2026, 9, 20),
        )

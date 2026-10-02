"""
URPP Implementation 13D-1C5.

Integration tests for the internal review-writing workflow.

Provider doubles are deliberately not real identity or
permission systems.

No APPROVE record created here can open Transfer Delivery.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.domain.learning.models import EvidenceType

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.transfer_review_decisions_v01 import (
    TransferReviewDecisionRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    create_transfer_design_review_draft_v01,
)

from app.services.assessment.transfer_review_decision_v01 import (
    TransferReviewOutcomeV01,
)

from app.services.assessment.transfer_review_application_v01 import (
    TransferReviewApplicationServiceV01,
)

from app.services.assessment.transfer_reviewer_authorization_v01 import (
    ReviewerAuthorizationError,
    ReviewerIdentityAssertionV01,
    TransferReviewerAuthorizationServiceV01,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.transfer_delivery_gate_v01 import (
    require_trusted_transfer_delivery_v01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


class FakeIdentityProvider:
    def __init__(
        self,
        *,
        identity=None,
    ):
        self.identity = identity
        self.calls = 0

    def current_reviewer(self):
        self.calls += 1

        return self.identity


class FakePermissionProvider:
    def __init__(
        self,
        *,
        allowed=False,
    ):
        self.allowed = allowed
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

        return self.allowed


def make_item(
    *,
    prompt="Apply the principle in a new application.",
):
    return AssessmentItemV02(
        assessment_item_id="transfer-item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt=prompt,
        evidence_type=EvidenceType.TRANSFER_ATTEMPT,
        rubric=NumericRubricV02(
            expected_value=5.0,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_draft(
    item,
    *,
    item_revision=1,
    created_at=NOW,
):
    return create_transfer_design_review_draft_v01(
        item=item,
        item_revision=item_revision,
        source_learning_context=(
            "Previously taught numerical setting."
        ),
        target_application_context=(
            "A new application requiring the same principle."
        ),
        changed_context_factors=(
            "Different problem presentation.",
        ),
        invariant_knowledge=(
            "The mathematical principle remains applicable."
        ),
        required_transfer_reasoning=(
            "Recognize and justify the principle in "
            "the new context."
        ),
        plausible_non_transfer_path=(
            "Repeat a memorized solution without "
            "recognizing the principle."
        ),
        review_questions=(
            "Does the changed context require transfer?",
        ),
        created_at=created_at,
    )


def make_identity(
    *,
    reviewer_id="reviewer-001",
    verified_at=NOW + timedelta(seconds=1),
):
    return ReviewerIdentityAssertionV01(
        reviewer_id=reviewer_id,
        issuer="configured-test-issuer",
        verified_at=verified_at,
    )


def open_database(
    path,
    *,
    initialize,
):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()

        cursor.execute("PRAGMA foreign_keys=ON")

        cursor.close()

    if initialize:
        Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(
        factory
    )

    decisions = TransferReviewDecisionRepositoryV01(
        factory
    )

    return engine, assessments, decisions


class TestEnvironment:
    """
    Shared test helper, explicitly excluded from
    pytest class collection.
    """

    __test__ = False

    def __init__(
        self,
        *,
        path,
        engine,
        assessments,
        decisions,
    ):
        self.path = path
        self.engine = engine
        self.assessments = assessments
        self.decisions = decisions

    def make_service(
        self,
        *,
        identity_provider=None,
        permission_provider=None,
        clock=None,
    ):
        authorization = (
            TransferReviewerAuthorizationServiceV01(
                expected_identity_issuer=(
                    "configured-test-issuer"
                ),
                identity_provider=identity_provider,
                permission_provider=permission_provider,
            )
        )

        return TransferReviewApplicationServiceV01(
            assessment_repository=self.assessments,
            decision_repository=self.decisions,
            authorization_service=authorization,
            clock=clock
            if clock is not None
            else lambda: NOW + timedelta(seconds=2),
        )


@pytest.fixture
def environment(tmp_path):
    path = tmp_path / "transfer_application.sqlite"

    engine, assessments, decisions = open_database(
        path,
        initialize=True,
    )

    env = TestEnvironment(
        path=path,
        engine=engine,
        assessments=assessments,
        decisions=decisions,
    )

    yield env

    engine.dispose()


def test_authorized_test_flow_persists_review_decision(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    identity_provider = FakeIdentityProvider(
        identity=make_identity()
    )

    permission_provider = FakePermissionProvider(
        allowed=True
    )

    service = environment.make_service(
        identity_provider=identity_provider,
        permission_provider=permission_provider,
    )

    recorded = service.submit_review(
        draft=make_draft(item),
        outcome=TransferReviewOutcomeV01.APPROVE,
        rationale="Review criteria were examined.",
    )

    assert recorded.decision_id

    assert recorded.reviewer_id == "reviewer-001"

    assert (
        recorded.reviewer_identity_issuer
        == "configured-test-issuer"
    )

    assert recorded.decided_at == (
        NOW + timedelta(seconds=2)
    )

    assert recorded.outcome == (
        TransferReviewOutcomeV01.APPROVE
    )

    assert identity_provider.calls == 1

    assert permission_provider.calls == [
        (
            "reviewer-001",
            "configured-test-issuer",
            "course-001",
            "objective-001",
        )
    ]

    assert environment.decisions.load_decision(
        recorded.decision_id
    ) == recorded


def test_recorded_decision_survives_database_reopen(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    recorded = service.submit_review(
        draft=make_draft(item),
        outcome=TransferReviewOutcomeV01.REJECT,
        rationale="The transfer requirement is not established.",
    )

    environment.engine.dispose()

    reopened_engine, _, reopened_decisions = open_database(
        environment.path,
        initialize=False,
    )

    try:
        recovered = reopened_decisions.load_decision(
            recorded.decision_id
        )

        assert recovered == recorded

    finally:
        reopened_engine.dispose()


def test_missing_identity_provider_rejects_without_persistence(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="not configured",
    ):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_permission_denial_rejects_without_persistence(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    permission_provider = FakePermissionProvider(
        allowed=False
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="not authorized",
    ):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert len(permission_provider.calls) == 1

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_unrecognized_identity_issuer_fails_closed(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    wrong_identity = ReviewerIdentityAssertionV01(
        reviewer_id="reviewer-001",
        issuer="unrecognized-issuer",
        verified_at=NOW + timedelta(seconds=1),
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=wrong_identity
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    with pytest.raises(
        ReviewerAuthorizationError,
        match="issuer does not match",
    ):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_stale_draft_is_rejected_before_review_write(
    environment,
):
    original_item = make_item()

    environment.assessments.save_item(
        original_item,
        revision=1,
    )

    stale_draft_item = make_item(
        prompt="A different assessment under the same ID."
    )

    draft = make_draft(
        stale_draft_item
    )

    identity_provider = FakeIdentityProvider(
        identity=make_identity()
    )

    permission_provider = FakePermissionProvider(
        allowed=True
    )

    service = environment.make_service(
        identity_provider=identity_provider,
        permission_provider=permission_provider,
    )

    with pytest.raises(
        ValueError,
        match="content has changed",
    ):
        service.submit_review(
            draft=draft,
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert identity_provider.calls == 0

    assert permission_provider.calls == []

    assert environment.decisions.list_decisions_for_item(
        original_item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_missing_item_revision_rejects_review(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    with pytest.raises(
        LookupError,
        match="revision was not found",
    ):
        service.submit_review(
            draft=make_draft(
                item,
                item_revision=2,
            ),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_future_dated_draft_is_rejected(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    with pytest.raises(
        ValueError,
        match="cannot be created after",
    ):
        service.submit_review(
            draft=make_draft(
                item,
                created_at=NOW + timedelta(days=1),
            ),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_invalid_application_clock_rejects_review(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
        clock=lambda: datetime(2026, 9, 20),
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware datetime",
    ):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="This must not be stored.",
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_review_request_cannot_supply_reviewer_identity_or_time(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    with pytest.raises(TypeError):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="A review rationale.",
            reviewer_id="arbitrary-caller-supplied-reviewer",
        )

    with pytest.raises(TypeError):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="A review rationale.",
            decided_at=NOW,
        )

    with pytest.raises(TypeError):
        service.submit_review(
            draft=make_draft(item),
            outcome=TransferReviewOutcomeV01.APPROVE,
            rationale="A review rationale.",
            access_check=object(),
        )

    assert environment.decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == ()


def test_recorded_approve_still_does_not_open_delivery_gate(
    environment,
):
    item = make_item()

    environment.assessments.save_item(
        item,
        revision=1,
    )

    service = environment.make_service(
        identity_provider=FakeIdentityProvider(
            identity=make_identity()
        ),
        permission_provider=FakePermissionProvider(
            allowed=True
        ),
    )

    recorded = service.submit_review(
        draft=make_draft(item),
        outcome=TransferReviewOutcomeV01.APPROVE,
        rationale="The review was recorded.",
    )

    assert (
        environment.decisions.load_decision(
            recorded.decision_id
        ).outcome
        == TransferReviewOutcomeV01.APPROVE
    )

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action=(
                TeachingActionV01.TRANSFER_ASSESSMENT
            ),
        )

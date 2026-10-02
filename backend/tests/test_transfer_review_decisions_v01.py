"""
URPP Implementation 13D-1C3.

Tests use temporary file-backed SQLite databases.

An APPROVE outcome is an untrusted recorded decision,
not permission to bypass the Transfer Delivery Gate.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pydantic import ValidationError

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
    TransferReviewDecisionV01,
    TransferReviewOutcomeV01,
    create_transfer_review_decision_v01,
    fingerprint_transfer_review_draft_v01,
)

from app.services.decision.models_v01 import TeachingActionV01

from app.services.decision.transfer_delivery_gate_v01 import (
    require_trusted_transfer_delivery_v01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


def make_item(
    *,
    prompt="Apply the principle in a new context.",
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


def make_draft(item, *, item_revision=1):
    return create_transfer_design_review_draft_v01(
        item=item,
        item_revision=item_revision,
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
            "Does the task genuinely require transfer?",
        ),
        created_at=NOW,
    )


def make_decision(
    *,
    decision_id="review-decision-001",
    item=None,
    item_revision=1,
    outcome=TransferReviewOutcomeV01.APPROVE,
    rationale="The proposed context change was reviewed.",
    decided_at=NOW,
):
    if item is None:
        item = make_item()

    draft = make_draft(
        item,
        item_revision=item_revision,
    )

    return create_transfer_review_decision_v01(
        decision_id=decision_id,
        draft=draft,
        item=item,
        item_revision=item_revision,
        reviewer_id="unverified-reviewer-001",
        reviewer_identity_issuer="test-record-source",
        outcome=outcome,
        rationale=rationale,
        decided_at=decided_at,
    )


def open_database(path, *, create_tables):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    if create_tables:
        Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    items = AssessmentRecordRepositoryV02(
        factory
    )

    decisions = TransferReviewDecisionRepositoryV01(
        factory
    )

    return engine, items, decisions


@pytest.fixture
def environment(tmp_path):
    path = tmp_path / "transfer_reviews.sqlite"

    engine, items, decisions = open_database(
        path,
        create_tables=True,
    )

    yield path, engine, items, decisions

    engine.dispose()


def test_decision_round_trip_and_database_reopen(
    environment,
):
    path, first_engine, items, decisions = environment

    item = make_item()

    items.save_item(
        item,
        revision=1,
    )

    decision = make_decision(item=item)

    decisions.save_decision(decision)

    first_engine.dispose()

    reopened_engine, _, reopened_decisions = open_database(
        path,
        create_tables=False,
    )

    try:
        restored = reopened_decisions.load_decision(
            decision.decision_id
        )

        assert restored == decision

        assert restored.outcome == (
            TransferReviewOutcomeV01.APPROVE
        )

        assert reopened_decisions.list_decisions_for_item(
            item.assessment_item_id,
            item_revision=1,
        ) == (decision,)

    finally:
        reopened_engine.dispose()


def test_duplicate_decision_id_cannot_overwrite_record(
    environment,
):
    _, _, items, decisions = environment

    item = make_item()

    items.save_item(
        item,
        revision=1,
    )

    first = make_decision(item=item)

    decisions.save_decision(first)

    replacement = first.model_copy(
        update={
            "outcome": TransferReviewOutcomeV01.REJECT,
            "rationale": "A different recorded decision.",
        }
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        decisions.save_decision(replacement)

    assert decisions.load_decision(
        first.decision_id
    ) == first


def test_approve_and_reject_are_separate_historical_decisions(
    environment,
):
    _, _, items, decisions = environment

    item = make_item()

    items.save_item(item, revision=1)

    first = make_decision(
        item=item,
        decision_id="review-decision-001",
        outcome=TransferReviewOutcomeV01.APPROVE,
    )

    second = make_decision(
        item=item,
        decision_id="review-decision-002",
        outcome=TransferReviewOutcomeV01.REJECT,
        rationale="A later review raised an unresolved issue.",
        decided_at=NOW + timedelta(seconds=1),
    )

    decisions.save_decision(first)
    decisions.save_decision(second)

    assert decisions.list_decisions_for_item(
        item.assessment_item_id,
        item_revision=1,
    ) == (first, second)


def test_missing_assessment_item_cannot_receive_decision(
    environment,
):
    _, _, _, decisions = environment

    with pytest.raises(
        LookupError,
        match="was not found",
    ):
        decisions.save_decision(
            make_decision()
        )


def test_wrong_item_revision_cannot_receive_decision(
    environment,
):
    _, _, items, decisions = environment

    item = make_item()

    items.save_item(
        item,
        revision=1,
    )

    decision = make_decision(
        item=item,
        item_revision=2,
    )

    with pytest.raises(
        LookupError,
        match="revision was not found",
    ):
        decisions.save_decision(decision)


def test_stored_item_content_mismatch_is_rejected(
    environment,
):
    _, _, items, decisions = environment

    stored_item = make_item()

    items.save_item(
        stored_item,
        revision=1,
    )

    different_item = make_item(
        prompt="A different question under the same item ID."
    )

    decision = make_decision(
        item=different_item
    )

    with pytest.raises(
        ValueError,
        match="stored Assessment Item content",
    ):
        decisions.save_decision(decision)


def test_review_decision_requires_valid_source_draft_binding():
    item = make_item()

    draft = make_draft(item)

    changed_item = make_item(
        prompt="Changed after the draft was created."
    )

    with pytest.raises(
        ValueError,
        match="content has changed",
    ):
        create_transfer_review_decision_v01(
            decision_id="review-decision-001",
            draft=draft,
            item=changed_item,
            item_revision=1,
            reviewer_id="reviewer-001",
            reviewer_identity_issuer="test-source",
            outcome=TransferReviewOutcomeV01.REJECT,
            rationale="The draft is stale.",
            decided_at=NOW,
        )


def test_draft_fingerprint_changes_with_review_content():
    item = make_item()

    first = make_draft(item)

    second = first.model_copy(
        update={
            "required_transfer_reasoning": (
                "A revised account of required reasoning."
            )
        }
    )

    assert fingerprint_transfer_review_draft_v01(
        first
    ) != fingerprint_transfer_review_draft_v01(
        second
    )


def test_decision_requires_nonblank_review_information():
    decision = make_decision()

    with pytest.raises(ValidationError):
        TransferReviewDecisionV01(
            **{
                **decision.model_dump(),
                "rationale": "   ",
            }
        )

    with pytest.raises(ValidationError):
        TransferReviewDecisionV01(
            **{
                **decision.model_dump(),
                "reviewer_id": "",
            }
        )


def test_decision_requires_valid_outcome_and_time():
    decision = make_decision()

    with pytest.raises(ValidationError):
        TransferReviewDecisionV01(
            **{
                **decision.model_dump(),
                "outcome": "unknown",
            }
        )

    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        TransferReviewDecisionV01(
            **{
                **decision.model_dump(),
                "decided_at": datetime(2026, 9, 20),
            }
        )


def test_recorded_approve_does_not_open_transfer_delivery_gate(
    environment,
):
    _, _, items, decisions = environment

    item = make_item()

    items.save_item(
        item,
        revision=1,
    )

    decision = make_decision(
        item=item,
        outcome=TransferReviewOutcomeV01.APPROVE,
    )

    decisions.save_decision(decision)

    assert decisions.load_decision(
        decision.decision_id
    ).outcome == TransferReviewOutcomeV01.APPROVE

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
        )

"""
URPP Implementation 13D-1C4.

Test historical Review Decision interpretation.

Every result remains descriptive and untrusted.
A recorded APPROVE never opens the Transfer Delivery Gate.
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
    create_transfer_review_decision_v01,
)

from app.services.assessment.transfer_review_lifecycle_v01 import (
    TransferReviewLifecycleStatusV01,
    evaluate_transfer_review_lifecycle_v01,
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
    item_id="transfer-item-001",
    prompt="Apply the same principle in a new context.",
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
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
):
    return create_transfer_design_review_draft_v01(
        item=item,
        item_revision=item_revision,
        source_learning_context="Previously taught setting.",
        target_application_context="New application setting.",
        changed_context_factors=(
            "Changed task presentation.",
        ),
        invariant_knowledge="The same mathematical principle.",
        required_transfer_reasoning=(
            "Recognize and apply the principle in new conditions."
        ),
        plausible_non_transfer_path=(
            "Memorizing a previously shown procedure."
        ),
        review_questions=(
            "Does the new task genuinely require transfer?",
        ),
        created_at=NOW,
    )


def make_decision(
    *,
    item=None,
    item_revision=1,
    decision_id="review-001",
    outcome=TransferReviewOutcomeV01.APPROVE,
    decided_at=NOW,
):
    if item is None:
        item = make_item()

    return create_transfer_review_decision_v01(
        decision_id=decision_id,
        draft=make_draft(
            item,
            item_revision=item_revision,
        ),
        item=item,
        item_revision=item_revision,
        reviewer_id="unverified-reviewer-001",
        reviewer_identity_issuer="test-record-source",
        outcome=outcome,
        rationale="Recorded review rationale.",
        decided_at=decided_at,
    )


def evaluate(
    decisions,
    *,
    item=None,
    item_revision=1,
    as_of=NOW + timedelta(minutes=5),
):
    if item is None:
        item = make_item()

    return evaluate_transfer_review_lifecycle_v01(
        item=item,
        item_revision=item_revision,
        decisions=decisions,
        as_of=as_of,
    )


def test_empty_history_has_no_decision():
    result = evaluate(())

    assert result.status == (
        TransferReviewLifecycleStatusV01.NO_DECISION
    )

    assert result.current_decision_id is None


def test_single_approve_is_only_recorded_approve_claim():
    decision = make_decision()

    result = evaluate((decision,))

    assert result.status == (
        TransferReviewLifecycleStatusV01.APPROVE_RECORDED
    )

    assert result.current_decision_id == decision.decision_id

    # No permission-to-deliver attribute is produced.
    assert not hasattr(
        result,
        "authorized_to_deliver",
    )


def test_later_reject_supersedes_earlier_recorded_approve():
    approved = make_decision(
        decision_id="review-001",
        outcome=TransferReviewOutcomeV01.APPROVE,
        decided_at=NOW,
    )

    rejected = make_decision(
        decision_id="review-002",
        outcome=TransferReviewOutcomeV01.REJECT,
        decided_at=NOW + timedelta(seconds=1),
    )

    result = evaluate(
        (approved, rejected)
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.REJECT_RECORDED
    )

    assert result.current_decision_id == "review-002"


def test_later_revoke_supersedes_earlier_recorded_approve():
    approved = make_decision(
        decision_id="review-001",
        outcome=TransferReviewOutcomeV01.APPROVE,
        decided_at=NOW,
    )

    revoked = make_decision(
        decision_id="review-002",
        outcome=TransferReviewOutcomeV01.REVOKE,
        decided_at=NOW + timedelta(seconds=1),
    )

    result = evaluate(
        (revoked, approved)
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.REVOKE_RECORDED
    )

    assert result.current_decision_id == "review-002"


def test_later_approve_after_revoke_is_new_recorded_claim():
    first_approval = make_decision(
        decision_id="review-001",
        outcome=TransferReviewOutcomeV01.APPROVE,
        decided_at=NOW,
    )

    revocation = make_decision(
        decision_id="review-002",
        outcome=TransferReviewOutcomeV01.REVOKE,
        decided_at=NOW + timedelta(seconds=1),
    )

    new_approval = make_decision(
        decision_id="review-003",
        outcome=TransferReviewOutcomeV01.APPROVE,
        decided_at=NOW + timedelta(seconds=2),
    )

    result = evaluate(
        (
            new_approval,
            first_approval,
            revocation,
        )
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.APPROVE_RECORDED
    )

    assert result.current_decision_id == "review-003"


def test_same_latest_timestamp_is_ambiguous():
    approved = make_decision(
        decision_id="review-001",
        outcome=TransferReviewOutcomeV01.APPROVE,
        decided_at=NOW,
    )

    revoked = make_decision(
        decision_id="review-002",
        outcome=TransferReviewOutcomeV01.REVOKE,
        decided_at=NOW,
    )

    first_order = evaluate(
        (approved, revoked)
    )

    reverse_order = evaluate(
        (revoked, approved)
    )

    assert first_order.status == (
        TransferReviewLifecycleStatusV01.AMBIGUOUS
    )

    assert reverse_order.status == (
        TransferReviewLifecycleStatusV01.AMBIGUOUS
    )

    assert first_order.current_decision_id is None
    assert reverse_order.current_decision_id is None


def test_same_latest_timestamp_is_ambiguous_even_if_both_approve():
    first = make_decision(
        decision_id="review-001",
        decided_at=NOW,
    )

    second = make_decision(
        decision_id="review-002",
        decided_at=NOW,
    )

    assert evaluate(
        (first, second)
    ).status == TransferReviewLifecycleStatusV01.AMBIGUOUS


def test_duplicate_decision_id_invalidates_history():
    decision = make_decision()

    result = evaluate(
        (decision, decision)
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.INVALID_HISTORY
    )

    assert result.current_decision_id is None


def test_different_item_identity_invalidates_history():
    other_item_decision = make_decision(
        item=make_item(
            item_id="different-item",
        )
    )

    result = evaluate(
        (other_item_decision,)
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.INVALID_HISTORY
    )


def test_different_item_revision_invalidates_history():
    revision_one = make_decision(
        item_revision=1,
    )

    result = evaluate(
        (revision_one,),
        item_revision=2,
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.INVALID_HISTORY
    )


def test_changed_item_content_invalidates_history():
    original = make_item()

    old_approval = make_decision(
        item=original,
    )

    changed = make_item(
        prompt="A revised assessment question.",
    )

    result = evaluate(
        (old_approval,),
        item=changed,
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.INVALID_HISTORY
    )


def test_future_dated_decision_invalidates_history():
    approved = make_decision(
        decision_id="review-001",
        decided_at=NOW,
    )

    future_rejection = make_decision(
        decision_id="review-002",
        outcome=TransferReviewOutcomeV01.REJECT,
        decided_at=NOW + timedelta(days=1),
    )

    result = evaluate(
        (approved, future_rejection),
        as_of=NOW + timedelta(minutes=1),
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.INVALID_HISTORY
    )


def test_non_time_aware_evaluation_is_rejected():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        evaluate(
            (),
            as_of=datetime(2026, 9, 20),
        )


def test_invalid_revision_is_rejected():
    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        evaluate(
            (),
            item_revision=0,
        )

    with pytest.raises(
        ValueError,
        match="positive integer",
    ):
        evaluate(
            (),
            item_revision=True,
        )


def test_wrong_decision_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="TransferReviewDecisionV01",
    ):
        evaluate(
            ("approve",)
        )


def test_recorded_approve_still_does_not_open_delivery_gate():
    result = evaluate(
        (make_decision(),)
    )

    assert result.status == (
        TransferReviewLifecycleStatusV01.APPROVE_RECORDED
    )

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
        )


def test_sqlite_history_survives_reopen_and_lifecycle_is_recomputed(
    tmp_path,
):
    database_path = tmp_path / "transfer_lifecycle.sqlite"

    def open_database(*, initialize):
        engine = create_engine(
            f"sqlite+pysqlite:///{database_path}"
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

        items = AssessmentRecordRepositoryV02(factory)

        reviews = TransferReviewDecisionRepositoryV01(
            factory
        )

        return engine, items, reviews

    first_engine, items, reviews = open_database(
        initialize=True
    )

    item = make_item()

    try:
        items.save_item(
            item,
            revision=1,
        )

        first = make_decision(
            decision_id="review-001",
            outcome=TransferReviewOutcomeV01.APPROVE,
            decided_at=NOW,
        )

        second = make_decision(
            decision_id="review-002",
            outcome=TransferReviewOutcomeV01.REVOKE,
            decided_at=NOW + timedelta(seconds=1),
        )

        reviews.save_decision(first)
        reviews.save_decision(second)

    finally:
        first_engine.dispose()

    reopened_engine, _, reopened_reviews = open_database(
        initialize=False
    )

    try:
        history = reopened_reviews.list_decisions_for_item(
            item.assessment_item_id,
            item_revision=1,
        )

        assert len(history) == 2

        result = evaluate(
            history,
            item=item,
        )

        assert result.status == (
            TransferReviewLifecycleStatusV01.REVOKE_RECORDED
        )

        assert result.current_decision_id == "review-002"

        # Persistent history does not create trusted approval.
        with pytest.raises(
            ValueError,
            match="requires a trusted Transfer Design Approval",
        ):
            require_trusted_transfer_delivery_v01(
                selected_action=(
                    TeachingActionV01.TRANSFER_ASSESSMENT
                ),
            )

    finally:
        reopened_engine.dispose()

"""
URPP Implementation 13D-1B.

Test the Transfer Design Review draft and its binding
to one concrete Assessment Item revision.

These tests do not represent reviewer approval.
"""

from datetime import datetime, timezone

import pytest

from pydantic import ValidationError

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.assessment.transfer_design_review_v01 import (
    TransferDesignReviewDraftV01,
    create_transfer_design_review_draft_v01,
    fingerprint_assessment_item_v01,
    require_current_transfer_review_binding_v01,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


def make_item(
    *,
    item_id="transfer-item-001",
    evidence_type=EvidenceType.TRANSFER_ATTEMPT,
    alignment_verified=True,
    prompt="Apply the same principle in a new task context.",
    expected=5.0,
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id="objective-001",
        prompt=prompt,
        evidence_type=evidence_type,
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=alignment_verified,
    )


def make_draft(
    *,
    item=None,
    item_revision=1,
    **overrides,
):
    if item is None:
        item = make_item()

    fields = {
        "source_learning_context":
            "The student practiced the principle in a "
            "previously taught numerical setting.",

        "target_application_context":
            "The student must recognize the same principle "
            "in a different application setting.",

        "changed_context_factors": (
            "Different task presentation.",
            "Different contextual cues.",
        ),

        "invariant_knowledge":
            "The mathematical principle remains applicable.",

        "required_transfer_reasoning":
            "Identify the principle despite changed cues "
            "and justify its application.",

        "plausible_non_transfer_path":
            "The student might reproduce a memorized "
            "procedure without recognizing the principle.",

        "review_questions": (
            "Does the target task require recognizing "
            "the principle in the changed context?",
            "Could the task be solved by copying "
            "a previously shown solution?",
        ),

        "created_at": NOW,
    }

    fields.update(overrides)

    return create_transfer_design_review_draft_v01(
        item=item,
        item_revision=item_revision,
        **fields,
    )


def test_draft_is_bound_to_exact_item_and_revision():
    item = make_item()

    draft = make_draft(
        item=item,
        item_revision=3,
    )

    assert draft.assessment_item_id == item.assessment_item_id
    assert draft.item_revision == 3

    assert draft.item_content_sha256 == (
        fingerprint_assessment_item_v01(item)
    )

    require_current_transfer_review_binding_v01(
        draft=draft,
        item=item,
        item_revision=3,
    )


def test_same_item_content_produces_same_fingerprint():
    item = make_item()

    same_content = make_item()

    assert fingerprint_assessment_item_v01(item) == (
        fingerprint_assessment_item_v01(same_content)
    )


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [
        (
            "prompt",
            "A different transfer task.",
        ),
        (
            "rubric",
            NumericRubricV02(
                expected_value=7.0,
                absolute_tolerance=0.0,
                rubric_version="numeric-rubric-v1",
            ),
        ),
        (
            "evidence_type",
            EvidenceType.PROBLEM_ATTEMPT,
        ),
        (
            "alignment_verified",
            False,
        ),
    ],
)
def test_modified_item_content_invalidates_draft_binding(
    changed_field,
    changed_value,
):
    item = make_item()

    draft = make_draft(item=item)

    modified_item = item.model_copy(
        update={changed_field: changed_value}
    )

    with pytest.raises(
        ValueError,
        match="content has changed",
    ):
        require_current_transfer_review_binding_v01(
            draft=draft,
            item=modified_item,
            item_revision=1,
        )


def test_revision_change_invalidates_binding():
    item = make_item()

    draft = make_draft(
        item=item,
        item_revision=1,
    )

    with pytest.raises(
        ValueError,
        match="identity or revision",
    ):
        require_current_transfer_review_binding_v01(
            draft=draft,
            item=item,
            item_revision=2,
        )


def test_different_item_identity_invalidates_binding():
    item = make_item()

    draft = make_draft(item=item)

    another_item = make_item(
        item_id="transfer-item-002"
    )

    with pytest.raises(
        ValueError,
        match="identity or revision",
    ):
        require_current_transfer_review_binding_v01(
            draft=draft,
            item=another_item,
            item_revision=1,
        )


def test_ordinary_problem_cannot_create_transfer_draft():
    with pytest.raises(
        ValueError,
        match="transfer-tagged Assessment Item",
    ):
        make_draft(
            item=make_item(
                evidence_type=EvidenceType.PROBLEM_ATTEMPT
            )
        )


def test_unverified_alignment_cannot_create_draft():
    with pytest.raises(
        ValueError,
        match="alignment is not verified",
    ):
        make_draft(
            item=make_item(
                alignment_verified=False
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "source_learning_context",
            "   ",
        ),
        (
            "target_application_context",
            "",
        ),
        (
            "invariant_knowledge",
            "   ",
        ),
        (
            "required_transfer_reasoning",
            "",
        ),
        (
            "plausible_non_transfer_path",
            "   ",
        ),
        (
            "changed_context_factors",
            (),
        ),
        (
            "changed_context_factors",
            ("Valid change.", "   "),
        ),
        (
            "review_questions",
            (),
        ),
    ],
)
def test_draft_requires_nonempty_review_information(
    field,
    value,
):
    with pytest.raises(ValidationError):
        make_draft(**{field: value})


def test_creation_timestamp_must_be_timezone_aware():
    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        make_draft(
            created_at=datetime(2026, 9, 19)
        )


def test_revision_must_be_positive_integer():
    with pytest.raises(ValidationError):
        make_draft(item_revision=0)

    with pytest.raises(ValidationError):
        make_draft(item_revision=True)


def test_draft_has_no_approval_or_reviewer_authority_field():
    draft = make_draft()

    assert "approved" not in TransferDesignReviewDraftV01.model_fields
    assert "reviewer_authorized" not in TransferDesignReviewDraftV01.model_fields

    with pytest.raises(ValidationError):
        TransferDesignReviewDraftV01(
            **draft.model_dump(),
            approved=True,
        )


def test_binding_check_does_not_claim_review_approval():
    item = make_item()

    draft = make_draft(item=item)

    result = require_current_transfer_review_binding_v01(
        draft=draft,
        item=item,
        item_revision=1,
    )

    # Success means that the draft still describes the
    # supplied item snapshot. It is not an approval result.
    assert result is None

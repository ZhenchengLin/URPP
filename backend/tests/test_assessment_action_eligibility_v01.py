"""
URPP Implementation 13D-1A.

Structural Action–Item compatibility tests.

Passing this guard does not prove genuine knowledge transfer
or independently performed work.
"""

import pytest

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.assessment_action_eligibility_v01 import (
    require_eligible_assessment_action_v01,
)

from app.services.decision.models_v01 import TeachingActionV01


def make_item(
    *,
    evidence_type=EvidenceType.PROBLEM_ATTEMPT,
    alignment_verified=True,
):
    return AssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="What is 2 + 3?",
        evidence_type=evidence_type,
        rubric=NumericRubricV02(
            expected_value=5.0,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=alignment_verified,
    )


@pytest.mark.parametrize(
    "action",
    [
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
        TeachingActionV01.INDEPENDENT_PRACTICE,
    ],
)
def test_ordinary_problem_supports_nontransfer_assessment_actions(
    action,
):
    require_eligible_assessment_action_v01(
        selected_action=action,
        item=make_item(),
    )


def test_transfer_action_rejects_ordinary_problem():
    with pytest.raises(
        ValueError,
        match="requires a transfer-tagged Assessment Item",
    ):
        require_eligible_assessment_action_v01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
            item=make_item(),
        )


def test_transfer_tag_satisfies_only_structural_requirement():
    """
    This test checks the item-type contract, not whether its
    content is a genuinely reviewed transfer problem.
    """

    require_eligible_assessment_action_v01(
        selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
        item=make_item(
            evidence_type=EvidenceType.TRANSFER_ATTEMPT
        ),
    )


@pytest.mark.parametrize(
    "action",
    [
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
        TeachingActionV01.INDEPENDENT_PRACTICE,
        TeachingActionV01.TRANSFER_ASSESSMENT,
    ],
)
def test_unverified_objective_alignment_is_rejected(
    action,
):
    with pytest.raises(
        ValueError,
        match="alignment is not verified",
    ):
        require_eligible_assessment_action_v01(
            selected_action=action,
            item=make_item(
                evidence_type=EvidenceType.TRANSFER_ATTEMPT,
                alignment_verified=False,
            ),
        )


def test_professor_action_cannot_issue_numeric_assignment():
    with pytest.raises(
        ValueError,
        match="requires an assessment action",
    ):
        require_eligible_assessment_action_v01(
            selected_action=TeachingActionV01.CONCEPTUAL_REVIEW,
            item=make_item(),
        )


def test_invalid_item_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="AssessmentItemV02",
    ):
        require_eligible_assessment_action_v01(
            selected_action=TeachingActionV01.INDEPENDENT_PRACTICE,
            item=object(),
        )

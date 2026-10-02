"""
URPP Implementation 13D-1A.

Validate the structural compatibility of a selected
Teaching Action and an existing Assessment Item.

This guard does not establish that a Transfer task genuinely
measures knowledge transfer, or that a student's answer
demonstrates independent performance.
"""

from app.domain.learning.models import EvidenceType

from app.services.assessment.models_v02 import AssessmentItemV02

from app.services.decision.models_v01 import TeachingActionV01

from app.services.decision.turn_orchestrator_v01 import (
    ASSESSMENT_ACTIONS,
)


def require_eligible_assessment_action_v01(
    *,
    selected_action: TeachingActionV01,
    item: AssessmentItemV02,
) -> None:
    """
    Reject an Assessment Action that cannot be represented
    by the supplied stored Assessment Item.

    A TRANSFER_ASSESSMENT action requires an item explicitly
    tagged TRANSFER_ATTEMPT. This is a necessary structural
    condition, not proof of a reviewed transfer design.

    The existing Session remains responsible for checking
    the item revision, course, Objective, and alignment.
    """

    if not isinstance(selected_action, TeachingActionV01):
        raise TypeError(
            "selected_action must be TeachingActionV01."
        )

    if not isinstance(item, AssessmentItemV02):
        raise TypeError(
            "item must be AssessmentItemV02."
        )

    if selected_action not in ASSESSMENT_ACTIONS:
        raise ValueError(
            "Numeric Assignment requires an assessment action."
        )

    if not item.alignment_verified:
        raise ValueError(
            "Assessment objective alignment is not verified."
        )

    if (
        selected_action == TeachingActionV01.TRANSFER_ASSESSMENT
        and item.evidence_type != EvidenceType.TRANSFER_ATTEMPT
    ):
        raise ValueError(
            "Transfer assessment requires a transfer-tagged "
            "Assessment Item; an ordinary problem cannot be "
            "relabelled by a student request."
        )

"""
URPP Implementation 13D-1C1.

The current Recoverable Numeric Session must not treat
a transfer-tagged item as an approved Transfer Assessment.
"""

import pytest

from app.services.decision.models_v01 import TeachingActionV01

from app.services.decision.transfer_delivery_gate_v01 import (
    require_trusted_transfer_delivery_v01,
)


@pytest.mark.parametrize(
    "action",
    [
        TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
        TeachingActionV01.INDEPENDENT_PRACTICE,
    ],
)
def test_nontransfer_assessment_actions_are_not_blocked(
    action,
):
    require_trusted_transfer_delivery_v01(
        selected_action=action,
    )


def test_transfer_assessment_fails_closed_without_trusted_approval():
    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
        )


def test_invalid_action_type_is_rejected():
    with pytest.raises(
        TypeError,
        match="TeachingActionV01",
    ):
        require_trusted_transfer_delivery_v01(
            selected_action="transfer_assessment",
        )


def test_gate_has_no_caller_supplied_approval_override():
    with pytest.raises(TypeError):
        require_trusted_transfer_delivery_v01(
            selected_action=TeachingActionV01.TRANSFER_ASSESSMENT,
            approved=True,
        )

"""
URPP Implementation 13D-1C1.

Fail-closed Transfer Assessment delivery boundary.

This version does not accept reviewer-provided approval
objects, caller-supplied approval flags, or LLM approval text.

Until trusted approval authorization and persistence exist,
Transfer Assessment delivery is disabled through this gate.
"""

from app.services.decision.models_v01 import TeachingActionV01


def require_trusted_transfer_delivery_v01(
    *,
    selected_action: TeachingActionV01,
) -> None:
    """
    Permit ordinary assessment actions to proceed.

    Reject TRANSFER_ASSESSMENT because the current system
    has no trusted Transfer Design Approval source.

    The function returning successfully is not evidence
    of student mastery or assessment validity.
    """

    if not isinstance(
        selected_action,
        TeachingActionV01,
    ):
        raise TypeError(
            "selected_action must be TeachingActionV01."
        )

    if selected_action == TeachingActionV01.TRANSFER_ASSESSMENT:
        raise ValueError(
            "Transfer Assessment delivery requires a trusted "
            "Transfer Design Approval. No trusted approval "
            "source is configured."
        )

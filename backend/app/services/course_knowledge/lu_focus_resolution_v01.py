"""
URPP 14C-5D-13E: LU Focus Classification Boundary.

Classify caller-supplied focus identifiers without treating
their contents as proof of caller identity or authorization.

This module does NOT:
- authenticate the caller or verify focus provenance;
- resolve an authorized teaching focus;
- infer focus from natural-language student input;
- call the deterministic LU teaching router;
- consume NanoJev shadow proposals;
- render, persist, or deliver teaching;
- read or modify Student State, Teaching Trace, or Mastery Evidence.

A single supported focus is a candidate requiring source
verification, not an authorized routing instruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


REGISTERED_LU_FOCI_V01 = frozenset({
    "sign_relation",
    "calculation",
})


LUFocusCandidateStatusV01 = Literal[
    "needs_source_verification",
    "needs_clarification",
    "unsupported",
]


@dataclass(frozen=True)
class LUFocusRequestV01:
    """
    A bounded collection of explicitly supplied focus IDs.

    requested_focus_ids represents caller-supplied data.

    Constructing this object does not establish that the
    caller is a student, that the focus was selected by
    the student, or that the request is authorized.
    """

    requested_focus_ids: tuple[str, ...]


@dataclass(frozen=True)
class LUFocusClassificationV01:
    """
    Developer-only, non-authoritative classification.

    candidate_focus_id may be present only when exactly one
    supported focus was supplied.

    No result produced by this component is permitted to
    authorize teaching-plan selection or student delivery.
    """

    status: LUFocusCandidateStatusV01

    candidate_focus_id: str | None

    reason_code: Literal[
        "single_supported_focus_unverified",
        "missing_focus",
        "conflicting_foci",
        "unsupported_focus",
    ]

    routing_authorized: Literal[False] = False

    student_delivery_authorized: Literal[False] = False

    status_scope: Literal[
        "developer_audit_only"
    ] = "developer_audit_only"


def classify_lu_focus_request_v01(
    request: LUFocusRequestV01,
) -> LUFocusClassificationV01:
    """
    Classify explicitly provided focus identifiers.

    This is structural validation, not provenance validation.

    A syntactically supported identifier cannot advance to
    an authorized 'resolved' state through this interface.
    """

    if type(request) is not LUFocusRequestV01:
        raise TypeError(
            "Expected LUFocusRequestV01."
        )

    focus_ids = request.requested_focus_ids

    if type(focus_ids) is not tuple:
        raise TypeError(
            "requested_focus_ids must be a tuple."
        )

    if len(focus_ids) > 8:
        raise ValueError(
            "Too many focus identifiers."
        )

    for focus_id in focus_ids:

        if type(focus_id) is not str:
            raise TypeError(
                "Every focus identifier must be a string."
            )

        if len(focus_id) > 128:
            raise ValueError(
                "Focus identifier exceeds the size limit."
            )

    if not focus_ids or all(
        not focus_id.strip()
        for focus_id in focus_ids
    ):
        return LUFocusClassificationV01(
            status="needs_clarification",
            candidate_focus_id=None,
            reason_code="missing_focus",
        )

    # Multiple supplied identifiers cannot be silently
    # reduced to one teaching focus.
    #
    # In particular, a supported ID must not override a
    # contradictory or unsupported accompanying ID.

    if len(focus_ids) != 1:
        return LUFocusClassificationV01(
            status="needs_clarification",
            candidate_focus_id=None,
            reason_code="conflicting_foci",
        )

    focus_id = focus_ids[0]

    if not focus_id.strip():
        return LUFocusClassificationV01(
            status="needs_clarification",
            candidate_focus_id=None,
            reason_code="missing_focus",
        )

    if focus_id not in REGISTERED_LU_FOCI_V01:
        return LUFocusClassificationV01(
            status="unsupported",
            candidate_focus_id=None,
            reason_code="unsupported_focus",
        )

    return LUFocusClassificationV01(
        status="needs_source_verification",
        candidate_focus_id=focus_id,
        reason_code="single_supported_focus_unverified",
    )

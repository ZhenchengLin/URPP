"""
URPP 14C-5D-13H: Session-Scoped LU Focus Preflight.

Combines non-authoritative Focus Classification with a
read-only check of an existing stored Numeric Session.

Matching stored identity fields does not authenticate
the caller or authorize access to that Session.

This component does not:
- authenticate students or authorize session access;
- issue an authorized or resolved LU Focus;
- call the LU teaching router or renderer;
- access NanoJev;
- write Student State, Teaching Trace, or Mastery Evidence;
- authorize student-facing teaching.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.repositories.numeric_session_records_v01 import (
    StoredNumericSessionV01,
)

from app.services.course_knowledge.lu_focus_resolution_v01 import (
    LUFocusClassificationV01,
    LUFocusRequestV01,
    classify_lu_focus_request_v01,
)


@dataclass(frozen=True)
class LUFocusSessionPreflightV01:
    classification: LUFocusClassificationV01

    session_scope_matched: bool

    caller_authenticated: Literal[False] = False

    routing_authorized: Literal[False] = False

    student_delivery_authorized: Literal[False] = False

    status: Literal[
        "developer_audit_only"
    ] = "developer_audit_only"


def _require_identifier(value: str, name: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 128
    ):
        raise ValueError(
            f"{name} must be a nonempty string "
            "of at most 128 characters."
        )

    return value


def inspect_lu_focus_session_v01(
    *,
    request: LUFocusRequestV01,
    session_repository,
    session_id: str,
    student_id: str,
    course_id: str,
    objective_id: str,
) -> LUFocusSessionPreflightV01:
    """
    Perform an internal, non-authorizing scope check.

    A stored Session match does not prove who supplied
    student_id or whether that caller may access it.
    """

    # First classify the request. Unsupported, missing,
    # or conflicting focus inputs never trigger a Session read.

    classification = classify_lu_focus_request_v01(
        request
    )

    if classification.status != "needs_source_verification":
        return LUFocusSessionPreflightV01(
            classification=classification,
            session_scope_matched=False,
        )

    identifiers = {
        "session_id": session_id,
        "student_id": student_id,
        "course_id": course_id,
        "objective_id": objective_id,
    }

    for name, value in identifiers.items():
        _require_identifier(value, name)

    load = getattr(session_repository, "load", None)

    if not callable(load):
        raise TypeError(
            "Expected a Session Repository with a load method."
        )

    # The existing Repository performs its own persistent
    # Session lookup and requested-scope checks.
    #
    # This call is read-only. The caller is not authenticated
    # by passing a matching set of identifiers.

    stored = load(
        session_id=session_id,
        student_id=student_id,
        course_id=course_id,
        objective_id=objective_id,
    )

    if type(stored) is not StoredNumericSessionV01:
        raise TypeError(
            "Session Repository returned an invalid record."
        )

    if (
        stored.session_id != session_id
        or stored.student_id != student_id
        or stored.course_id != course_id
        or stored.objective_id != objective_id
    ):
        raise ValueError(
            "Stored Session scope does not match the request."
        )

    return LUFocusSessionPreflightV01(
        classification=classification,
        session_scope_matched=True,
    )

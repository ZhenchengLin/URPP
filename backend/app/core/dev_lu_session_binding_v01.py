"""
URPP 14C-5D-13J-7.

Developer-only Credential-to-Session identity binding.

This component verifies a developer Bearer credential before
using its configured synthetic student identity in the existing
LU Focus Session Preflight.

It does not establish production student authentication,
Session access authorization, teaching-plan selection,
or student-facing delivery.

No public API route uses this component.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.dev_caller_credential_v01 import (
    DevBearerCredentialVerifierV01,
    DevCallerObservationV01,
)

from app.services.course_knowledge.lu_focus_resolution_v01 import (
    LUFocusRequestV01,
)

from app.services.course_knowledge.lu_focus_session_preflight_v01 import (
    LUFocusSessionPreflightV01,
    inspect_lu_focus_session_v01,
)


@dataclass(frozen=True)
class DevLUSessionBindingResultV01:
    """
    An internal audit result, not an authorization credential.

    Python callers can fabricate this object. No downstream
    authorization decision may rely on possession of it.
    """

    synthetic_student_id: str

    preflight: LUFocusSessionPreflightV01

    status: Literal["developer_audit_only"] = (
        "developer_audit_only"
    )

    session_access_authorized: Literal[False] = False

    lu_routing_authorized: Literal[False] = False

    student_delivery_authorized: Literal[False] = False


class DevLUSessionBindingV01:
    """
    Bind one developer credential to one synthetic Session check.

    The configured token and synthetic student ID must originate
    from trusted local server configuration, never request data.

    This class does not accept a caller-provided principal
    or a caller-provided student_id in its inspect method.
    """

    def __init__(
        self,
        *,
        configured_token: str,
        synthetic_student_id: str,
        session_repository,
    ) -> None:

        self._verifier = DevBearerCredentialVerifierV01(
            configured_token=configured_token,
            synthetic_student_id=synthetic_student_id,
        )

        self._expected_student_id = synthetic_student_id

        self._session_repository = session_repository

    def inspect(
        self,
        *,
        authorization_header: str | None,
        focus_request: LUFocusRequestV01,
        session_id: str,
        course_id: str,
        objective_id: str,
    ) -> DevLUSessionBindingResultV01:
        """
        Verify the supplied credential before any Session lookup.

        The caller cannot supply student_id or an already
        constructed DevCallerObservationV01 as input.

        The resulting record is audit-only.
        """

        observation = self._verifier.verify_bearer_header(
            authorization_header
        )

        if (
            type(observation) is not DevCallerObservationV01
            or observation.synthetic_student_id
            != self._expected_student_id
        ):
            raise RuntimeError(
                "Developer credential identity mismatch."
            )

        preflight = inspect_lu_focus_session_v01(
            request=focus_request,
            session_repository=self._session_repository,
            session_id=session_id,
            student_id=observation.synthetic_student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        if type(preflight) is not LUFocusSessionPreflightV01:
            raise TypeError(
                "Invalid LU Focus Session Preflight result."
            )

        if (
            preflight.caller_authenticated is not False
            or preflight.routing_authorized is not False
            or preflight.student_delivery_authorized is not False
        ):
            raise RuntimeError(
                "Session Preflight crossed its authority boundary."
            )

        return DevLUSessionBindingResultV01(
            synthetic_student_id=observation.synthetic_student_id,
            preflight=preflight,
        )

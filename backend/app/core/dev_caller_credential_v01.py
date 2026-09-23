"""
URPP 14C-5D-13J-5.

Developer-only verification of an opaque Bearer credential.

This is an isolated local-development prototype, not a
production student authentication service.

The configured credential and synthetic student identity
must originate from trusted server-side configuration.

A successful match does not authorize:
- access to any stored Session;
- LU Focus resolution or teaching-plan selection;
- Student State or evidence writes;
- student-facing teaching delivery.

No API route uses this component.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import re
from typing import Literal


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43,256}\Z")


class DevCredentialRejectedV01(ValueError):
    """A developer credential was not accepted."""


@dataclass(frozen=True)
class DevCallerObservationV01:
    """
    Records a successful developer credential match.

    This object is not a credential, access grant,
    production authenticated principal, or authorization
    capability. Python callers can fabricate dataclasses.
    """

    synthetic_student_id: str

    status: Literal["developer_audit_only"] = (
        "developer_audit_only"
    )

    session_access_authorized: Literal[False] = False

    lu_routing_authorized: Literal[False] = False

    student_delivery_authorized: Literal[False] = False


class DevBearerCredentialVerifierV01:
    """
    Verify possession of one server-configured development token.

    This component must not be configured from request parameters
    or made available as a public student-login mechanism.
    """

    def __init__(
        self,
        *,
        configured_token: str,
        synthetic_student_id: str,
    ) -> None:

        if (
            type(configured_token) is not str
            or _TOKEN_PATTERN.fullmatch(configured_token) is None
        ):
            raise ValueError(
                "Invalid server-side development credential configuration."
            )

        if (
            type(synthetic_student_id) is not str
            or not synthetic_student_id.strip()
            or len(synthetic_student_id) > 128
        ):
            raise ValueError(
                "Invalid synthetic student identity configuration."
            )

        # Do not retain the plaintext configured token.
        # This digest is used only for developer credential
        # comparison; it does not establish a production
        # authentication or session-management mechanism.
        self._expected_digest = sha256(
            configured_token.encode("ascii")
        ).digest()

        self._synthetic_student_id = synthetic_student_id

    def verify_bearer_header(
        self,
        authorization_header: str | None,
    ) -> DevCallerObservationV01:
        """
        Verify an exact Bearer header.

        Never accept caller-provided authenticated flags,
        student IDs, or principal-like objects as proof.
        """

        if (
            type(authorization_header) is not str
            or len(authorization_header) > 263
            or not authorization_header.startswith("Bearer ")
        ):
            raise DevCredentialRejectedV01(
                "Developer credential rejected."
            )

        supplied_token = authorization_header[len("Bearer "):]

        if _TOKEN_PATTERN.fullmatch(supplied_token) is None:
            raise DevCredentialRejectedV01(
                "Developer credential rejected."
            )

        supplied_digest = sha256(
            supplied_token.encode("ascii")
        ).digest()

        if not compare_digest(
            self._expected_digest,
            supplied_digest,
        ):
            raise DevCredentialRejectedV01(
                "Developer credential rejected."
            )

        return DevCallerObservationV01(
            synthetic_student_id=self._synthetic_student_id,
        )

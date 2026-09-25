"""
URPP 14C-5D-13J-5 offline tests.

Synthetic credentials only.
No external authentication provider, network, database,
student-facing route, or teaching execution.
"""

from dataclasses import replace

import pytest

from app.core.dev_caller_credential_v01 import (
    DevBearerCredentialVerifierV01,
    DevCredentialRejectedV01,
)


TEST_TOKEN = "A" * 43

SYNTHETIC_STUDENT_ID = "synthetic-student-001"


def verifier():
    return DevBearerCredentialVerifierV01(
        configured_token=TEST_TOKEN,
        synthetic_student_id=SYNTHETIC_STUDENT_ID,
    )


def test_matching_credential_produces_developer_observation():
    result = verifier().verify_bearer_header(
        "Bearer " + TEST_TOKEN
    )

    assert result.synthetic_student_id == SYNTHETIC_STUDENT_ID
    assert result.status == "developer_audit_only"

    assert result.session_access_authorized is False
    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer ",
        "Bearer incorrect",
        "bearer " + TEST_TOKEN,
        "Basic " + TEST_TOKEN,
        "Bearer  " + TEST_TOKEN,
        "Bearer " + TEST_TOKEN + " ",
        "Bearer " + TEST_TOKEN + "\n",
        "Bearer " + ("B" * 43),
        "Bearer " + ("A" * 257),
        True,
        {"authenticated": True},
    ],
)
def test_invalid_credential_rejected(header):
    with pytest.raises(
        DevCredentialRejectedV01,
        match="Developer credential rejected",
    ):
        verifier().verify_bearer_header(header)


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "short",
        "A" * 42,
        "A" * 257,
        "A" * 42 + "!",
    ],
)
def test_invalid_server_credential_configuration_rejected(token):
    with pytest.raises(ValueError):
        DevBearerCredentialVerifierV01(
            configured_token=token,
            synthetic_student_id=SYNTHETIC_STUDENT_ID,
        )


@pytest.mark.parametrize(
    "student_id",
    [
        None,
        "",
        " ",
        "x" * 129,
        True,
    ],
)
def test_invalid_synthetic_identity_configuration_rejected(
    student_id,
):
    with pytest.raises(ValueError):
        DevBearerCredentialVerifierV01(
            configured_token=TEST_TOKEN,
            synthetic_student_id=student_id,
        )


def test_developer_observation_is_not_an_authorization_grant():
    result = verifier().verify_bearer_header(
        "Bearer " + TEST_TOKEN
    )

    # A caller can fabricate a modified dataclass.
    # Downstream components must not accept such fields
    # as evidence of Session or teaching authorization.
    forged = replace(
        result,
        session_access_authorized=True,
    )

    assert forged.session_access_authorized is True
    assert result.session_access_authorized is False

    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False


def test_no_token_is_exposed_in_verifier_representation():
    instance = verifier()

    assert TEST_TOKEN not in repr(instance)
    assert TEST_TOKEN not in repr(instance.__dict__)


def test_no_lu_teaching_execution(monkeypatch):
    from app.services.course_knowledge import (
        controlled_lu_teaching_v01,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Credential verification must not execute teaching."
        )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "select_pilot_plan_v01",
        forbidden,
    )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "render_verified_lu_pilot_v01",
        forbidden,
    )

    result = verifier().verify_bearer_header(
        "Bearer " + TEST_TOKEN
    )

    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False

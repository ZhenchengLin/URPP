"""
URPP 14C-5D-13E: LU Focus Classification tests.

All inputs are synthetic.

No model, network, database, student record, teaching
execution, or student-facing delivery is involved.
"""

from dataclasses import FrozenInstanceError, replace

import pytest

from app.services.course_knowledge import (
    controlled_lu_teaching_v01,
)

from app.services.course_knowledge.lu_focus_resolution_v01 import (
    LUFocusRequestV01,
    classify_lu_focus_request_v01,
)


def classify(*focus_ids):
    return classify_lu_focus_request_v01(
        LUFocusRequestV01(
            requested_focus_ids=focus_ids,
        )
    )


@pytest.mark.parametrize(
    "focus_id",
    [
        "sign_relation",
        "calculation",
    ],
)
def test_single_supported_focus_requires_source_verification(
    focus_id,
):
    result = classify(focus_id)

    assert result.status == "needs_source_verification"
    assert result.candidate_focus_id == focus_id

    assert result.reason_code == (
        "single_supported_focus_unverified"
    )

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False
    assert result.status_scope == "developer_audit_only"


@pytest.mark.parametrize(
    "focus_ids",
    [
        (),
        ("",),
        ("   ",),
        ("", " "),
    ],
)
def test_missing_focus_needs_clarification(focus_ids):
    result = classify(*focus_ids)

    assert result.status == "needs_clarification"
    assert result.candidate_focus_id is None
    assert result.reason_code == "missing_focus"

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "focus_ids",
    [
        ("sign_relation", "calculation"),
        ("calculation", "sign_relation"),
        ("sign_relation", "sign_relation"),
        ("calculation", "calculation"),
        ("sign_relation", "unknown"),
        ("sign_relation", ""),
    ],
)
def test_multiple_focus_inputs_cannot_be_reduced_to_one(
    focus_ids,
):
    result = classify(*focus_ids)

    assert result.status == "needs_clarification"
    assert result.candidate_focus_id is None
    assert result.reason_code == "conflicting_foci"

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "focus_id",
    [
        "unknown",
        "Sign_Relation",
        " sign_relation",
        "sign_relation ",
        "execute_python",
        "ask_row_operation",
        "untrusted_shadow_model",
    ],
)
def test_unsupported_focus_is_not_silently_mapped(
    focus_id,
):
    result = classify(focus_id)

    assert result.status == "unsupported"
    assert result.candidate_focus_id is None
    assert result.reason_code == "unsupported_focus"

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "sign_relation",
        ["sign_relation"],
        {"requested_focus_ids": ("sign_relation",)},
    ],
)
def test_request_type_is_strict(invalid):
    with pytest.raises(TypeError):
        classify_lu_focus_request_v01(invalid)


@pytest.mark.parametrize(
    "invalid_ids",
    [
        None,
        "sign_relation",
        ["sign_relation"],
        (None,),
        (True,),
        (1,),
        (b"sign_relation",),
    ],
)
def test_identifier_container_and_element_types_are_strict(
    invalid_ids,
):
    with pytest.raises(TypeError):
        classify_lu_focus_request_v01(
            LUFocusRequestV01(
                requested_focus_ids=invalid_ids,
            )
        )


def test_request_size_limits():
    with pytest.raises(ValueError):
        classify(*(["sign_relation"] * 9))

    with pytest.raises(ValueError):
        classify("x" * 129)


def test_result_and_request_are_immutable():
    request = LUFocusRequestV01(
        requested_focus_ids=("sign_relation",)
    )

    result = classify_lu_focus_request_v01(request)

    with pytest.raises(FrozenInstanceError):
        request.requested_focus_ids = ("calculation",)

    with pytest.raises(FrozenInstanceError):
        result.routing_authorized = True


def test_caller_supplied_fields_cannot_assert_authority():
    with pytest.raises(TypeError):
        LUFocusRequestV01(
            requested_focus_ids=("sign_relation",),
            routing_authorized=True,
        )

    with pytest.raises(TypeError):
        LUFocusRequestV01(
            requested_focus_ids=("sign_relation",),
            verified_source="trusted",
        )


def test_status_cannot_be_promoted_to_authorized_resolution():
    result = classify("sign_relation")

    assert result.status != "resolved"
    assert result.routing_authorized is False

    # dataclasses.replace is capable of constructing a new
    # object. The result type itself is NOT an authorization
    # credential and must never be accepted as one.
    forged = replace(
        result,
        routing_authorized=True,
    )

    assert forged.routing_authorized is True

    # This demonstrates why a future execution boundary
    # cannot trust caller-provided dataclass fields.


def test_focus_classification_does_not_call_router_or_renderer(
    monkeypatch,
):
    def forbidden_call(*args, **kwargs):
        raise AssertionError(
            "Focus classification must not execute teaching."
        )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "select_pilot_plan_v01",
        forbidden_call,
    )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "render_verified_lu_pilot_v01",
        forbidden_call,
    )

    for focus_ids in (
        ("sign_relation",),
        ("calculation",),
        (),
        ("sign_relation", "calculation"),
        ("unknown",),
    ):
        result = classify(*focus_ids)

        assert result.routing_authorized is False
        assert result.student_delivery_authorized is False


def test_shadow_plan_cannot_be_used_as_focus_request():
    shadow_plan = (
        controlled_lu_teaching_v01.validate_shadow_proposal_v01(
            {
                "plan_id": "sign_first",
                "check_id": "ask_sign_relation",
            }
        )
    )

    with pytest.raises(TypeError):
        classify_lu_focus_request_v01(shadow_plan)

    with pytest.raises(TypeError):
        classify_lu_focus_request_v01(
            LUFocusRequestV01(
                requested_focus_ids=(shadow_plan,),
            )
        )


def test_existing_deterministic_router_is_unchanged():
    sign_plan = (
        controlled_lu_teaching_v01.select_pilot_plan_v01(
            "sign_relation"
        )
    )

    calculation_plan = (
        controlled_lu_teaching_v01.select_pilot_plan_v01(
            "calculation"
        )
    )

    assert sign_plan.plan_id == "sign_first"
    assert sign_plan.check_id == "ask_sign_relation"

    assert calculation_plan.plan_id == "calculation_first"
    assert calculation_plan.check_id == "ask_row_operation"

    assert sign_plan.origin == "deterministic_lu_pilot"
    assert calculation_plan.origin == "deterministic_lu_pilot"

"""
URPP 14C-5D-1 NanoJev Adapter tests.

No model inference.
No external services.
No database.
No student-state modifications.
"""

import json
from copy import deepcopy

import pytest

from app.services.course_knowledge.nanojev_shadow_adapter_v01 import (
    STATE_ID,
    PLAN_QUESTION_ID,
    CHECK_QUESTION_ID,
    PLAN_CRITERIA,
    CHECK_CRITERIA,
    build_nanojev_lu_request_v01,
    validate_nanojev_lu_response_v01,
    parse_nanojev_lu_response_v01,
)


# ============================================================
# SYNTHETIC NANOJEV RESPONSE
# ============================================================

def valid_response():

    return {

        "schema_version": "openjev-toy-inference-v1",

        "states": [
            {
                "id": STATE_ID,

                "answers": {

                    PLAN_QUESTION_ID: {

                        "type": "choice",

                        "probabilities": {

                            "sign_first": 0.8,

                            "calculation_first": 0.2,

                        },

                        "choice": "sign_first",

                        "value": "sign_first",

                    },

                    CHECK_QUESTION_ID: {

                        "type": "choice",

                        "probabilities": {

                            "ask_sign_relation": 0.7,

                            "ask_row_operation": 0.3,

                        },

                        "choice": "ask_sign_relation",

                        "value": "ask_sign_relation",

                    },

                },

            }
        ],

    }


# ============================================================
# REQUEST CONTRACT
# ============================================================

@pytest.mark.parametrize(
    "focus",
    [
        "sign_relation",
        "calculation",
    ],
)
def test_request_contract(focus):

    request = build_nanojev_lu_request_v01(
        focus
    )

    assert set(request) == {"states"}

    assert len(request["states"]) == 1

    state = request["states"][0]

    assert state["id"] == STATE_ID

    assert isinstance(state["state"], str)

    assert set(state["questions"]) == {
        PLAN_QUESTION_ID,
        CHECK_QUESTION_ID,
    }

    assert (
        state["questions"][PLAN_QUESTION_ID]["criteria"]
        == PLAN_CRITERIA
    )

    assert (
        state["questions"][CHECK_QUESTION_ID]["criteria"]
        == CHECK_CRITERIA
    )

    for question in state["questions"].values():

        assert question["type"] == "choice"


def test_invalid_focus_rejected():

    with pytest.raises(ValueError):

        build_nanojev_lu_request_v01(
            "execute_python"
        )


# ============================================================
# VALID RESPONSE
# ============================================================

def test_valid_nanojev_response():

    result = validate_nanojev_lu_response_v01(
        valid_response()
    )

    assert result.proposal.plan_id == "sign_first"

    assert result.proposal.check_id == "ask_sign_relation"

    assert result.proposal.origin == "untrusted_shadow_model"

    assert result.status == "developer_audit_only"

    assert not result.execution_authority

    assert not result.student_delivery_authorized

    assert dict(result.plan_probabilities) == {

        "sign_first": 0.8,

        "calculation_first": 0.2,

    }


def test_valid_json_response():

    raw = json.dumps(
        valid_response()
    )

    result = parse_nanojev_lu_response_v01(
        raw
    )

    assert result.proposal.plan_id == "sign_first"


# ============================================================
# INVALID RESPONSE
# ============================================================

def test_wrong_schema_rejected():

    response = valid_response()

    response["schema_version"] = "unknown"

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_wrong_state_rejected():

    response = valid_response()

    response["states"][0]["id"] = "other_student"

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_missing_question_rejected():

    response = valid_response()

    del response["states"][0]["answers"][
        CHECK_QUESTION_ID
    ]

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


@pytest.mark.parametrize(
    "value",
    [
        -0.2,
        1.2,
        float("nan"),
        float("inf"),
        True,
        "0.8",
    ],
)
def test_invalid_probability_rejected(value):

    response = valid_response()

    response["states"][0]["answers"][
        PLAN_QUESTION_ID
    ]["probabilities"]["sign_first"] = value

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_distribution_sum_rejected():

    response = valid_response()

    response["states"][0]["answers"][
        PLAN_QUESTION_ID
    ]["probabilities"]["sign_first"] = 0.6

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_unknown_action_rejected():

    response = valid_response()

    probabilities = response["states"][0][
        "answers"
    ][PLAN_QUESTION_ID]["probabilities"]

    probabilities["execute_python"] = 0.0

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_inconsistent_choice_rejected():

    response = valid_response()

    response["states"][0]["answers"][
        PLAN_QUESTION_ID
    ]["choice"] = "calculation_first"

    with pytest.raises(ValueError):

        validate_nanojev_lu_response_v01(
            response
        )


def test_duplicate_json_keys_rejected():

    raw = (
        '{"schema_version":"openjev-toy-inference-v1",'
        '"schema_version":"other","states":[]}'
    )

    with pytest.raises(ValueError):

        parse_nanojev_lu_response_v01(
            raw
        )


def test_nonfinite_json_constant_rejected():

    raw = json.dumps(
        valid_response()
    )

    raw = raw.replace(
        "0.8",
        "NaN",
        1,
    )

    with pytest.raises(ValueError):

        parse_nanojev_lu_response_v01(
            raw
        )


def test_response_does_not_modify_input():

    response = valid_response()

    original = deepcopy(response)

    validate_nanojev_lu_response_v01(
        response
    )

    assert response == original

"""
URPP 14C-5D-1: NanoJev Shadow Decision Adapter.

Purpose
-------
Convert a bounded URPP LU teaching decision into the
published NanoJev local Choice request format.

Validate the corresponding model response and produce
an untrusted shadow proposal.

This module does not:

- Load or execute NanoJev.
- Connect to a model server.
- Download model weights.
- Access Student State.
- Execute a teaching plan.
- Modify Mastery Evidence.
- Authorize student-facing delivery.

The current implementation is restricted to the
2x2 LU teaching pilot.
"""

from __future__ import annotations

import json
import math

from dataclasses import dataclass
from typing import Any

from app.services.course_knowledge.controlled_lu_teaching_v01 import (
    TeachingPlanV01,
    validate_shadow_proposal_v01,
)


# ============================================================
# 1. FIXED PILOT CONTRACT
# ============================================================

STATE_ID = "urpp_lu_pilot_01"

PLAN_QUESTION_ID = "teaching_plan"

CHECK_QUESTION_ID = "follow_up_check"


PLAN_CRITERIA = {
    "sign_first": (
        "Explain the sign relationship between "
        "the elimination matrix E and lower matrix L first."
    ),
    "calculation_first": (
        "Review the LU elimination calculation first."
    ),
}


CHECK_CRITERIA = {
    "ask_sign_relation": (
        "Ask the student to explain why E and L "
        "have opposite elimination multiplier signs."
    ),
    "ask_row_operation": (
        "Ask the student to independently write "
        "the row operation and calculate the second row of U."
    ),
}


# ============================================================
# 2. SHADOW DECISION RESULT
# ============================================================

@dataclass(frozen=True)
class NanoJevShadowDecisionV01:
    """
    Validated model output for developer evaluation only.

    Choice probabilities are model scores.

    They are not verified student mastery probabilities
    or empirical teaching-effectiveness measurements.
    """

    proposal: TeachingPlanV01

    plan_probabilities: tuple[
        tuple[str, float], ...
    ]

    check_probabilities: tuple[
        tuple[str, float], ...
    ]

    origin: str = "nanojev_shadow"

    status: str = "developer_audit_only"

    execution_authority: bool = False

    student_delivery_authorized: bool = False


# ============================================================
# 3. BUILD NANOJEV REQUEST
# ============================================================

def build_nanojev_lu_request_v01(
    focus_id: str,
) -> dict[str, Any]:
    """
    Build a request using NanoJev's published local
    state/question/criteria contract.

    The current state is synthetic and intentionally
    excludes personal student information.

    This is not a general Student State serializer.
    """

    if focus_id == "sign_relation":

        state_text = (
            "Synthetic LU teaching pilot. "
            "The student can calculate U but asks why "
            "the elimination matrix E and the lower "
            "triangular matrix L have opposite multiplier signs."
        )

    elif focus_id == "calculation":

        state_text = (
            "Synthetic LU teaching pilot. "
            "The student is reviewing the calculation of "
            "the elimination multiplier, row operation, "
            "and upper triangular matrix U."
        )

    else:

        raise ValueError(
            "Unsupported LU teaching focus."
        )

    return {
        "states": [
            {
                "id": STATE_ID,

                "state": state_text,

                "questions": {

                    PLAN_QUESTION_ID: {

                        "type": "choice",

                        "instructions": (
                            "Which registered teaching plan "
                            "should be proposed for this "
                            "student's current learning need?"
                        ),

                        "criteria": dict(
                            PLAN_CRITERIA
                        ),

                    },

                    CHECK_QUESTION_ID: {

                        "type": "choice",

                        "instructions": (
                            "Which registered follow-up "
                            "question should be proposed "
                            "for this learning need?"
                        ),

                        "criteria": dict(
                            CHECK_CRITERIA
                        ),

                    },

                },

            }
        ]
    }


# ============================================================
# 4. VALIDATE PROBABILITY DISTRIBUTION
# ============================================================

def _validate_choice_answer(
    answer: Any,
    allowed: dict[str, str],
) -> tuple[str, tuple[tuple[str, float], ...]]:
    """
    Validate the published NanoJev Choice answer fields.

    Reject invalid probability values, unknown actions,
    missing candidates, and inconsistent selected actions.

    A valid distribution does not establish calibration.
    """

    if not isinstance(answer, dict):

        raise ValueError(
            "Choice answer must be an object."
        )

    expected_fields = {
        "type",
        "probabilities",
        "choice",
        "value",
    }

    if set(answer) != expected_fields:

        raise ValueError(
            "Unexpected or missing Choice answer fields."
        )

    if answer["type"] != "choice":

        raise ValueError(
            "Expected a Choice answer."
        )

    probabilities = answer["probabilities"]

    if not isinstance(probabilities, dict):

        raise ValueError(
            "Choice probabilities must be an object."
        )

    if set(probabilities) != set(allowed):

        raise ValueError(
            "Choice probability candidates do not match "
            "the registered action set."
        )

    validated = {}

    for action in allowed:

        probability = probabilities[action]

        if (
            type(probability) not in (int, float)
            or not math.isfinite(probability)
            or probability < 0
            or probability > 1
        ):

            raise ValueError(
                "Invalid Choice probability."
            )

        validated[action] = float(probability)

    total = math.fsum(
        validated.values()
    )

    if abs(total - 1.0) > 1e-5:

        raise ValueError(
            "Choice probabilities do not sum to one."
        )

    selected = answer["choice"]

    if (
        type(selected) is not str
        or selected not in allowed
        or answer["value"] != selected
    ):

        raise ValueError(
            "Invalid or inconsistent Choice selection."
        )

    maximum = max(
        validated.values()
    )

    if validated[selected] != maximum:

        raise ValueError(
            "Selected action is not a maximum-probability candidate."
        )

    distribution = tuple(
        (action, validated[action])
        for action in allowed
    )

    return selected, distribution


# ============================================================
# 5. VALIDATE NANOJEV RESPONSE
# ============================================================

def validate_nanojev_lu_response_v01(
    response: Any,
) -> NanoJevShadowDecisionV01:
    """
    Validate the response to the fixed LU pilot request.

    Only one state and the two registered Choice questions
    are accepted.

    This function cannot authorize execution.
    """

    if not isinstance(response, dict):

        raise ValueError(
            "NanoJev response must be an object."
        )

    if response.get("schema_version") != (
        "openjev-toy-inference-v1"
    ):

        raise ValueError(
            "Unsupported NanoJev response schema."
        )

    states = response.get("states")

    if (
        not isinstance(states, list)
        or len(states) != 1
        or not isinstance(states[0], dict)
    ):

        raise ValueError(
            "Expected exactly one NanoJev response state."
        )

    state = states[0]

    if state.get("id") != STATE_ID:

        raise ValueError(
            "NanoJev response state ID mismatch."
        )

    answers = state.get("answers")

    if not isinstance(answers, dict):

        raise ValueError(
            "NanoJev answers must be an object."
        )

    if set(answers) != {
        PLAN_QUESTION_ID,
        CHECK_QUESTION_ID,
    }:

        raise ValueError(
            "NanoJev returned unexpected or missing questions."
        )

    plan_id, plan_distribution = _validate_choice_answer(

        answers[PLAN_QUESTION_ID],

        PLAN_CRITERIA,

    )

    check_id, check_distribution = _validate_choice_answer(

        answers[CHECK_QUESTION_ID],

        CHECK_CRITERIA,

    )

    # Reuse the existing URPP Shadow Proposal Validator.
    #
    # Do not construct an authorized teaching plan here.

    proposal = validate_shadow_proposal_v01(
        {
            "plan_id": plan_id,
            "check_id": check_id,
        }
    )

    if proposal.origin != "untrusted_shadow_model":

        raise ValueError(
            "Unexpected teaching proposal origin."
        )

    return NanoJevShadowDecisionV01(

        proposal=proposal,

        plan_probabilities=plan_distribution,

        check_probabilities=check_distribution,

    )


# ============================================================
# 6. JSON RESPONSE PARSER
# ============================================================

def parse_nanojev_lu_response_v01(
    raw: str,
) -> NanoJevShadowDecisionV01:
    """
    Parse a local NanoJev service response.

    Duplicate JSON keys and nonfinite JSON constants
    are rejected.

    No HTTP request is performed by this function.
    """

    if type(raw) is not str:

        raise ValueError(
            "NanoJev response must be a string."
        )

    if len(raw) > 100_000:

        raise ValueError(
            "NanoJev response exceeds the pilot size limit."
        )

    def unique_object(pairs):

        result = {}

        for key, value in pairs:

            if key in result:

                raise ValueError(
                    "Duplicate JSON response key."
                )

            result[key] = value

        return result

    def reject_constant(value):

        raise ValueError(
            "Nonfinite JSON constant is not allowed."
        )

    try:

        response = json.loads(

            raw,

            object_pairs_hook=unique_object,

            parse_constant=reject_constant,

        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Invalid NanoJev response JSON."
        ) from exc

    return validate_nanojev_lu_response_v01(
        response
    )

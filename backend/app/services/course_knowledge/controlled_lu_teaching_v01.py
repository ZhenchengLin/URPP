"""
URPP 14C-5C: Controlled LU Teaching Pilot.

Responsibilities:

1. Validate untrusted model-generated teaching proposals.
2. Select a deterministic teaching plan for the current pilot.
3. Render teaching content from verified Python LU results.
4. Preserve the separation between mathematical verification
   and pedagogical review.

This module does NOT:

- Call an LLM.
- Execute arbitrary Python.
- Read or modify Student State.
- Create Teaching Trace.
- Create Mastery Evidence.
- Authorize student-facing delivery.

The current scope is the existing exact-integer,
no-row-exchange 2x2 LU pilot.
"""

from __future__ import annotations

import json

from dataclasses import dataclass
from typing import Any, Literal

from app.services.course_knowledge.tool_assisted_lu_pilot_v01 import (
    LocalLUToolResultV01,
)


# ============================================================
# 1. REGISTERED TEACHING ACTIONS
# ============================================================

TeachingPlanID = Literal[
    "sign_first",
    "calculation_first",
]

TeachingCheckID = Literal[
    "ask_row_operation",
    "ask_sign_relation",
]


ALLOWED_PLANS = frozenset({
    "sign_first",
    "calculation_first",
})

ALLOWED_CHECKS = frozenset({
    "ask_row_operation",
    "ask_sign_relation",
})


# ============================================================
# 2. STRUCTURED TEACHING PLAN
# ============================================================

@dataclass(frozen=True)
class TeachingPlanV01:
    """
    A validated proposal is not an execution authorization.

    The origin field records where the plan came from.
    """

    plan_id: TeachingPlanID
    check_id: TeachingCheckID
    origin: str


# ============================================================
# 3. SHADOW PROPOSAL VALIDATION
# ============================================================

def validate_shadow_proposal_v01(
    candidate: Any,
) -> TeachingPlanV01:
    """
    Validate an untrusted model proposal.

    Fail closed on missing fields, extra fields,
    invalid identifiers, and incorrect value types.

    A successful result is valid for shadow evaluation only.
    """

    if not isinstance(candidate, dict):
        raise ValueError(
            "Teaching proposal must be a JSON object."
        )

    expected_fields = {
        "plan_id",
        "check_id",
    }

    if set(candidate) != expected_fields:
        raise ValueError(
            "Teaching proposal contains unexpected or missing fields."
        )

    plan_id = candidate["plan_id"]
    check_id = candidate["check_id"]

    if (
        type(plan_id) is not str
        or plan_id not in ALLOWED_PLANS
    ):
        raise ValueError(
            "Unregistered teaching plan."
        )

    if (
        type(check_id) is not str
        or check_id not in ALLOWED_CHECKS
    ):
        raise ValueError(
            "Unregistered teaching check."
        )

    return TeachingPlanV01(
        plan_id=plan_id,
        check_id=check_id,
        origin="untrusted_shadow_model",
    )


def parse_shadow_proposal_v01(
    raw: str,
) -> TeachingPlanV01:
    """
    Parse a model-generated JSON proposal.

    Duplicate JSON keys are rejected before validation.
    """

    if type(raw) is not str:
        raise ValueError(
            "Model response must be a string."
        )

    def reject_duplicate_keys(pairs):

        result = {}

        for key, value in pairs:

            if key in result:
                raise ValueError(
                    "Duplicate JSON field."
                )

            result[key] = value

        return result

    try:

        candidate = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Invalid model response JSON."
        ) from exc

    return validate_shadow_proposal_v01(
        candidate
    )


# ============================================================
# 4. DETERMINISTIC PILOT ROUTER
# ============================================================

def select_pilot_plan_v01(
    focus_id: str,
) -> TeachingPlanV01:
    """
    Select a registered plan from an explicit pilot focus.

    The caller must supply an authorized focus identifier.

    This function does not infer student intent from
    arbitrary natural language and does not authorize
    student-facing teaching.
    """

    if focus_id == "sign_relation":

        return TeachingPlanV01(
            plan_id="sign_first",
            check_id="ask_sign_relation",
            origin="deterministic_lu_pilot",
        )

    if focus_id == "calculation":

        return TeachingPlanV01(
            plan_id="calculation_first",
            check_id="ask_row_operation",
            origin="deterministic_lu_pilot",
        )

    raise ValueError(
        "Unsupported teaching focus."
    )


# ============================================================
# 5. CONTROLLED TEACHING RESULT
# ============================================================

@dataclass(frozen=True)
class ControlledLUTeachingCandidateV01:

    plan: TeachingPlanV01

    teaching_text: str

    follow_up_question: str

    pack_sha256: str

    status: Literal[
        "developer_audit_only"
    ] = "developer_audit_only"

    mathematical_reference_verified: bool = True

    teaching_prose_verified: bool = False

    pedagogical_review_completed: bool = False

    student_delivery_authorized: bool = False


# ============================================================
# 6. MATRIX CONSISTENCY CHECK
# ============================================================

def _multiply_2x2(left, right):

    return [
        [
            sum(
                left[i][k] * right[k][j]
                for k in range(2)
            )
            for j in range(2)
        ]
        for i in range(2)
    ]


def _validate_reference(
    tool_result: LocalLUToolResultV01,
) -> dict:
    """
    Recheck the mathematical relationships before rendering.

    These defensive checks do not replace the original
    Verification Framework.
    """

    if not isinstance(
        tool_result,
        LocalLUToolResultV01,
    ):
        raise TypeError(
            "Expected a LocalLUToolResultV01."
        )

    if tool_result.status != "developer_audit_only":
        raise ValueError(
            "Unexpected tool status."
        )

    verification = tool_result.verification

    if (
        verification.status != "passed"
        or not verification.arithmetic_accepted
    ):
        raise ValueError(
            "Mathematical reference has not passed verification."
        )

    reference = tool_result.reference_data()

    A = reference["A"]
    E = reference["E"]
    L = reference["L"]
    U = reference["U"]

    product = reference["product"]

    m = reference["multiplier"]

    (a, b), (c, d) = A

    if (
        type(m) is not int
        or a == 0
        or c != m * a
        or E != [[1, 0], [-m, 1]]
        or L != [[1, 0], [m, 1]]
        or U != [[a, b], [0, d - m * b]]
        or product != A
        or _multiply_2x2(E, A) != U
        or _multiply_2x2(L, U) != A
    ):
        raise ValueError(
            "LU reference failed renderer consistency checks."
        )

    return reference


# ============================================================
# 7. CONTROLLED TEACHING RENDERER
# ============================================================

def render_verified_lu_pilot_v01(
    *,
    tool_result: LocalLUToolResultV01,
    plan: TeachingPlanV01,
) -> ControlledLUTeachingCandidateV01:
    """
    Render a developer-only teaching candidate.

    Mathematical expressions are constructed from the
    verified Python LU result.

    Model-generated explanatory text is not accepted here.

    The teaching template itself has not been certified
    for pedagogical quality or student-facing delivery.
    """

    if not isinstance(plan, TeachingPlanV01):
        raise TypeError(
            "Expected a structured TeachingPlanV01."
        )

    if (
        plan.plan_id not in ALLOWED_PLANS
        or plan.check_id not in ALLOWED_CHECKS
    ):
        raise ValueError(
            "Teaching plan contains unregistered actions."
        )

    if plan.origin != "deterministic_lu_pilot":
        raise ValueError(
            "Shadow proposals cannot directly control rendering."
        )

    reference = _validate_reference(
        tool_result
    )

    A = reference["A"]

    E = reference["E"]

    L = reference["L"]

    U = reference["U"]

    m = reference["multiplier"]

    (a, b), (c, d) = A

    # --------------------------------------------------------
    # CALCULATION BLOCK
    # --------------------------------------------------------

    calculation_block = (

        "【LU Factorization：计算过程】\n\n"

        f"原始矩阵 A = {A}。\n\n"

        f"Elimination Multiplier：\n"
        f"m = {c} / ({a}) = {m}。\n\n"

        f"Row Operation：\n"
        f"R2 ← R2 - ({m}) × R1。\n\n"

        f"第二行第一个元素：\n"
        f"{c} - ({m}) × ({a}) = {U[1][0]}。\n\n"

        f"第二行第二个元素：\n"
        f"{d} - ({m}) × ({b}) = {U[1][1]}。\n\n"

        f"因此，U = {U}。"

    )

    # --------------------------------------------------------
    # SIGN RELATIONSHIP BLOCK
    # --------------------------------------------------------

    sign_block = (

        "【为什么 E 和 L 的符号相反？】\n\n"

        f"消元乘子 m = {m}。\n\n"

        f"Elimination Matrix：\n"
        f"E = {E}。\n\n"

        f"E 的 (2,1) 元素为 {-m}。\n"

        "左乘 E 相当于从第二行减去 "
        "m 倍第一行。\n\n"

        f"Lower Triangular Matrix：\n"
        f"L = {L}。\n\n"

        f"L 的 (2,1) 元素为 {m}。\n\n"

        "在当前二阶单位下三角矩阵中，"
        "L 是 E 的逆矩阵。\n\n"

        "可以通过 E × A = U 和 L × U = A "
        "检查这一关系。"

    )

    # --------------------------------------------------------
    # REGISTERED TEACHING ORDER
    # --------------------------------------------------------

    if plan.plan_id == "sign_first":

        teaching_text = (
            sign_block
            + "\n\n"
            + calculation_block
        )

    elif plan.plan_id == "calculation_first":

        teaching_text = (
            calculation_block
            + "\n\n"
            + sign_block
        )

    else:

        raise ValueError(
            "Unsupported teaching plan."
        )

    # --------------------------------------------------------
    # FOLLOW-UP QUESTION
    # --------------------------------------------------------

    if plan.check_id == "ask_sign_relation":

        follow_up = (

            "理解检查：请解释为什么当前例子中 "
            f"E 的 (2,1) 元素为 {-m}，"
            f"而 L 的对应元素为 {m}。"
            "两个矩阵之间有什么关系？"

        )

    elif plan.check_id == "ask_row_operation":

        follow_up = (

            "请独立写出当前矩阵的 Row Operation，"
            "并计算 U 的第二行。"

        )

    else:

        raise ValueError(
            "Unsupported teaching check."
        )

    return ControlledLUTeachingCandidateV01(

        plan=plan,

        teaching_text=teaching_text,

        follow_up_question=follow_up,

        pack_sha256=tool_result.pack_sha256,

    )

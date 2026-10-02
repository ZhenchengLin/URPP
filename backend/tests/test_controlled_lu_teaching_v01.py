"""
URPP 14C-5C: Controlled Teaching Pipeline tests.

All course data is synthetic.

No model, network, database or student-state access.
"""

from dataclasses import replace
from hashlib import sha256

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.knowledge_fetch_v01 import (
    CourseKnowledgeFetcherV01,
    CourseKnowledgeFetchRequestV01,
    InMemoryCoursePackStoreV01,
    course_pack_digest_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)

from app.services.course_knowledge.verification_framework_v01 import (
    LU2X2_CAPABILITY_V01,
)

from app.services.course_knowledge.tool_assisted_lu_pilot_v01 import (
    MIT_LU_COURSE_V01,
    MIT_LU_OBJECTIVE_V01,
    MathToolProposalV01,
    execute_lu_tool_proposal_v01,
)

from app.services.course_knowledge.controlled_lu_teaching_v01 import (
    TeachingPlanV01,
    parse_shadow_proposal_v01,
    select_pilot_plan_v01,
    render_verified_lu_pilot_v01,
)


# ============================================================
# 1. SYNTHETIC COURSE FIXTURE
# ============================================================

def make_tool_result(
    matrix=((5, 2), (15, 11)),
):

    text = (
        "Synthetic LU teaching test. "
        "This is not MIT course content."
    )

    source = CourseSourceV01(

        course_id=MIT_LU_COURSE_V01,

        source_id="synthetic-lu-source",

        source_revision="r1",

        source_locator="synthetic:lu-test#1",

        content=text,

        content_sha256=sha256(
            text.encode("utf-8")
        ).hexdigest(),

        visibility="student_visible",

        use_permission="approved_for_local_teaching",

        review_status="approved",

    )

    objective = CourseLearningObjectiveV01(

        course_id=MIT_LU_COURSE_V01,

        objective_id=MIT_LU_OBJECTIVE_V01,

        description="Synthetic LU objective",

        review_status="approved",

        source_refs=(source.reference(),),

    )

    pack = CoursePackV01(

        course_id=MIT_LU_COURSE_V01,

        pack_id="synthetic-lu-pack",

        pack_revision="r1",

        objectives=(objective,),

        sources=(source,),

    )

    request = CourseKnowledgeFetchRequestV01(

        course_id=MIT_LU_COURSE_V01,

        objective_id=MIT_LU_OBJECTIVE_V01,

        pack_id=pack.pack_id,

        pack_revision=pack.pack_revision,

        expected_pack_sha256=course_pack_digest_v01(
            pack
        ),

    )

    fetched = CourseKnowledgeFetcherV01(

        InMemoryCoursePackStoreV01(
            (pack,)
        )

    ).fetch(request)

    proposal = MathToolProposalV01(

        capability_id=LU2X2_CAPABILITY_V01,

        action="compute_lu",

        matrix_a=matrix,

    )

    return execute_lu_tool_proposal_v01(

        fetched=fetched,

        proposal=proposal,

    )


# ============================================================
# 2. VALID SHADOW PROPOSALS
# ============================================================

def test_valid_shadow_proposal():

    raw = (
        '{"plan_id":"calculation_first",'
        '"check_id":"ask_sign_relation"}'
    )

    result = parse_shadow_proposal_v01(
        raw
    )

    assert result.plan_id == "calculation_first"

    assert result.check_id == "ask_sign_relation"

    assert result.origin == "untrusted_shadow_model"


# ============================================================
# 3. INVALID SHADOW PROPOSALS
# ============================================================

@pytest.mark.parametrize(
    "raw",
    [
        "{}",

        "[]",

        "not json",

        '{"plan_id":"unknown","check_id":"ask_sign_relation"}',

        '{"plan_id":"sign_first","check_id":"unknown"}',

        '{"plan_id":"sign_first","check_id":"ask_sign_relation",'
        '"execute_python":true}',

        '{"plan_id":"sign_first","check_id":"ask_sign_relation",'
        '"plan_id":"calculation_first"}',

        '{"plan_id":true,"check_id":"ask_sign_relation"}',

        '{"plan_id":"sign_first","check_id":false}',
    ],
)

def test_invalid_shadow_proposal_rejected(raw):

    with pytest.raises(ValueError):

        parse_shadow_proposal_v01(
            raw
        )


# ============================================================
# 4. DETERMINISTIC ROUTING
# ============================================================

def test_deterministic_sign_routing():

    result = select_pilot_plan_v01(
        "sign_relation"
    )

    assert result.plan_id == "sign_first"

    assert result.check_id == "ask_sign_relation"

    assert result.origin == "deterministic_lu_pilot"


def test_deterministic_calculation_routing():

    result = select_pilot_plan_v01(
        "calculation"
    )

    assert result.plan_id == "calculation_first"

    assert result.check_id == "ask_row_operation"


def test_unknown_focus_rejected():

    with pytest.raises(ValueError):

        select_pilot_plan_v01(
            "arbitrary_action"
        )


# ============================================================
# 5. CONTROLLED TEACHING RENDERER
# ============================================================

def test_sign_first_rendering():

    tool_result = make_tool_result()

    plan = select_pilot_plan_v01(
        "sign_relation"
    )

    result = render_verified_lu_pilot_v01(

        tool_result=tool_result,

        plan=plan,

    )

    assert result.status == "developer_audit_only"

    assert result.mathematical_reference_verified

    assert not result.teaching_prose_verified

    assert not result.pedagogical_review_completed

    assert not result.student_delivery_authorized

    assert result.pack_sha256 == tool_result.pack_sha256

    assert (
        result.teaching_text.index("为什么 E 和 L")
        <
        result.teaching_text.index("LU Factorization：计算过程")
    )

    assert "11 - (3) × (2) = 5" in result.teaching_text

    assert "E 的 (2,1) 元素为 -3" in result.teaching_text

    assert "L 的 (2,1) 元素为 3" in result.teaching_text


def test_calculation_first_rendering():

    result = render_verified_lu_pilot_v01(

        tool_result=make_tool_result(),

        plan=select_pilot_plan_v01(
            "calculation"
        ),

    )

    assert (
        result.teaching_text.index("LU Factorization：计算过程")
        <
        result.teaching_text.index("为什么 E 和 L")
    )

    assert "Row Operation" in result.follow_up_question


# ============================================================
# 6. UNTRUSTED ROUTING CANNOT CONTROL RENDERER
# ============================================================

def test_shadow_proposal_cannot_directly_control_renderer():

    shadow = parse_shadow_proposal_v01(

        '{"plan_id":"calculation_first",'
        '"check_id":"ask_sign_relation"}'

    )

    with pytest.raises(
        ValueError,
        match="Shadow proposals",
    ):

        render_verified_lu_pilot_v01(

            tool_result=make_tool_result(),

            plan=shadow,

        )


# ============================================================
# 7. TAMPERED MATHEMATICAL REFERENCE
# ============================================================

def test_tampered_math_rejected():

    original = make_tool_result()

    tampered = replace(

        original,

        upper=((5, 2), (0, -5)),

    )

    with pytest.raises(
        ValueError,
        match="consistency",
    ):

        render_verified_lu_pilot_v01(

            tool_result=tampered,

            plan=select_pilot_plan_v01(
                "sign_relation"
            ),

        )


# ============================================================
# 8. NEGATIVE MULTIPLIER
# ============================================================

def test_negative_multiplier_rendering():

    result = render_verified_lu_pilot_v01(

        tool_result=make_tool_result(

            matrix=(
                (-2, 1),
                (8, 7),
            ),

        ),

        plan=select_pilot_plan_v01(
            "sign_relation"
        ),

    )

    assert "m = 8 / (-2) = -4" in result.teaching_text

    assert "E 的 (2,1) 元素为 4" in result.teaching_text

    assert "L 的 (2,1) 元素为 -4" in result.teaching_text

    assert "7 - (-4) × (1) = 11" in result.teaching_text

    assert not result.student_delivery_authorized


# ============================================================
# 9. UNREGISTERED PLAN
# ============================================================

def test_unregistered_plan_rejected():

    invalid = TeachingPlanV01(

        plan_id="execute_python",

        check_id="ask_sign_relation",

        origin="deterministic_lu_pilot",

    )

    with pytest.raises(
        ValueError,
        match="unregistered",
    ):

        render_verified_lu_pilot_v01(

            tool_result=make_tool_result(),

            plan=invalid,

        )

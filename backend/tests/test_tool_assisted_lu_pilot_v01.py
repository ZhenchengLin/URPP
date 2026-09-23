"""14C-5A: only synthetic course knowledge; no LLM, network or persistent DB."""

from dataclasses import replace
from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
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
from app.services.course_knowledge.tool_assisted_lu_pilot_v01 import (
    MIT_LU_COURSE_V01,
    MIT_LU_OBJECTIVE_V01,
    MathToolProposalV01,
    execute_lu_tool_proposal_v01,
)
from app.services.course_knowledge.verification_framework_v01 import LU2X2_CAPABILITY_V01


def fetched(*, course=MIT_LU_COURSE_V01, objective=MIT_LU_OBJECTIVE_V01,
            visibility="student_visible", permission="approved_for_local_teaching",
            review="approved"):
    text = "Synthetic 2x2 LU rule, not MIT content."
    source = CourseSourceV01(
        course_id=course, source_id="synthetic-s", source_revision="r1",
        source_locator="synthetic:example#1", content=text,
        content_sha256=sha256(text.encode()).hexdigest(),
        visibility=visibility, use_permission=permission, review_status=review,
    )
    obj = CourseLearningObjectiveV01(
        course_id=course, objective_id=objective, description="Synthetic LU objective",
        review_status="approved", source_refs=(source.reference(),),
    )
    pack = CoursePackV01(course_id=course, pack_id="synthetic-pack",
                           pack_revision="p1", objectives=(obj,), sources=(source,))
    request = CourseKnowledgeFetchRequestV01(
        course_id=course, objective_id=objective, pack_id=pack.pack_id,
        pack_revision=pack.pack_revision,
        expected_pack_sha256=course_pack_digest_v01(pack),
    )
    return CourseKnowledgeFetcherV01(InMemoryCoursePackStoreV01((pack,))).fetch(request)


def proposal(matrix=((5, 2), (15, 11)), *, capability=LU2X2_CAPABILITY_V01,
             action="compute_lu"):
    return MathToolProposalV01(capability_id=capability, action=action, matrix_a=matrix)


def test_policy_bound_tool_math_and_reference_copy():
    result = execute_lu_tool_proposal_v01(fetched=fetched(), proposal=proposal())
    assert result.status == "developer_audit_only"
    assert result.verification.arithmetic_accepted
    assert result.verification.verified_claims == ("structured_lu2x2_arithmetic",)
    assert "teaching_prose" in result.verification.unverified_claims
    assert result.reference_data() == {
        "A": [[5, 2], [15, 11]], "multiplier": 3,
        "row_operation": "R2 <- R2 - 3*R1",
        "E": [[1, 0], [-3, 1]], "L": [[1, 0], [3, 1]],
        "U": [[5, 2], [0, 5]], "product": [[5, 2], [15, 11]],
        "source_locator": "synthetic:example#1", "provenance": "new_practice",
    }
    modified = result.reference_data()
    modified["U"][1][1] = -1
    assert result.reference_data()["U"][1][1] == 5


def test_original_example_and_negative_multiplier():
    for matrix, m, u22 in (
        (((2, 1), (8, 7)), 4, 3),
        (((-2, 1), (8, 7)), -4, 11),
    ):
        result = execute_lu_tool_proposal_v01(fetched=fetched(), proposal=proposal(matrix))
        assert result.multiplier == m
        assert result.upper[1][1] == u22
        assert result.verification.arithmetic_accepted


@pytest.mark.parametrize("change", [
    {"capability": "python.eval"},
    {"capability": "math.lu3x3"},
    {"action": "execute_python"},
    {"action": "assess_mastery"},
])
def test_untrusted_router_cannot_select_unapproved_action(change):
    with pytest.raises(ValueError, match="not allowed"):
        execute_lu_tool_proposal_v01(fetched=fetched(), proposal=proposal(**change))


@pytest.mark.parametrize("matrix", [
    [[0, 1], [8, 7]], [[3, 1], [8, 7]],
    [[True, 1], [8, 7]], [[2.0, 1], [8, 7]],
    [[2, 1, 3], [8, 7]], [[2, 1], [8, 7], [1, 2]],
    [[1_000_001, 1], [8, 7]], "not a matrix",
])
def test_invalid_or_out_of_scope_matrix_fails_closed(matrix):
    with pytest.raises(ValueError):
        execute_lu_tool_proposal_v01(fetched=fetched(), proposal=proposal(matrix))


@pytest.mark.parametrize("change", [
    {"course": "another-course"},
    {"objective": "another-objective"},
])
def test_unapproved_course_or_objective_cannot_invoke_tool(change):
    with pytest.raises(ValueError, match="course/objective"):
        execute_lu_tool_proposal_v01(fetched=fetched(**change), proposal=proposal())


@pytest.mark.parametrize("change", [
    {"visibility": "restricted"},
    {"permission": "not_authorized"},
    {"review": "revoked"},
])
def test_fetcher_blocks_unavailable_source_before_execution(change):
    with pytest.raises(ValidationError):
        fetched(**change)


def test_invalid_proposal_type_rejected():
    with pytest.raises(TypeError):
        execute_lu_tool_proposal_v01(fetched=fetched(), proposal={"action": "compute_lu"})


def test_invalid_fetch_type_rejected():
    with pytest.raises(TypeError):
        execute_lu_tool_proposal_v01(fetched={}, proposal=proposal())


def test_bypassed_source_validation_detected_before_tool_execution():
    original = fetched()
    tampered = original.knowledge.sources[0].model_copy(update={"content": "TAMPERED"})
    altered_knowledge = original.knowledge.model_copy(update={"sources": (tampered,)})
    modified = replace(original, knowledge=altered_knowledge)
    with pytest.raises(ValidationError, match="digest mismatch"):
        execute_lu_tool_proposal_v01(fetched=modified, proposal=proposal())

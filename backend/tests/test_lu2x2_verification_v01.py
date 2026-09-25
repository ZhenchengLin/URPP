"""Independent negative/positive cases: no AI model, network or persistence."""

from copy import deepcopy

import pytest

from app.services.course_knowledge.lu2x2_verification_v01 import (
    verify_lu2x2_candidate_v01,
)

LOCATOR = "test-source:session-1.4#page=1"


def good(a, m, u22, provenance="lecture_example"):
    return {
        "multiplier": m,
        "row_operation": f"R2 <- R2 - {m}*R1",
        "E": [[1, 0], [-m, 1]],
        "L": [[1, 0], [m, 1]],
        "U": [[a[0][0], a[0][1]], [0, u22]],
        "product": deepcopy(a),
        "explanation_zh": "This prose is deliberately NOT verified by this function.",
        "source_locator": LOCATOR,
        "provenance": provenance,
    }


def verify(a, answer, provenance="lecture_example"):
    return verify_lu2x2_candidate_v01(
        matrix_a=a, candidate=answer,
        expected_source_locator=LOCATOR,
        expected_provenance=provenance,
    )


def test_two_independent_reference_cases_pass_as_arithmetic_only():
    for a, m, u22, provenance in (
        ([[2, 1], [8, 7]], 4, 3, "lecture_example"),
        ([[5, 2], [15, 11]], 3, 5, "new_practice"),
    ):
        result = verify(a, good(a, m, u22, provenance), provenance)
        assert result.accepted_arithmetic and not result.errors
        assert result.teaching_prose_reviewed is False


def test_bug_regression_correct_E_does_not_excuse_wrong_claimed_U():
    a = [[5, 2], [15, 11]]
    answer = good(a, 3, 5)
    answer["U"] = [[5, 2], [0, -1]]
    result = verify(a, answer)
    assert not result.accepted_arithmetic
    assert "candidate E*A does not equal candidate U" in result.errors
    assert "candidate L*U does not equal original A" in result.errors


@pytest.mark.parametrize("field,bad_value", [
    ("multiplier", -3),
    ("multiplier", True),
    ("row_operation", "R2 <- R2 + 3*R1"),
    ("E", [[1, 0], [3, 1]]),
    ("L", [[1, 0], [-3, 1]]),
    ("U", [[5, 2], [0, -1]]),
    ("product", [[5, 2], [0, -1]]),
    ("source_locator", "a-made-up-source"),
    ("provenance", "lecture_example"),
])
def test_bad_fields_fail_closed(field, bad_value):
    a = [[5, 2], [15, 11]]
    candidate = good(a, 3, 5, "new_practice")
    candidate[field] = bad_value
    assert not verify(a, candidate, "new_practice").accepted_arithmetic


def test_explicitly_does_not_certify_incorrect_prose():
    a = [[2, 1], [8, 7]]
    candidate = good(a, 4, 3)
    candidate["explanation_zh"] = "Wrong: R2 + 4*R1 eliminates 8."
    result = verify(a, candidate)
    assert result.accepted_arithmetic
    assert result.teaching_prose_reviewed is False


@pytest.mark.parametrize("matrix", [
    [[0, 1], [8, 7]], [[3, 1], [8, 7]],
    [[True, 1], [8, 7]], [[2, 1, 5], [8, 7]],
])
def test_out_of_scope_matrices_rejected(matrix):
    with pytest.raises(ValueError):
        verify(matrix, {})


def test_non_mapping_rejected():
    with pytest.raises(TypeError):
        verify_lu2x2_candidate_v01(
            matrix_a=[[2, 1], [8, 7]], candidate="not-a-mapping",
            expected_source_locator=LOCATOR, expected_provenance="lecture_example",
        )

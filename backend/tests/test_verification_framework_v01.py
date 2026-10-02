"""14C-2: explicit dispatch; arithmetic-only claims; fail-closed outcomes."""

from dataclasses import replace

import pytest

from app.services.course_knowledge.verification_framework_v01 import (
    LU2X2_CAPABILITY_V01,
    LU2x2VerificationAdapterV01,
    VerificationRegistryV01,
    VerificationRequestV01,
    VerificationResultV01,
    local_math_registry_v01,
)

LOCATOR = "test-source:lu#page=1"


def request(a=None, candidate=None, *, kind=LU2X2_CAPABILITY_V01):
    matrix = a if a is not None else [[5, 2], [15, 11]]
    answer = candidate if candidate is not None else {
        "multiplier": 3,
        "row_operation": "R2 <- R2 - 3*R1",
        "E": [[1, 0], [-3, 1]],
        "L": [[1, 0], [3, 1]],
        "U": [[5, 2], [0, 5]],
        "product": [[5, 2], [15, 11]],
        "explanation_zh": "这是不受验证的自然语言解释。",
        "source_locator": LOCATOR,
        "provenance": "new_practice",
    }
    return VerificationRequestV01(
        capability_id=kind,
        inputs={"matrix_a": matrix},
        candidate=answer,
        context={"expected_source_locator": LOCATOR,
                 "expected_provenance": "new_practice"},
    )


def test_new_practice_passes_only_structured_arithmetic():
    result = local_math_registry_v01().verify(request())
    assert result.status == "passed"
    assert result.arithmetic_accepted
    assert result.verified_claims == ("structured_lu2x2_arithmetic",)
    assert "teaching_prose" in result.unverified_claims
    assert "source_authenticity_and_permissions" in result.unverified_claims
    assert "student_mastery_and_assessment" in result.unverified_claims
    assert not result.errors


def test_explicit_source_echo_does_not_claim_source_authenticity():
    result = local_math_registry_v01().verify(request())
    assert "source_authenticity_and_permissions" not in result.verified_claims


def test_wrong_prose_still_not_certified_when_math_is_correct():
    r = request()
    wrong = dict(r.candidate, explanation_zh="R2 + 3R1 消掉 15，错误说法。")
    result = local_math_registry_v01().verify(replace(r, candidate=wrong))
    assert result.status == "passed"
    assert "teaching_prose" in result.unverified_claims


@pytest.mark.parametrize("field,bad", [
    ("multiplier", -3),
    ("row_operation", "R2 <- R2 + 3*R1"),
    ("E", [[1, 0], [3, 1]]),
    ("U", [[5, 2], [0, -1]]),
    ("product", [[5, 2], [0, -1]]),
    ("source_locator", "a-fake-source"),
])
def test_bad_candidate_never_passes(field, bad):
    r = request()
    result = local_math_registry_v01().verify(replace(r, candidate=dict(r.candidate, **{field: bad})))
    assert result.status == "failed"
    assert not result.arithmetic_accepted
    assert not result.verified_claims
    assert result.errors


def test_unregistered_capability_is_unsupported_and_does_not_fallback():
    result = local_math_registry_v01().verify(request(kind="math.eigenvalue.v01"))
    assert result.status == "unsupported"
    assert result.verified_claims == ()
    assert not result.arithmetic_accepted


@pytest.mark.parametrize("wrong", [
    VerificationRequestV01(LU2X2_CAPABILITY_V01, {}, {}, {}),
    replace(request(), inputs={"matrix_a": [[0, 2], [15, 11]]}),
    replace(request(), context={"expected_source_locator": LOCATOR}),
    replace(request(), context={"expected_source_locator": "", "expected_provenance": "new_practice"}),
    replace(request(), candidate="not a mapping"),
])
def test_invalid_requests_fail_closed(wrong):
    result = local_math_registry_v01().verify(wrong)
    assert result.status == "failed"
    assert not result.arithmetic_accepted
    assert not result.verified_claims


def test_missing_plugin_and_duplicate_id():
    result = VerificationRegistryV01(()).verify(request())
    assert result.status == "unsupported"
    with pytest.raises(ValueError, match="duplicate"):
        VerificationRegistryV01((LU2x2VerificationAdapterV01(), LU2x2VerificationAdapterV01()))


def test_wrong_capability_direct_invocation_fails():
    with pytest.raises(ValueError, match="mismatch"):
        LU2x2VerificationAdapterV01().verify(request(kind="math.unknown.v01"))


class MalformedVerifier:
    capability_id = "test.malformed.v01"

    def __init__(self, result):
        self.result = result

    def verify(self, request):
        return self.result


@pytest.mark.parametrize("result", [
    "passed",
    VerificationResultV01("wrong.id", "passed", ("math",), (), ()),
    VerificationResultV01("test.malformed.v01", "failed", ("math",), (), ("invalid",)),
    VerificationResultV01("test.malformed.v01", "passed", (), (), ()),
    VerificationResultV01("test.malformed.v01", "passed", ("math",), (), ("contradiction",)),
])
def test_registry_rejects_invalid_plugin_results(result):
    registry = VerificationRegistryV01((MalformedVerifier(result),))
    with pytest.raises(RuntimeError):
        registry.verify(request(kind="test.malformed.v01"))


def test_unexpected_plugin_exception_is_not_disguised_as_success():
    class BuggyVerifier:
        capability_id = "test.buggy.v01"

        def verify(self, _request):
            raise RuntimeError("unexpected verifier crash")

    registry = VerificationRegistryV01((BuggyVerifier(),))
    with pytest.raises(RuntimeError, match="unexpected verifier crash"):
        registry.verify(request(kind="test.buggy.v01"))

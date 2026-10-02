from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.services.course_knowledge.models_v01 import (
    CourseSourceRefV01,
)

from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    BenchmarkConversationTurnV01,
    BenchmarkEquationGoldV01,
    BenchmarkEvidenceExpectationV01,
    BenchmarkExecutionTraceV01,
    BenchmarkGoldV01,
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
    canonical_benchmark_case_bytes_v01,
    validate_benchmark_execution_trace_v01,
    validate_source_grounded_benchmark_case_v01,
)


SHA_A = "a" * 64
SHA_B = "b" * 64


def source_ref(
    source_id: str = "pdf-6",
    *,
    revision: str = "paper-rev-1",
    locator: str = "local-pdf://paper.pdf?pages=6-6",
    digest: str = SHA_A,
):
    return CourseSourceRefV01(
        source_id=source_id,
        source_revision=revision,
        source_locator=locator,
        content_sha256=digest,
    )


def evidence(
    ref=None,
    *,
    locator="PDF page 6, Equation (15)",
    kind="equation",
    rationale="Supports the requested source-grounded content.",
):
    return BenchmarkEvidenceExpectationV01(
        source_ref=ref or source_ref(),
        evidence_locator=locator,
        evidence_kind=kind,
        rationale=rationale,
    )


def equation_gold():
    return BenchmarkEquationGoldV01(
        equation_label="15",
        normalized_latex=(
            r"\mathrm{height}="
            r"\begin{cases}"
            r"\dfrac{\Delta_z}{2}-D_{\mathrm{pl}},"
            r"&0\leq D_{\mathrm{pl}}\leq\dfrac{\Delta_z}{2},\\"
            r"0,&\mathrm{otherwise}."
            r"\end{cases}"
        ),
    )


def positive_case():
    ref = source_ref()

    return SourceGroundedBenchmarkCaseV01(
        case_id="ltri-eq15-copy-001",
        benchmark_version="ct-dev-v0.1",
        split="development",
        language="zh",
        question_type="equation_transcription",
        question="请写出式 (15) 的完整公式。",
        source_scope_refs=(ref,),
        required_evidence=(
            evidence(ref),
        ),
        gold=BenchmarkGoldV01(
            required_facts=(
                "Equation (15) is the Regression Method approximation.",
            ),
            equations=(
                equation_gold(),
            ),
            prohibited_errors=(
                "Do not move D_pl into a denominator.",
            ),
            acceptable_variants=(
                "D_pl and D_{pl} are equivalent notation.",
            ),
        ),
        expected_outcome="answer",
        evaluation_categories=(
            "source_selection",
            "formula_structure",
            "formula_transcription",
            "math_rendering",
        ),
    )


def test_positive_case_is_valid_and_frozen():
    case = positive_case()

    assert case.expected_outcome == "answer"

    with pytest.raises(
        ValidationError,
    ):
        case.question = "changed"


def test_case_gold_does_not_require_candidate_architecture():
    case = positive_case()

    payload = case.model_dump(
        mode="python"
    )

    assert "expected_trace" not in payload

    equation_payload = (
        case.gold.equations[0]
        .model_dump(mode="python")
    )

    assert set(
        equation_payload
    ) == {
        "equation_label",
        "normalized_latex",
    }


def test_extra_fields_are_forbidden():
    data = positive_case().model_dump(
        mode="python"
    )

    data["expected_verified_record_ids"] = (
        "record-15",
    )

    with pytest.raises(
        ValidationError,
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_canonical_case_digest_is_deterministic():
    case = positive_case()

    first = benchmark_case_digest_v01(
        case
    )

    encoded = (
        canonical_benchmark_case_bytes_v01(
            case
        )
    )

    restored = (
        SourceGroundedBenchmarkCaseV01
        .model_validate_json(
            encoded
        )
    )

    second = benchmark_case_digest_v01(
        restored
    )

    assert first == second
    assert len(first) == 64


def test_case_digest_changes_when_question_changes():
    case = positive_case()

    changed = case.model_copy(
        update={
            "question": (
                "Write Equation (15)."
            )
        }
    )

    assert (
        benchmark_case_digest_v01(
            case
        )
        !=
        benchmark_case_digest_v01(
            changed
        )
    )


def test_case_digest_changes_when_gold_changes():
    case = positive_case()

    changed_gold = case.gold.model_copy(
        update={
            "required_facts": (
                "Different frozen fact.",
            )
        }
    )

    changed = case.model_copy(
        update={
            "gold": changed_gold,
        }
    )

    assert (
        benchmark_case_digest_v01(
            case
        )
        !=
        benchmark_case_digest_v01(
            changed
        )
    )


def test_digest_revalidates_model_copy_tampering():
    case = positive_case()

    tampered = case.model_copy(
        update={
            "question": " ",
        }
    )

    with pytest.raises(
        ValidationError,
    ):
        benchmark_case_digest_v01(
            tampered
        )


def test_blank_question_rejected():
    data = positive_case().model_dump(
        mode="python"
    )

    data["question"] = " "

    with pytest.raises(
        ValidationError,
        match="Benchmark question",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_duplicate_source_scope_ids_rejected():
    data = positive_case().model_dump(
        mode="python"
    )

    ref = source_ref()

    data["source_scope_refs"] = (
        ref,
        ref,
    )

    with pytest.raises(
        ValidationError,
        match="Source scope IDs",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_required_evidence_must_be_inside_scope():
    data = positive_case().model_dump(
        mode="python"
    )

    other = source_ref(
        "pdf-5",
        locator="local-pdf://paper.pdf?pages=5-5",
        digest=SHA_B,
    )

    data["required_evidence"] = (
        evidence(
            other,
            locator="PDF page 5",
            kind="definition",
        ),
    )

    with pytest.raises(
        ValidationError,
        match="outside case scope",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_required_evidence_revision_must_match_scope():
    data = positive_case().model_dump(
        mode="python"
    )

    data["required_evidence"] = (
        evidence(
            source_ref(
                revision="different-revision",
            )
        ),
    )

    with pytest.raises(
        ValidationError,
        match="revision does not match",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_duplicate_evidence_expectation_rejected():
    data = positive_case().model_dump(
        mode="python"
    )

    item = evidence()

    data["required_evidence"] = (
        item,
        item,
    )

    with pytest.raises(
        ValidationError,
        match="duplicate evidence",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_answered_case_requires_evidence():
    data = positive_case().model_dump(
        mode="python"
    )

    data["required_evidence"] = ()

    with pytest.raises(
        ValidationError,
        match="requires required evidence",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_answered_case_requires_gold():
    ref = source_ref()

    with pytest.raises(
        ValidationError,
        match="requires independently frozen gold",
    ):
        SourceGroundedBenchmarkCaseV01(
            case_id="fact-no-gold",
            benchmark_version="v0.1",
            split="development",
            language="en",
            question_type="direct_fact",
            question="What method is used?",
            source_scope_refs=(ref,),
            required_evidence=(
                evidence(
                    ref,
                    kind="method",
                ),
            ),
            gold=BenchmarkGoldV01(),
            expected_outcome="answer",
            evaluation_categories=(
                "method_attribution",
            ),
        )


def unsupported_case():
    ref = source_ref()

    return SourceGroundedBenchmarkCaseV01(
        case_id="unsupported-eq99",
        benchmark_version="v0.1",
        split="holdout",
        language="en",
        question_type="unsupported",
        question="Write Equation (99).",
        source_scope_refs=(ref,),
        required_evidence=(),
        gold=BenchmarkGoldV01(
            prohibited_errors=(
                "Do not fabricate Equation (99).",
            ),
            reference_answer=(
                "The authorized source does not provide Equation (99)."
            ),
        ),
        expected_outcome="abstain",
        evaluation_categories=(
            "insufficient_evidence_handling",
            "unsupported_claim",
        ),
    )


def test_unsupported_case_can_expect_abstention():
    case = unsupported_case()

    assert case.expected_outcome == "abstain"


def test_unsupported_case_cannot_expect_answer():
    data = unsupported_case().model_dump(
        mode="python"
    )

    data["expected_outcome"] = "answer"

    with pytest.raises(
        ValidationError,
        match="must expect abstention",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_abstention_case_cannot_require_positive_fact():
    data = unsupported_case().model_dump(
        mode="python"
    )

    data["gold"] = BenchmarkGoldV01(
        required_facts=(
            "A positive factual answer.",
        ),
    )

    with pytest.raises(
        ValidationError,
        match="cannot require positive facts",
    ):
        SourceGroundedBenchmarkCaseV01(
            **data
        )


def test_duplicate_gold_facts_rejected():
    with pytest.raises(
        ValidationError,
        match="contains duplicates",
    ):
        BenchmarkGoldV01(
            required_facts=(
                "same",
                "same",
            ),
        )


def test_duplicate_equation_labels_rejected():
    eq = equation_gold()

    with pytest.raises(
        ValidationError,
        match="equation labels",
    ):
        BenchmarkGoldV01(
            equations=(
                eq,
                eq,
            ),
        )


@pytest.mark.parametrize(
    "bad_latex",
    [
        "$$x+y$$",
        r"\[x+y\]",
        "```math\nx+y\n```",
        "x\t+y",
        " x+y",
        "x+y ",
    ],
)
def test_equation_gold_rejects_non_normalized_latex(
    bad_latex,
):
    with pytest.raises(
        ValidationError,
    ):
        BenchmarkEquationGoldV01(
            equation_label="15",
            normalized_latex=bad_latex,
        )


def test_follow_up_case_can_freeze_prior_conversation():
    ref = source_ref()

    case = SourceGroundedBenchmarkCaseV01(
        case_id="follow-up-second-equation",
        benchmark_version="v0.1",
        split="holdout",
        language="zh",
        question_type="follow_up",
        question="把第二个完整写出来。",
        prior_turns=(
            BenchmarkConversationTurnV01(
                role="student",
                text=(
                    "式 (15) 和 (16) "
                    "分别是什么方法？"
                ),
            ),
            BenchmarkConversationTurnV01(
                role="professor",
                text=(
                    "前者是 Regression Method，"
                    "后者是 Distance Method。"
                ),
            ),
        ),
        source_scope_refs=(ref,),
        required_evidence=(
            evidence(ref),
        ),
        gold=BenchmarkGoldV01(
            equations=(
                BenchmarkEquationGoldV01(
                    equation_label="16",
                    normalized_latex=(
                        r"h_{\mathrm{eff}}="
                        r"\begin{cases}"
                        r"\min(z^+,t_c^+)-"
                        r"\max(z^-,t_c^-),"
                        r"&\mathrm{if\ overlap},\\"
                        r"0,&\mathrm{otherwise}."
                        r"\end{cases}"
                    ),
                ),
            ),
        ),
        expected_outcome="answer",
        evaluation_categories=(
            "conversation_context",
            "formula_transcription",
        ),
    )

    assert len(
        case.prior_turns
    ) == 2


def valid_trace(
    **updates,
):
    case = positive_case()

    data = dict(
        trace_version="v0.1",
        run_id="run-001",
        case_id=case.case_id,
        case_sha256=(
            benchmark_case_digest_v01(
                case
            )
        ),
        candidate_system="urpp-current-chain",
        candidate_version=(
            "2035348caf14a6c291b88ff93816f5fe1be54f55"
        ),
        run_started_at=datetime(
            2026,
            9,
            25,
            5,
            0,
            tzinfo=timezone.utc,
        ),
        selected_source_refs=(
            source_ref(),
        ),
        extracted_equation_labels=(
            "15",
        ),
        verified_record_ids=(),
        model_called=True,
        model_id="qwen3.5:4b",
        contract_valid=True,
        session_write_performed=False,
        system_answer_status="course_grounded",
        final_status="answered",
        raw_model_output=(
            '{"content":"answer"}'
        ),
        final_answer=(
            "A source-grounded answer."
        ),
        error_code=None,
    )

    data.update(
        updates
    )

    return BenchmarkExecutionTraceV01(
        **data
    )


def test_execution_trace_binds_exact_case_digest():
    trace = valid_trace()
    case = positive_case()

    assert trace.case_id == case.case_id

    assert (
        trace.case_sha256
        ==
        benchmark_case_digest_v01(
            case
        )
    )


def test_same_case_supports_different_candidate_architectures():
    case = positive_case()
    digest = benchmark_case_digest_v01(
        case
    )

    current = valid_trace(
        candidate_system="urpp-current-chain",
        verified_record_ids=(),
    )

    verified = valid_trace(
        candidate_system="urpp-verified-equation-chain",
        verified_record_ids=(
            "real-ltri-equation-15",
        ),
        model_called=False,
        model_id=None,
        raw_model_output=None,
        final_answer=(
            "**Equation (15)** exact deterministic rendering"
        ),
    )

    assert current.case_sha256 == digest
    assert verified.case_sha256 == digest

    assert (
        current.verified_record_ids
        !=
        verified.verified_record_ids
    )


def test_execution_trace_is_frozen():
    trace = valid_trace()

    with pytest.raises(
        ValidationError,
    ):
        trace.final_answer = "changed"


def test_trace_case_sha_must_be_exact_sha256():
    with pytest.raises(
        ValidationError,
    ):
        valid_trace(
            case_sha256="abc",
        )


def test_trace_time_must_be_timezone_aware():
    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        valid_trace(
            run_started_at=datetime(
                2026,
                9,
                25,
                5,
                0,
            )
        )


def test_trace_rejects_duplicate_selected_source_ids():
    ref = source_ref()

    with pytest.raises(
        ValidationError,
        match="Selected source IDs",
    ):
        valid_trace(
            selected_source_refs=(
                ref,
                ref,
            )
        )


def test_model_call_requires_model_id():
    with pytest.raises(
        ValidationError,
        match="requires model_id",
    ):
        valid_trace(
            model_id=None,
        )


def test_no_model_call_cannot_claim_model_output():
    with pytest.raises(
        ValidationError,
        match="cannot contain raw model output",
    ):
        valid_trace(
            model_called=False,
            model_id=None,
            raw_model_output=(
                "impossible output"
            ),
        )


def test_answered_trace_requires_final_answer():
    with pytest.raises(
        ValidationError,
        match="requires final_answer",
    ):
        valid_trace(
            final_answer=None,
        )


def test_error_trace_requires_error_code():
    with pytest.raises(
        ValidationError,
        match="requires error_code",
    ):
        valid_trace(
            final_status="error",
            final_answer=None,
            error_code=None,
        )


def test_abstained_trace_may_return_explanation_without_error():
    trace = valid_trace(
        final_status="abstained",
        final_answer=(
            "The authorized material "
            "does not support this answer."
        ),
        error_code=None,
    )

    assert trace.final_status == "abstained"


def test_trace_validator_revalidates_model_copy_tampering():
    trace = valid_trace()

    tampered = trace.model_copy(
        update={
            "final_answer": None,
        }
    )

    with pytest.raises(
        ValidationError,
    ):
        validate_benchmark_execution_trace_v01(
            tampered
        )


def test_case_validator_requires_correct_type():
    with pytest.raises(
        TypeError,
        match="Expected SourceGroundedBenchmarkCaseV01",
    ):
        validate_source_grounded_benchmark_case_v01(
            "not-a-case"
        )


def test_trace_validator_requires_correct_type():
    with pytest.raises(
        TypeError,
        match="Expected BenchmarkExecutionTraceV01",
    ):
        validate_benchmark_execution_trace_v01(
            "not-a-trace"
        )

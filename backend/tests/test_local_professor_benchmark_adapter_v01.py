from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

from hashlib import sha256
import json

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.local_professor_benchmark_adapter_v01 import (
    CANDIDATE_SYSTEM_V01,
    run_local_professor_benchmark_case_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)

from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    BenchmarkEvidenceExpectationV01,
    BenchmarkGoldV01,
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
)


RUN_AT = datetime(
    2026,
    9,
    25,
    7,
    0,
    tzinfo=timezone.utc,
)

CANDIDATE_VERSION = (
    "9ab7eff64bd3d3b926b89b34c867d5b0977a6bf8"
)


def course_source(
    source_id: str,
    *,
    page: int,
    content: str,
):
    return CourseSourceV01(
        course_id="course-1",
        source_id=source_id,
        source_revision="paper-revision-1",
        source_locator=(
            "local-pdf://paper.pdf"
            "?sha256="
            + ("f" * 64)
            + f"&pages={page}-{page}"
            + f"&excerpt={page}"
        ),
        content=content,
        content_sha256=sha256(
            content.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission=(
            "approved_for_local_teaching"
        ),
        review_status="approved",
    )


def pack():
    page5 = course_source(
        "pdf-5",
        page=5,
        content=(
            "Height Look-Up Table. "
            "D_pl is a signed perpendicular "
            "distance associated with the plane. "
            "Equation (12) defines the "
            "voxel-specific distance."
        ),
    )

    page6 = course_source(
        "pdf-6",
        page=6,
        content=(
            "C. Height Approximation Methods\n"
            "1) Regression Method\n"
            "height is approximated by a "
            "piece-wise regression function.\n"
            "height = Delta_z/2 - D_pl "
            "for the supported interval; "
            "otherwise zero. (15)\n"
            "2) Distance Method\n"
            "overlapped distance gives h_eff. (16)"
        ),
    )

    objective = (
        CourseLearningObjectiveV01(
            course_id="course-1",
            objective_id="objective-1",
            description=(
                "Learn the height approximation "
                "methods in the supplied paper."
            ),
            review_status="approved",
            source_refs=(
                page5.reference(),
                page6.reference(),
            ),
        )
    )

    return CoursePackV01(
        course_id="course-1",
        pack_id="pack-1",
        pack_revision="paper-revision-1",
        objectives=(objective,),
        sources=(
            page5,
            page6,
        ),
    )


def positive_case(
    *,
    secret_gold: str | None = None,
):
    material = pack()

    page5, page6 = (
        material.sources
    )

    required_fact = (
        secret_gold
        or (
            "Equation (15) belongs to "
            "Regression Method."
        )
    )

    return SourceGroundedBenchmarkCaseV01(
        case_id="eq15-current-chain",
        benchmark_version="v0.1",
        split="development",
        language="zh",
        question_type=(
            "equation_transcription"
        ),
        question=(
            "请写出式 (15) 的完整公式。"
        ),
        source_scope_refs=(
            page5.reference(),
            page6.reference(),
        ),
        required_evidence=(
            BenchmarkEvidenceExpectationV01(
                source_ref=(
                    page6.reference()
                ),
                evidence_locator=(
                    "PDF page 6, Equation (15)"
                ),
                evidence_kind="equation",
                rationale=(
                    secret_gold
                    or (
                        "This region independently "
                        "supports Equation (15)."
                    )
                ),
            ),
        ),
        gold=BenchmarkGoldV01(
            required_facts=(
                required_fact,
            ),
            prohibited_errors=(
                secret_gold
                or (
                    "Do not invent another "
                    "method name."
                ),
            ),
        ),
        expected_outcome="answer",
        evaluation_categories=(
            "source_selection",
            "formula_transcription",
        ),
        notes=(
            secret_gold
            or "Private evaluation metadata."
        ),
    )


def success_response(
    *,
    content=(
        "式 (15) 是 Regression Method "
        "中的高度近似公式。"
    ),
    source_ids=None,
    answer_status="course_grounded",
):
    if source_ids is None:
        source_ids = [
            "pdf-6",
        ]

    raw = json.dumps(
        {
            "content": content,
            "source_ids": source_ids,
            "answer_status": answer_status,
        },
        ensure_ascii=False,
    )

    return {
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": raw,
        },
    }


def test_real_current_chain_returns_structured_trace():
    case = positive_case()

    observed_requests = []

    def transport(request):
        observed_requests.append(
            request
        )

        return success_response()

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-001",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.case_id == case.case_id

    assert (
        trace.case_sha256
        ==
        benchmark_case_digest_v01(
            case
        )
    )

    assert (
        trace.candidate_system
        == CANDIDATE_SYSTEM_V01
    )

    assert trace.model_called is True
    assert trace.model_id == "qwen3.5:4b"
    assert trace.contract_valid is True

    assert (
        trace.session_write_performed
        is False
    )

    assert (
        trace.system_answer_status
        == "course_grounded"
    )

    assert trace.final_status == "answered"

    assert (
        trace.final_answer
        ==
        "式 (15) 是 Regression Method "
        "中的高度近似公式。"
    )

    assert len(
        trace.selected_source_refs
    ) == 1

    assert (
        trace.selected_source_refs[0]
        .source_id
        == "pdf-6"
    )

    assert (
        trace.selected_source_refs[0]
        == pack().sources[1].reference()
    )

    assert trace.extracted_equation_labels == ()
    assert trace.verified_record_ids == ()

    assert len(observed_requests) == 1

    raw_expected = (
        success_response()[
            "message"
        ][
            "content"
        ]
    )

    assert (
        trace.raw_model_output
        == raw_expected
    )


def test_benchmark_gold_is_not_leaked_into_model_request():
    secret = (
        "SECRET_GOLD_DO_NOT_LEAK_9F31"
    )

    case = positive_case(
        secret_gold=secret,
    )

    request_texts = []

    def transport(request):
        encoded = json.dumps(
            request,
            ensure_ascii=False,
        )

        request_texts.append(
            encoded
        )

        assert secret not in encoded

        return success_response()

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-gold-boundary",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.final_status == "answered"

    assert len(request_texts) == 1

    assert secret not in request_texts[0]


def test_case_source_scope_must_match_candidate_scope():
    material = pack()

    full = positive_case()

    mismatched = (
        full.model_copy(
            update={
                "source_scope_refs": (
                    material.sources[1]
                    .reference(),
                )
            }
        )
    )

    calls = []

    def transport(request):
        calls.append(request)
        return success_response()

    with pytest.raises(
        ValueError,
        match=(
            "source scope must exactly match"
        ),
    ):
        run_local_professor_benchmark_case_v01(
            case=mismatched,
            pack=material,
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-bad-scope",
            run_started_at=RUN_AT,
            transport=transport,
        )

    assert calls == []


def test_unknown_chinese_topic_abstains_without_model_call():
    material = pack()

    case = SourceGroundedBenchmarkCaseV01(
        case_id="unsupported-topic",
        benchmark_version="v0.1",
        split="development",
        language="zh",
        question_type="unsupported",
        question=(
            "请解释量子色动力学中的渐近自由。"
        ),
        source_scope_refs=tuple(
            source.reference()
            for source in material.sources
        ),
        required_evidence=(),
        gold=BenchmarkGoldV01(
            prohibited_errors=(
                "Do not invent support from "
                "the CT paper.",
            ),
            reference_answer=(
                "The supplied material does not "
                "establish an answer."
            ),
        ),
        expected_outcome="abstain",
        evaluation_categories=(
            "insufficient_evidence_handling",
            "unsupported_claim",
        ),
    )

    def transport(_request):
        raise AssertionError(
            "Ollama must not be called "
            "for an empty source selection."
        )

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=material,
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-abstain",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.model_called is False
    assert trace.model_id is None

    assert trace.selected_source_refs == ()
    assert trace.raw_model_output is None

    assert trace.contract_valid is True

    assert (
        trace.system_answer_status
        == "insufficient_evidence"
    )

    assert trace.final_status == "abstained"

    assert trace.final_answer is not None

    assert (
        trace.session_write_performed
        is False
    )


def test_invalid_model_citation_becomes_error_trace():
    case = positive_case()

    raw = success_response(
        source_ids=[
            "pdf-999",
        ],
    )

    def transport(_request):
        return raw

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-bad-citation",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.model_called is True

    assert (
        trace.selected_source_refs[0]
        .source_id
        == "pdf-6"
    )

    assert trace.contract_valid is False
    assert trace.final_status == "error"

    assert (
        trace.error_code
        == "ProfessorOutputContractErrorV01"
    )

    assert trace.final_answer is None

    assert trace.system_answer_status is None

    assert (
        trace.raw_model_output
        ==
        raw["message"]["content"]
    )

    assert (
        trace.session_write_performed
        is False
    )


def test_prior_turn_case_fails_explicitly_before_model():
    base = positive_case()

    from app.services.course_knowledge.source_grounded_benchmark_v01 import (
        BenchmarkConversationTurnV01,
    )

    follow_up = (
        base.model_copy(
            update={
                "prior_turns": (
                    BenchmarkConversationTurnV01(
                        role="student",
                        text=(
                            "式 (15) 和 (16) "
                            "分别是什么？"
                        ),
                    ),
                    BenchmarkConversationTurnV01(
                        role="professor",
                        text=(
                            "前者是 Regression Method，"
                            "后者是 Distance Method。"
                        ),
                    ),
                )
            }
        )
    )

    calls = []

    def transport(request):
        calls.append(request)
        return success_response()

    with pytest.raises(
        ValueError,
        match="does not yet support prior_turns",
    ):
        run_local_professor_benchmark_case_v01(
            case=follow_up,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-follow-up",
            run_started_at=RUN_AT,
            transport=transport,
        )

    assert calls == []


def test_run_time_must_be_timezone_aware_before_candidate_execution():
    calls = []

    def transport(request):
        calls.append(request)
        return success_response()

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        run_local_professor_benchmark_case_v01(
            case=positive_case(),
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-bad-time",
            run_started_at=datetime(
                2026,
                9,
                25,
                7,
                0,
            ),
            transport=transport,
        )

    assert calls == []


def test_downstream_chat_limit_does_not_become_professor_contract_failure():
    """A 1501-char answer passes Professor's 6000-char content limit.

    Local Chat later rejects it because ConversationMessageV01 is
    limited to 1500 characters.

    That downstream failure must not be recorded as a directly
    observed Professor output-contract failure.
    """

    case = positive_case()

    long_content = "x" * 1501

    raw = success_response(
        content=long_content,
        source_ids=[
            "pdf-6",
        ],
        answer_status="course_grounded",
    )

    def transport(_request):
        return raw

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-chat-limit",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.model_called is True

    assert (
        trace.raw_model_output
        ==
        raw["message"]["content"]
    )

    # The generated Professor output was structurally valid
    # enough to pass the Professor's 6000-character boundary.
    # The later Chat message contract rejected persistence.
    #
    # The benchmark adapter does not have an explicit stage
    # callback proving the precise internal boundary, so it
    # records UNKNOWN rather than falsely claiming Professor
    # output-contract failure.
    assert trace.contract_valid is None

    assert trace.final_status == "error"

    assert trace.error_code == "ValidationError"

    assert trace.final_answer is None

    assert trace.system_answer_status is None

    assert (
        trace.session_write_performed
        is False
    )


def test_direct_professor_output_contract_failure_remains_false():
    case = positive_case()

    raw = success_response(
        source_ids=[
            "pdf-999",
        ],
    )

    def transport(_request):
        return raw

    trace = (
        run_local_professor_benchmark_case_v01(
            case=case,
            pack=pack(),
            objective_id="objective-1",
            candidate_version=(
                CANDIDATE_VERSION
            ),
            run_id="run-contract-failure",
            run_started_at=RUN_AT,
            transport=transport,
        )
    )

    assert trace.contract_valid is False

    assert (
        trace.error_code
        ==
        "ProfessorOutputContractErrorV01"
    )

    assert trace.final_status == "error"

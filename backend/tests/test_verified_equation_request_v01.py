"""URPP 14D-4B4D2G tests.

Synthetic source material only.

These tests include regression shapes derived from observed URPP failure
modes:

- Chinese "式" must behave as an explicit equation marker.
- Multi-equation requests must preserve both labels.
- Formula-only requests should not require Professor semantics.
- Method / variable / explanation requests must preserve deterministic
  formulas while indicating that semantic explanation is still needed.
- Missing reviewed equations must fail closed without partial rendering.

No LLM or Session write is used.
"""

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.services.course_knowledge.local_course_source_selector_v01 import (
    select_course_source_ids_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseSourceV01,
)

from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
)

from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

from app.services.course_knowledge.verified_equation_request_v01 import (
    equation_request_requires_explanation_v01,
    extract_explicit_equation_labels_v01,
    resolve_verified_equation_request_v01,
)


LATEX_15 = (
    r"\mathrm{height}="
    r"\begin{cases}"
    r"\dfrac{\Delta_z}{2}-D_{\mathrm{pl}},"
    r"&0\leq D_{\mathrm{pl}}\leq"
    r"\dfrac{\Delta_z}{2},\\"
    r"0,&\mathrm{otherwise}."
    r"\end{cases}"
)

LATEX_16 = (
    r"h_{\mathrm{eff}}="
    r"\begin{cases}"
    r"\min(z^+,t_c^+)-\max(z^-,t_c^-),"
    r"&\mathrm{if\ overlap},\\"
    r"0,&\mathrm{otherwise}."
    r"\end{cases}"
)


def make_source(
    *,
    source_id,
    page,
    content,
):
    return CourseSourceV01(
        course_id="synthetic-request-course",
        source_id=source_id,
        source_revision="v1",
        source_locator=(
            "local-pdf://synthetic.pdf?"
            f"pages={page}-{page}&excerpt={page}"
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


def page5():
    return make_source(
        source_id="pdf-5",
        page=5,
        content=(
            "B. HEIGHT LOOK-UP TABLE\n"
            "Synthetic equation (10)."
        ),
    )


def page6():
    return make_source(
        source_id="pdf-6",
        page=6,
        content=(
            "C. HEIGHT APPROXIMATION METHODS\n"
            "1) Regression Method\n"
            "Synthetic equation (15).\n"
            "2) Distance Method\n"
            "Synthetic equation (16)."
        ),
    )


def record(source, label, latex):
    return VerifiedEquationRecordV01(
        record_id=f"record-{label}",
        record_revision="review-v1",
        equation_label=label,
        source_ref=source.reference(),
        equation_locator=(
            source.source_locator
            + f"#equation-{label}"
        ),
        normalized_latex=latex,
        review_status="source_checked",
        reviewer_id="synthetic-reviewer",
        reviewed_at=datetime(
            2026,
            9,
            24,
            20,
            30,
            tzinfo=timezone.utc,
        ),
    )


def full_registry(source=None):
    source = source or page6()

    return VerifiedEquationRegistryV01(
        records=(
            record(
                source,
                "15",
                LATEX_15,
            ),
            record(
                source,
                "16",
                LATEX_16,
            ),
        )
    )


@pytest.mark.parametrize(
    "question, expected",
    [
        (
            "请写出式 (15) 的完整公式。",
            ("15",),
        ),
        (
            "请解释公式 (16)。",
            ("16",),
        ),
        (
            "Eq. 16",
            ("16",),
        ),
        (
            "Explain equation (15).",
            ("15",),
        ),
        (
            "式 (15) 和 (16) 分别是什么方法？",
            ("15", "16"),
        ),
        (
            "equations (15) and (16)",
            ("15", "16"),
        ),
        (
            "公式 (15)、(16)",
            ("15", "16"),
        ),
        (
            "公式 (15) 和 (15)",
            ("15",),
        ),
        (
            "第 16 页讲什么？",
            (),
        ),
        (
            "这个方法用了 15 个 voxel 吗？",
            (),
        ),
    ],
)
def test_extract_explicit_equation_labels(
    question,
    expected,
):
    assert (
        extract_explicit_equation_labels_v01(
            question
        )
        == expected
    )


@pytest.mark.parametrize(
    "question",
    [
        "",
        " ",
        "\n",
    ],
)
def test_invalid_question_rejected(question):
    with pytest.raises(
        ValueError,
        match="Invalid bounded equation question",
    ):
        extract_explicit_equation_labels_v01(
            question
        )


@pytest.mark.parametrize(
    "question",
    [
        "请解释式 (15)。",
        "式 (16) 为什么这样计算？",
        "式 (15) 的变量分别是什么？",
        "式 (15) 和 (16) 分别是什么方法？",
        "Explain equation (16).",
        "Why does Eq. 16 use min and max?",
        "Compare equations (15) and (16).",
    ],
)
def test_semantic_equation_requests_require_professor(
    question,
):
    assert (
        equation_request_requires_explanation_v01(
            question
        )
        is True
    )


@pytest.mark.parametrize(
    "question",
    [
        "请写出式 (15) 的完整公式。",
        "给出公式 (16)。",
        "Eq. 16",
        "Write equation (15).",
    ],
)
def test_formula_transcription_does_not_require_professor(
    question,
):
    assert (
        equation_request_requires_explanation_v01(
            question
        )
        is False
    )


def test_formula_only_request_resolves_without_professor_need():
    source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source),
        sources=(source,),
        question="请写出式 (16) 的完整公式。",
    )

    assert result.status == "verified"
    assert result.requested_labels == ("16",)
    assert result.missing_labels == ()
    assert result.requires_professor_explanation is False
    assert result.source_ids == ("pdf-6",)
    assert result.record_ids == ("record-16",)
    assert LATEX_16 in result.rendered_markdown


def test_m15_copy_benchmark_shape_keeps_exact_formula_and_flags_semantics():
    source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source),
        sources=(source,),
        question=(
            "请写出式 (15) 的完整分段公式、"
            "阈值和方法名称。"
        ),
    )

    assert result.status == "verified"
    assert result.requested_labels == ("15",)
    assert result.requires_professor_explanation is True
    assert LATEX_15 in result.rendered_markdown


def test_m16_copy_benchmark_shape_keeps_exact_formula_and_flags_semantics():
    source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source),
        sources=(source,),
        question=(
            "请写出式 (16) 的完整分段公式、"
            "变量含义和无重叠分支。"
        ),
    )

    assert result.status == "verified"
    assert result.requested_labels == ("16",)
    assert result.requires_professor_explanation is True
    assert LATEX_16 in result.rendered_markdown


def test_m15_m16_benchmark_shape_resolves_both_formulas():
    source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source),
        sources=(source,),
        question=(
            "式 (15) 和 (16) 分别是什么方法？"
            "把两条完整公式写出来。"
        ),
    )

    assert result.status == "verified"
    assert result.requested_labels == (
        "15",
        "16",
    )

    assert result.requires_professor_explanation is True

    assert result.record_ids == (
        "record-15",
        "record-16",
    )

    assert LATEX_15 in result.rendered_markdown
    assert LATEX_16 in result.rendered_markdown

    assert (
        result.rendered_markdown.index(
            "Equation (15)"
        )
        <
        result.rendered_markdown.index(
            "Equation (16)"
        )
    )


def test_missing_requested_equation_fails_closed_without_partial_formula():
    source = page6()

    registry = VerifiedEquationRegistryV01(
        records=(
            record(
                source,
                "15",
                LATEX_15,
            ),
        )
    )

    result = resolve_verified_equation_request_v01(
        registry=registry,
        sources=(source,),
        question=(
            "式 (15) 和 (16) 分别是什么方法？"
        ),
    )

    assert result.status == "incomplete"

    assert result.requested_labels == (
        "15",
        "16",
    )

    assert result.missing_labels == (
        "16",
    )

    assert result.rendered_markdown is None
    assert result.source_ids == ()
    assert result.record_ids == ()


def test_non_equation_question_is_not_applicable():
    source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source),
        sources=(source,),
        question=(
            "Regression Method 的核心思想是什么？"
        ),
    )

    assert result.status == "not_applicable"
    assert result.requested_labels == ()
    assert result.rendered_markdown is None
    assert result.requires_professor_explanation is False


def test_registry_cannot_use_source_not_supplied_by_selector():
    verified_source = page6()

    result = resolve_verified_equation_request_v01(
        registry=full_registry(
            verified_source
        ),
        sources=(page5(),),
        question="请写出式 (16)。",
    )

    assert result.status == "incomplete"
    assert result.missing_labels == ("16",)
    assert result.rendered_markdown is None


def test_existing_source_selector_and_request_resolver_compose():
    source5 = page5()
    source6 = page6()

    available = (
        source5,
        source6,
    )

    selector_input = tuple(
        {
            "source_id": item.source_id,
            "source_revision": (
                item.source_revision
            ),
            "source_locator": (
                item.source_locator
            ),
            "content": item.content,
        }
        for item in available
    )

    question = (
        "式 (15) 和 (16) 分别是什么方法？"
        "把两条完整公式写出来。"
    )

    selected_ids = (
        select_course_source_ids_v01(
            sources=selector_input,
            current_question=question,
        )
    )

    # Existing Selector selects page 6 based on the first
    # explicit equation marker. Both requested equations are
    # present on that selected source in this benchmark case.
    assert selected_ids == ("pdf-6",)

    selected_sources = tuple(
        item
        for item in available
        if item.source_id in selected_ids
    )

    result = resolve_verified_equation_request_v01(
        registry=full_registry(source6),
        sources=selected_sources,
        question=question,
    )

    assert result.status == "verified"

    assert result.requested_labels == (
        "15",
        "16",
    )

    assert LATEX_15 in result.rendered_markdown
    assert LATEX_16 in result.rendered_markdown

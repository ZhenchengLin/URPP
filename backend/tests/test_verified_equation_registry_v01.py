"""URPP 14D-4B4D2F tests.

All material is synthetic.

These tests exercise only deterministic Course Source selection,
verified equation lookup, exact source binding, and deterministic
rendering.

No model, network, PDF parser, Session write, Student State, or
Mastery Evidence is used.
"""

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from pydantic import ValidationError

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
    lookup_verified_equation_v01,
)


COURSE = "synthetic-equation-registry-course"

LATEX_15 = (
    r"\mathrm{height}="
    r"\begin{cases}"
    r"\dfrac{\Delta_z}{2}-D_{\mathrm{pl}},"
    r"&0\leq D_{\mathrm{pl}}\leq\dfrac{\Delta_z}{2},\\"
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
    revision="source-revision-001",
    **overrides,
):
    values = {
        "course_id": COURSE,
        "source_id": source_id,
        "source_revision": revision,
        "source_locator": (
            "local-pdf://synthetic-paper.pdf?"
            f"pages={page}-{page}&excerpt={page}"
        ),
        "content": content,
        "content_sha256": sha256(
            content.encode("utf-8")
        ).hexdigest(),
        "visibility": "student_visible",
        "use_permission": (
            "approved_for_local_teaching"
        ),
        "review_status": "approved",
    }

    values.update(overrides)

    return CourseSourceV01(**values)


def page5():
    return make_source(
        source_id="pdf-5",
        page=5,
        content=(
            "B. HEIGHT LOOK-UP TABLE\n"
            "Synthetic equation (10) is on this page."
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


def make_record(
    *,
    source,
    label,
    latex,
    record_id=None,
    record_revision="review-revision-001",
    review_status="source_checked",
):
    reviewed = (
        review_status
        in {"source_checked", "revoked"}
    )

    return VerifiedEquationRecordV01(
        record_id=(
            record_id
            or f"record-{source.source_id}-{label}"
        ),
        record_revision=record_revision,
        equation_label=label,
        source_ref=source.reference(),
        equation_locator=(
            source.source_locator
            + f"#equation-{label}"
        ),
        normalized_latex=latex,
        review_status=review_status,
        reviewer_id=(
            "synthetic-reviewer"
            if reviewed
            else None
        ),
        reviewed_at=(
            datetime(
                2026,
                9,
                24,
                20,
                0,
                tzinfo=timezone.utc,
            )
            if reviewed
            else None
        ),
    )


def make_registry(*records):
    return VerifiedEquationRegistryV01(
        records=tuple(records)
    )


def test_exact_verified_equation_lookup():
    source = page6()

    record = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
    )

    result = lookup_verified_equation_v01(
        registry=make_registry(record),
        sources=(source,),
        equation_label="16",
    )

    assert result is not None
    assert result.record == record
    assert result.source == source
    assert LATEX_16 in result.rendered_markdown
    assert result.rendered_markdown.startswith(
        "**Equation (16)**"
    )


def test_lookup_is_deterministic():
    source = page6()

    registry = make_registry(
        make_record(
            source=source,
            label="16",
            latex=LATEX_16,
        )
    )

    first = lookup_verified_equation_v01(
        registry=registry,
        sources=(source,),
        equation_label="16",
    )

    second = lookup_verified_equation_v01(
        registry=registry,
        sources=(source,),
        equation_label="16",
    )

    assert first == second
    assert (
        first.rendered_markdown
        == second.rendered_markdown
    )


def test_unknown_equation_returns_none():
    source = page6()

    registry = make_registry(
        make_record(
            source=source,
            label="15",
            latex=LATEX_15,
        )
    )

    assert (
        lookup_verified_equation_v01(
            registry=registry,
            sources=(source,),
            equation_label="16",
        )
        is None
    )


@pytest.mark.parametrize(
    "review_status",
    [
        "proposed",
        "revoked",
    ],
)
def test_non_current_review_record_is_not_teaching_match(
    review_status,
):
    source = page6()

    record = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
        review_status=review_status,
    )

    assert (
        lookup_verified_equation_v01(
            registry=make_registry(record),
            sources=(source,),
            equation_label="16",
        )
        is None
    )


def test_registry_does_not_grant_unselected_source_access():
    source = page6()

    record = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
    )

    unrelated = page5()

    assert (
        lookup_verified_equation_v01(
            registry=make_registry(record),
            sources=(unrelated,),
            equation_label="16",
        )
        is None
    )


def test_stale_source_revision_does_not_match():
    original = page6()

    record = make_record(
        source=original,
        label="16",
        latex=LATEX_16,
    )

    changed = make_source(
        source_id="pdf-6",
        page=6,
        revision="source-revision-002",
        content=original.content,
    )

    assert (
        lookup_verified_equation_v01(
            registry=make_registry(record),
            sources=(changed,),
            equation_label="16",
        )
        is None
    )


def test_changed_source_content_does_not_match():
    original = page6()

    record = make_record(
        source=original,
        label="16",
        latex=LATEX_16,
    )

    changed_content = (
        original.content
        + "\nSynthetic revision change."
    )

    changed = make_source(
        source_id="pdf-6",
        page=6,
        content=changed_content,
    )

    assert (
        lookup_verified_equation_v01(
            registry=make_registry(record),
            sources=(changed,),
            equation_label="16",
        )
        is None
    )


def test_tampered_source_is_revalidated_before_lookup():
    source = page6()

    record = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
    )

    tampered = source.model_copy(
        update={
            "content": (
                source.content
                + "\nTampered."
            )
        }
    )

    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        lookup_verified_equation_v01(
            registry=make_registry(record),
            sources=(tampered,),
            equation_label="16",
        )


def test_duplicate_record_ids_are_rejected():
    source = page6()

    first = make_record(
        source=source,
        label="15",
        latex=LATEX_15,
        record_id="same-record",
    )

    second = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
        record_id="same-record",
    )

    with pytest.raises(
        ValidationError,
        match="Duplicate verified equation record ID",
    ):
        make_registry(
            first,
            second,
        )


def test_duplicate_exact_bindings_are_rejected():
    source = page6()

    first = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
        record_id="record-a",
        record_revision="review-a",
    )

    second = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
        record_id="record-b",
        record_revision="review-b",
    )

    with pytest.raises(
        ValidationError,
        match="Duplicate verified equation binding",
    ):
        make_registry(
            first,
            second,
        )


def test_ambiguous_same_label_across_selected_sources_fails_closed():
    first_source = make_source(
        source_id="pdf-a",
        page=6,
        content="Synthetic equation (16), source A.",
    )

    second_source = make_source(
        source_id="pdf-b",
        page=7,
        content="Synthetic equation (16), source B.",
    )

    registry = make_registry(
        make_record(
            source=first_source,
            label="16",
            latex=LATEX_16,
        ),
        make_record(
            source=second_source,
            label="16",
            latex=LATEX_16,
        ),
    )

    with pytest.raises(
        ValueError,
        match="Ambiguous verified equation lookup",
    ):
        lookup_verified_equation_v01(
            registry=registry,
            sources=(
                first_source,
                second_source,
            ),
            equation_label="16",
        )


@pytest.mark.parametrize(
    "label",
    [
        "",
        " ",
        "(16)",
        "16 17",
        "16/17",
        "x" * 65,
    ],
)
def test_invalid_lookup_label_is_rejected(
    label,
):
    source = page6()

    registry = make_registry(
        make_record(
            source=source,
            label="16",
            latex=LATEX_16,
        )
    )

    with pytest.raises(
        ValueError,
        match="Invalid equation label",
    ):
        lookup_verified_equation_v01(
            registry=registry,
            sources=(source,),
            equation_label=label,
        )


def test_registry_revalidates_model_copy_bypass():
    source = page6()

    record = make_record(
        source=source,
        label="16",
        latex=LATEX_16,
    )

    registry = make_registry(record)

    bypassed = registry.model_copy(
        update={
            "records": (
                record,
                record,
            )
        }
    )

    with pytest.raises(
        ValidationError,
        match="Duplicate verified equation",
    ):
        lookup_verified_equation_v01(
            registry=bypassed,
            sources=(source,),
            equation_label="16",
        )


def test_existing_source_selector_composes_with_registry():
    source5 = page5()
    source6 = page6()

    selection_input = tuple(
        {
            "source_id": source.source_id,
            "source_revision": (
                source.source_revision
            ),
            "source_locator": (
                source.source_locator
            ),
            "content": source.content,
        }
        for source in (
            source5,
            source6,
        )
    )

    selected_ids = (
        select_course_source_ids_v01(
            sources=selection_input,
            current_question=(
                "请写出式 (16) 的完整公式。"
            ),
        )
    )

    assert selected_ids == ("pdf-6",)

    selected_sources = tuple(
        source
        for source in (
            source5,
            source6,
        )
        if source.source_id in selected_ids
    )

    registry = make_registry(
        make_record(
            source=source6,
            label="15",
            latex=LATEX_15,
        ),
        make_record(
            source=source6,
            label="16",
            latex=LATEX_16,
        ),
    )

    result = lookup_verified_equation_v01(
        registry=registry,
        sources=selected_sources,
        equation_label="16",
    )

    assert result is not None
    assert result.source.source_id == "pdf-6"
    assert result.record.equation_label == "16"
    assert result.record.normalized_latex == LATEX_16
    assert LATEX_16 in result.rendered_markdown

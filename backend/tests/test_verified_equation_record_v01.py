"""14D-4B4D2E tests.

All source material and equations in this test file are synthetic.
No model, PDF parser, network service, Session, Student State, or
Mastery Evidence is used.
"""

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from pydantic import ValidationError

from app.services.course_knowledge.models_v01 import (
    CourseSourceV01,
)

from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
    render_verified_equation_markdown_v01,
    validate_verified_equation_binding_v01,
)


COURSE = "synthetic-equation-course"

CONTENT = (
    "Synthetic source text containing equation (15)."
)

LATEX = (
    r"\mathrm{height}="
    "\n"
    r"\begin{cases}"
    "\n"
    r"\dfrac{\Delta_z}{2}-D_{\mathrm{pl}},"
    r"&0\leq D_{\mathrm{pl}}\leq"
    r"\dfrac{\Delta_z}{2},\\"
    "\n"
    r"0,&\mathrm{otherwise}."
    "\n"
    r"\end{cases}"
)


def make_source(**overrides):
    values = {
        "course_id": COURSE,
        "source_id": "source-page-6",
        "source_revision": "source-revision-001",
        "source_locator": (
            "local-pdf://synthetic.pdf?"
            "sha256=abc&pages=6-6&excerpt=6"
        ),
        "content": CONTENT,
        "content_sha256": sha256(
            CONTENT.encode("utf-8")
        ).hexdigest(),
        "visibility": "student_visible",
        "use_permission": (
            "approved_for_local_teaching"
        ),
        "review_status": "approved",
    }

    values.update(overrides)

    return CourseSourceV01(**values)


def make_record(
    source=None,
    **overrides,
):
    if source is None:
        source = make_source()

    values = {
        "record_id": "equation-record-15",
        "record_revision": "equation-review-001",
        "equation_label": "15",
        "source_ref": source.reference(),
        "equation_locator": (
            source.source_locator + "#equation-15"
        ),
        "normalized_latex": LATEX,
        "review_status": "source_checked",
        "reviewer_id": "synthetic-reviewer",
        "reviewed_at": datetime(
            2026,
            9,
            24,
            18,
            0,
            tzinfo=timezone.utc,
        ),
    }

    values.update(overrides)

    return VerifiedEquationRecordV01(**values)


def test_valid_source_checked_equation_renders_exact_latex():
    source = make_source()
    record = make_record(source)

    rendered = render_verified_equation_markdown_v01(
        record=record,
        source=source,
    )

    assert rendered == (
        "**Equation (15)**\n\n"
        "$$\n"
        + LATEX
        + "\n$$"
    )

    assert LATEX in rendered


def test_rendering_is_deterministic():
    source = make_source()
    record = make_record(source)

    first = render_verified_equation_markdown_v01(
        record=record,
        source=source,
    )

    second = render_verified_equation_markdown_v01(
        record=record,
        source=source,
    )

    assert first == second


def test_record_survives_json_round_trip():
    original = make_record()

    recovered = (
        VerifiedEquationRecordV01
        .model_validate_json(
            original.model_dump_json()
        )
    )

    assert recovered == original


def test_record_is_immutable_by_normal_assignment():
    record = make_record()

    with pytest.raises(ValidationError):
        record.equation_label = "16"


@pytest.mark.parametrize(
    "latex",
    [
        "   ",
        "$$x=1$$",
        r"\[x=1\]",
        "```latex\nx=1\n```",
        "x=\b egin",
        "x=\f frac",
        "x=\t text",
        "x=\r right",
    ],
)
def test_rejects_invalid_or_transport_corrupted_latex(
    latex,
):
    with pytest.raises(ValidationError):
        make_record(
            normalized_latex=latex
        )


def test_renderer_revalidates_model_copy_bypass():
    source = make_source()
    record = make_record(source)

    corrupted = record.model_copy(
        update={
            "normalized_latex": "x=\b egin{cases}"
        }
    )

    with pytest.raises(
        ValidationError,
        match="control character",
    ):
        render_verified_equation_markdown_v01(
            record=corrupted,
            source=source,
        )


def test_proposed_record_cannot_render():
    source = make_source()

    record = make_record(
        source,
        review_status="proposed",
        reviewer_id=None,
        reviewed_at=None,
    )

    with pytest.raises(
        ValueError,
        match="not currently source-checked",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=source,
        )


def test_revoked_record_cannot_render():
    source = make_source()

    record = make_record(
        source,
        review_status="revoked",
    )

    with pytest.raises(
        ValueError,
        match="not currently source-checked",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=source,
        )


def test_source_revision_mismatch_fails_closed():
    original = make_source()
    record = make_record(original)

    changed = make_source(
        source_revision="source-revision-002"
    )

    with pytest.raises(
        ValueError,
        match="exact Course Source revision",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=changed,
        )


def test_source_locator_mismatch_fails_closed():
    original = make_source()
    record = make_record(original)

    changed = make_source(
        source_locator=(
            "local-pdf://synthetic.pdf?"
            "sha256=abc&pages=5-5&excerpt=5"
        )
    )

    with pytest.raises(
        ValueError,
        match="exact Course Source revision",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=changed,
        )


def test_source_content_digest_binding_fails_on_new_content():
    original = make_source()
    record = make_record(original)

    changed_content = (
        CONTENT
        + " Different source revision content."
    )

    changed = make_source(
        content=changed_content,
        content_sha256=sha256(
            changed_content.encode("utf-8")
        ).hexdigest(),
    )

    with pytest.raises(
        ValueError,
        match="exact Course Source revision",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=changed,
        )


def test_renderer_revalidates_tampered_source_content():
    source = make_source()
    record = make_record(source)

    tampered = source.model_copy(
        update={
            "content": CONTENT + " tampered"
        }
    )

    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=tampered,
        )


@pytest.mark.parametrize(
    "overrides, message",
    [
        (
            {"visibility": "restricted"},
            "not student-visible",
        ),
        (
            {
                "use_permission":
                "not_authorized"
            },
            "not approved for local teaching",
        ),
        (
            {"review_status": "proposed"},
            "source is not approved",
        ),
        (
            {"review_status": "revoked"},
            "source is not approved",
        ),
    ],
)
def test_renderer_does_not_grant_source_permission(
    overrides,
    message,
):
    source = make_source(**overrides)

    # Build the record against this exact source to prove that
    # exact binding alone is NOT sufficient authorization.
    record = make_record(source)

    with pytest.raises(
        ValueError,
        match=message,
    ):
        render_verified_equation_markdown_v01(
            record=record,
            source=source,
        )


def test_source_checked_requires_review_provenance():
    with pytest.raises(
        ValidationError,
        match="reviewer metadata",
    ):
        make_record(
            reviewer_id=None,
        )

    with pytest.raises(
        ValidationError,
        match="review time",
    ):
        make_record(
            reviewed_at=None,
        )


def test_review_time_must_be_timezone_aware():
    with pytest.raises(
        ValidationError,
        match="timezone-aware",
    ):
        make_record(
            reviewed_at=datetime(
                2026,
                9,
                24,
                18,
                0,
            )
        )


def test_proposed_record_cannot_claim_review_metadata():
    with pytest.raises(
        ValidationError,
        match="cannot claim completed review metadata",
    ):
        make_record(
            review_status="proposed",
        )


def test_explicit_binding_returns_revalidated_objects():
    source = make_source()
    record = make_record(source)

    checked_record, checked_source = (
        validate_verified_equation_binding_v01(
            record=record,
            source=source,
        )
    )

    assert checked_record == record
    assert checked_source == source
    assert (
        checked_record.source_ref
        == checked_source.reference()
    )

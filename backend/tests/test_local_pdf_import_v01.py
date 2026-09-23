"""
URPP 14D-1B PDF Import contract tests.

Use a synthetic extraction boundary rather than running
an actual PDF parser or model. Real pypdf integration is
a separate dependency-enabled test.
"""

from hashlib import sha256

import pytest

import app.services.course_knowledge.local_pdf_import_v01 as importer

from app.services.course_knowledge.course_pack_v01 import (
    resolve_course_knowledge_v01,
)


PDF_BYTES = b"%PDF-1.7\nsynthetic-test-data"


def build(
    monkeypatch,
    pages,
    **overrides,
):
    monkeypatch.setattr(
        importer,
        "_extract_pdf_pages_v01",
        lambda _: tuple(pages),
    )

    arguments = {
        "filename": "ct_notes.pdf",
        "pdf_bytes": PDF_BYTES,
        "course_id": "ct-course",
        "objective_id": "projection-math",
        "objective_description": (
            "Explain CT projection mathematics."
        ),
        "allow_local_teaching": True,
    }

    arguments.update(overrides)

    return importer.build_local_pdf_pack_v01(
        **arguments
    )


def test_pdf_builds_existing_course_pack(monkeypatch):
    result = build(
        monkeypatch,
        [
            "Line integral describes projection.",
            "Beer-Lambert law describes attenuation.",
        ],
    )

    pack = result.pack

    assert result.total_pages == 2
    assert result.pages_without_text == ()
    assert len(pack.sources) == 1

    knowledge = resolve_course_knowledge_v01(
        pack=pack,
        course_id="ct-course",
        objective_id="projection-math",
        expected_pack_revision=pack.pack_revision,
    )

    assert knowledge.sources == pack.sources

    assert "Line integral" in (
        knowledge.sources[0].content
    )

    assert "Beer-Lambert" in (
        knowledge.sources[0].content
    )


def test_original_pdf_identity_is_preserved(monkeypatch):
    result = build(
        monkeypatch,
        ["Synthetic PDF text."],
    )

    digest = sha256(
        PDF_BYTES
    ).hexdigest()

    assert result.original_file_sha256 == digest
    assert result.pack.pack_revision == digest
    assert digest in (
        result.pack.sources[0].source_locator
    )


def test_page_locator_records_page_range(monkeypatch):
    result = build(
        monkeypatch,
        [
            "First page.",
            "Second page.",
            "Third page.",
        ],
    )

    assert "pages=1-3" in (
        result.pack.sources[0].source_locator
    )


def test_blank_page_is_reported(monkeypatch):
    result = build(
        monkeypatch,
        [
            "Readable page.",
            "  ",
            "Another readable page.",
        ],
    )

    assert result.total_pages == 3
    assert result.pages_without_text == (2,)

    content = "".join(
        source.content
        for source in result.pack.sources
    )

    assert "Readable page." in content
    assert "Another readable page." in content


def test_all_scanned_or_blank_pages_rejected(monkeypatch):
    with pytest.raises(
        ValueError,
        match="OCR",
    ):
        build(
            monkeypatch,
            ["", "  ", ""],
        )


def test_long_page_is_split_without_discarding_text(
    monkeypatch,
):
    text = (
        "A" * 7000
        + "B" * 7000
    )

    result = build(
        monkeypatch,
        [text],
    )

    assert len(result.pack.sources) >= 2

    recovered = "".join(
        source.content
        for source in result.pack.sources
    )

    assert recovered.count("A") == 7000
    assert recovered.count("B") == 7000


def test_oversized_pdf_text_is_rejected(monkeypatch):
    with pytest.raises(
        ValueError,
        match="limit",
    ):
        build(
            monkeypatch,
            ["A" * 48001],
        )


def test_more_than_eight_excerpts_is_rejected(
    monkeypatch,
):
    with pytest.raises(
        ValueError,
        match="eight",
    ):
        build(
            monkeypatch,
            ["A" * 48000],
        )


def test_permission_is_required(monkeypatch):
    with pytest.raises(PermissionError):
        build(
            monkeypatch,
            ["Readable PDF."],
            allow_local_teaching=False,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "../ct.pdf",
        "/tmp/ct.pdf",
        r"folder\ct.pdf",
        "notes.txt",
    ],
)
def test_invalid_filenames_rejected(
    monkeypatch,
    filename,
):
    with pytest.raises(ValueError):
        build(
            monkeypatch,
            ["Readable PDF."],
            filename=filename,
        )


def test_non_pdf_header_rejected(monkeypatch):
    with pytest.raises(
        ValueError,
        match="PDF header",
    ):
        build(
            monkeypatch,
            ["Readable PDF."],
            pdf_bytes=b"not a PDF",
        )


def test_import_does_not_require_model_or_database(
    monkeypatch,
):
    result = build(
        monkeypatch,
        ["A projection is a line integral."],
    )

    assert result.pack.sources
    assert result.pack.objectives

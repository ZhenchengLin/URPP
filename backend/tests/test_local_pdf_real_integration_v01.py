"""
URPP 14D-1C: real PDF extraction integration tests.

Synthetic PDFs are constructed in memory with pypdf.
No personal documents, model inference, network requests,
persistent databases, or application file writes.

These tests skip when the optional PDF dependency is absent.
The 14D-1C validation command supplies that dependency.
"""

from hashlib import sha256
from io import BytesIO

import pytest

pypdf = pytest.importorskip("pypdf")

from pypdf import PdfReader, PdfWriter

from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.services.course_knowledge.course_pack_v01 import (
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.local_pdf_import_v01 import (
    build_local_pdf_pack_v01,
)


def make_pdf(
    page_texts,
    *,
    encrypted=False,
):
    """
    Build a real PDF with standard Helvetica text.

    None represents a blank page with no text content.
    No reportlab, external fonts, or OCR are required.
    """

    writer = PdfWriter()

    for page_text in page_texts:
        page = writer.add_blank_page(
            width=612,
            height=792,
        )

        if page_text is None:
            continue

        if not page_text.isascii():
            raise ValueError(
                "Synthetic PDF fixture must use ASCII."
            )

        # Only fixed, trusted ASCII fixture text is used
        # in this PDF content stream.
        if any(
            character in page_text
            for character in "()\\"
        ):
            raise ValueError(
                "Fixture contains an unescaped PDF character."
            )

        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): DictionaryObject({
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }),
            }),
        })

        stream = DecodedStreamObject()

        stream.set_data(
            (
                "BT "
                "/F1 12 Tf "
                "72 720 Td "
                f"({page_text}) Tj "
                "ET"
            ).encode("ascii")
        )

        # Attach the generated text stream to the page.
        page[NameObject("/Contents")] = writer._add_object(
            stream
        )

    if encrypted:
        writer.encrypt(
            user_password="synthetic-test-password"
        )

    output = BytesIO()
    writer.write(output)

    result = output.getvalue()

    assert result.startswith(b"%PDF-")

    return result


def import_pdf(pdf_bytes):
    return build_local_pdf_pack_v01(
        filename="synthetic_ct_notes.pdf",
        pdf_bytes=pdf_bytes,
        course_id="synthetic-ct-course",
        objective_id="projection-mathematics",
        objective_description=(
            "Explain CT projection mathematics "
            "using the supplied notes."
        ),
        allow_local_teaching=True,
    )


def test_real_pdf_text_is_extracted_and_grounded():
    original = make_pdf([
        "CT projection is a line integral.",
        "Beer Lambert law models attenuation.",
    ])

    result = import_pdf(original)

    assert result.total_pages == 2
    assert result.pages_without_text == ()

    assert result.original_file_sha256 == sha256(
        original
    ).hexdigest()

    knowledge = resolve_course_knowledge_v01(
        pack=result.pack,
        course_id="synthetic-ct-course",
        objective_id="projection-mathematics",
        expected_pack_revision=result.pack.pack_revision,
    )

    extracted = "\n".join(
        source.content
        for source in knowledge.sources
    )

    assert "CT projection is a line integral." in extracted
    assert "Beer Lambert law models attenuation." in extracted

    assert "pages=1-2" in (
        knowledge.sources[0].source_locator
    )


def test_real_pdf_blank_page_is_reported():
    original = make_pdf([
        "First page has selectable text.",
        None,
        "Third page also contains text.",
    ])

    result = import_pdf(original)

    assert result.total_pages == 3
    assert result.pages_without_text == (2,)

    extracted = "\n".join(
        source.content
        for source in result.pack.sources
    )

    assert "First page has selectable text." in extracted
    assert "Third page also contains text." in extracted


def test_real_pdf_with_no_selectable_text_is_rejected():
    original = make_pdf([
        None,
        None,
    ])

    with pytest.raises(
        ValueError,
        match="OCR",
    ):
        import_pdf(original)


def test_real_encrypted_pdf_is_rejected():
    original = make_pdf(
        ["Encrypted synthetic notes."],
        encrypted=True,
    )

    reader = PdfReader(
        BytesIO(original)
    )

    assert reader.is_encrypted

    with pytest.raises(
        ValueError,
        match="Encrypted",
    ):
        import_pdf(original)


def test_real_corrupted_pdf_is_rejected():
    corrupted = (
        b"%PDF-1.7\n"
        b"This is not a complete PDF file."
    )

    with pytest.raises(
        ValueError,
        match="extraction failed",
    ):
        import_pdf(corrupted)

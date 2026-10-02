"""
URPP 14D-1B: local, text-based PDF Course Pack import.

PDF bytes are supplied by an explicit caller. This module
does not open arbitrary paths, save uploads, call an LLM,
or update Student State.

A local caller must explicitly confirm permission for
local teaching. This confirmation is not copyright
verification or authorization for public distribution.

Text extraction requires the optional pypdf dependency.
Scanned documents require a separate OCR workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from urllib.parse import quote

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.local_material_import_v01 import (
    MAX_SOURCE_CHARACTERS,
    MAX_SOURCES,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 32
MAX_EXTRACTED_CHARACTERS = 48000


@dataclass(frozen=True)
class LocalPDFImportResultV01:
    pack: CoursePackV01
    total_pages: int
    pages_without_text: tuple[int, ...]
    original_file_sha256: str


def _identifier(value: str, name: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 128
    ):
        raise ValueError(
            f"{name} must contain 1–128 nonblank characters."
        )

    return value.strip()


def _extract_pdf_pages_v01(
    pdf_bytes: bytes,
) -> tuple[str, ...]:
    """
    Extract selectable text from each PDF page.

    This is intentionally separate from Course Pack
    construction so extraction and provenance handling
    can be validated independently.
    """

    try:
        from pypdf import PdfReader

    except ImportError as exc:
        raise RuntimeError(
            "PDF extraction requires the optional "
            "'pypdf' dependency."
        ) from exc

    try:
        reader = PdfReader(
            BytesIO(pdf_bytes),
            strict=False,
        )

        if reader.is_encrypted:
            raise ValueError(
                "Encrypted PDFs are not supported."
            )

        page_count = len(reader.pages)

        if not 1 <= page_count <= MAX_PDF_PAGES:
            raise ValueError(
                "PDF must contain 1–32 pages."
            )

        pages = []

        total_characters = 0

        for page in reader.pages:
            extracted = page.extract_text()

            if extracted is None:
                extracted = ""

            if type(extracted) is not str:
                raise ValueError(
                    "PDF extractor returned invalid text."
                )

            total_characters += len(extracted)

            if total_characters > MAX_EXTRACTED_CHARACTERS:
                raise ValueError(
                    "Extracted PDF text exceeds the "
                    "current local teaching limit."
                )

            pages.append(extracted)

        return tuple(pages)

    except ValueError:
        raise

    except Exception as exc:
        raise ValueError(
            "PDF text extraction failed."
        ) from exc


def _source_chunks_v01(
    pages: tuple[str, ...],
) -> tuple[
    tuple[str, int, int],
    ...
]:
    """
    Build bounded source chunks with page provenance.

    Each returned item is:
        (source_text, first_page, last_page)

    Nonempty extracted text is preserved without
    silently dropping the end of an oversized document.
    """

    chunks = []

    current_text = ""
    current_first_page = None
    current_last_page = None

    def flush():
        nonlocal current_text
        nonlocal current_first_page
        nonlocal current_last_page

        if not current_text:
            return

        chunks.append(
            (
                current_text,
                current_first_page,
                current_last_page,
            )
        )

        current_text = ""
        current_first_page = None
        current_last_page = None

    for page_number, page_text in enumerate(
        pages,
        start=1,
    ):
        if not page_text.strip():
            continue

        offset = 0
        fragment_number = 0

        while offset < len(page_text):
            fragment_number += 1

            heading = (
                f"[PDF page {page_number}, "
                f"fragment {fragment_number}]\n"
            )

            capacity = (
                MAX_SOURCE_CHARACTERS
                - len(heading)
            )

            if capacity <= 0:
                raise ValueError(
                    "PDF source heading exceeds the "
                    "available excerpt limit."
                )

            fragment = page_text[
                offset:offset + capacity
            ]

            offset += len(fragment)

            piece = heading + fragment

            separator = (
                "\n\n"
                if current_text
                else ""
            )

            if (
                current_text
                and len(
                    current_text
                    + separator
                    + piece
                ) > MAX_SOURCE_CHARACTERS
            ):
                flush()
                separator = ""

            if current_first_page is None:
                current_first_page = page_number

            current_last_page = page_number

            current_text += separator + piece

            if len(chunks) >= MAX_SOURCES:
                raise ValueError(
                    "PDF requires more than eight "
                    "Source Excerpts."
                )

    flush()

    if len(chunks) > MAX_SOURCES:
        raise ValueError(
            "PDF requires more than eight "
            "Source Excerpts."
        )

    return tuple(chunks)


def build_local_pdf_pack_v01(
    *,
    filename: str,
    pdf_bytes: bytes,
    course_id: str,
    objective_id: str,
    objective_description: str,
    allow_local_teaching: bool,
) -> LocalPDFImportResultV01:
    """Convert one explicitly selected PDF into a Course Pack."""

    if allow_local_teaching is not True:
        raise PermissionError(
            "Explicit local-teaching permission is required."
        )

    course_id = _identifier(
        course_id,
        "course_id",
    )

    objective_id = _identifier(
        objective_id,
        "objective_id",
    )

    if (
        type(objective_description) is not str
        or not objective_description.strip()
        or len(objective_description) > 1000
    ):
        raise ValueError(
            "Objective description must contain "
            "1–1000 nonblank characters."
        )

    if (
        type(filename) is not str
        or not filename
        or len(filename) > 255
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or not filename.lower().endswith(".pdf")
    ):
        raise ValueError(
            "A PDF filename without directory "
            "components is required."
        )

    if type(pdf_bytes) is not bytes:
        raise TypeError(
            "PDF content must be supplied as bytes."
        )

    if not 0 < len(pdf_bytes) <= MAX_PDF_BYTES:
        raise ValueError(
            "PDF is empty or exceeds the "
            "8 MiB import limit."
        )

    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError(
            "Input does not have a PDF header."
        )

    file_digest = sha256(
        pdf_bytes
    ).hexdigest()

    pages = _extract_pdf_pages_v01(
        pdf_bytes
    )

    if not 1 <= len(pages) <= MAX_PDF_PAGES:
        raise ValueError(
            "PDF must contain 1–32 pages."
        )

    if any(
        type(page) is not str
        for page in pages
    ):
        raise ValueError(
            "PDF extractor returned invalid page text."
        )

    if sum(map(len, pages)) > MAX_EXTRACTED_CHARACTERS:
        raise ValueError(
            "Extracted PDF text exceeds the "
            "current local teaching limit."
        )

    missing_text_pages = tuple(
        index
        for index, text in enumerate(
            pages,
            start=1,
        )
        if not text.strip()
    )

    if len(missing_text_pages) == len(pages):
        raise ValueError(
            "PDF contains no extractable text. "
            "A scanned document may require OCR."
        )

    chunks = _source_chunks_v01(
        pages
    )

    if not chunks:
        raise ValueError(
            "PDF contains no usable teaching excerpts."
        )

    pack_id = (
        "local-pdf-"
        + file_digest[:24]
    )

    sources = []

    for index, (
        excerpt,
        first_page,
        last_page,
    ) in enumerate(
        chunks,
        start=1,
    ):
        locator = (
            "local-pdf://"
            + quote(filename, safe="")
            + f"?sha256={file_digest}"
            + f"&pages={first_page}-{last_page}"
            + f"&excerpt={index}"
        )

        sources.append(
            CourseSourceV01(
                course_id=course_id,
                source_id=(
                    f"{pack_id}-excerpt-{index}"
                ),
                source_revision=file_digest,
                source_locator=locator,
                content=excerpt,
                content_sha256=sha256(
                    excerpt.encode("utf-8")
                ).hexdigest(),
                visibility="student_visible",
                use_permission="approved_for_local_teaching",
                review_status="approved",
            )
        )

    objective = CourseLearningObjectiveV01(
        course_id=course_id,
        objective_id=objective_id,
        description=objective_description.strip(),
        review_status="approved",
        source_refs=tuple(
            source.reference()
            for source in sources
        ),
    )

    pack = CoursePackV01(
        course_id=course_id,
        pack_id=pack_id,
        pack_revision=file_digest,
        objectives=(objective,),
        sources=tuple(sources),
    )

    return LocalPDFImportResultV01(
        pack=pack,
        total_pages=len(pages),
        pages_without_text=missing_text_pages,
        original_file_sha256=file_digest,
    )

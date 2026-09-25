"""
URPP 14D-1A: local text and Markdown material import.

Convert explicitly supplied local teaching material into an
existing, version-bound CoursePackV01.

The caller supplies the bytes and explicitly confirms that
the material may be used for local teaching.

This module performs no filesystem writes, model calls,
Student State updates, or assessment operations.

The approval fields describe the caller's local choice.
They do not establish copyright ownership, authenticate
the caller, or authorize public distribution.

PDF extraction and the local upload endpoint are separate
integration steps.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


SUPPORTED_EXTENSIONS = frozenset({
    ".txt",
    ".md",
    ".markdown",
})

MAX_FILE_BYTES = 128 * 1024
MAX_SOURCE_CHARACTERS = 6000
MAX_SOURCES = 8


def _required_identifier(value: str, name: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 128
    ):
        raise ValueError(
            f"{name} must contain 1–128 nonblank characters."
        )

    return value.strip()


def _required_description(value: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > 1000
    ):
        raise ValueError(
            "Objective description must contain "
            "1–1000 nonblank characters."
        )

    return value.strip()


def split_material_into_excerpts_v01(
    text: str,
) -> tuple[str, ...]:
    """
    Split one document into bounded source excerpts.

    No substantive content may be silently discarded.
    Oversized material is rejected rather than truncated.

    The current Professor supports at most eight excerpts.
    """

    if type(text) is not str or not text.strip():
        raise ValueError(
            "Course material must contain readable text."
        )

    if "\x00" in text:
        raise ValueError(
            "Course material contains a NUL character."
        )

    if len(text) > MAX_SOURCE_CHARACTERS * MAX_SOURCES:
        raise ValueError(
            "Course material exceeds the current "
            "eight-excerpt teaching limit."
        )

    excerpts = []

    for start in range(
        0,
        len(text),
        MAX_SOURCE_CHARACTERS,
    ):
        excerpt = text[
            start:start + MAX_SOURCE_CHARACTERS
        ]

        # A whitespace-only boundary segment is not a
        # useful Course Source. Nonblank text is never
        # discarded.
        if excerpt.strip():
            excerpts.append(excerpt)

    if not excerpts:
        raise ValueError(
            "Course material contains no usable excerpt."
        )

    if len(excerpts) > MAX_SOURCES:
        raise ValueError(
            "Too many course excerpts."
        )

    return tuple(excerpts)


def build_local_material_pack_v01(
    *,
    filename: str,
    file_bytes: bytes,
    course_id: str,
    objective_id: str,
    objective_description: str,
    allow_local_teaching: bool,
) -> CoursePackV01:
    """
    Build one version-bound Course Pack from user-selected
    UTF-8 text or Markdown.

    File bytes are provided by the caller; this function
    does not open arbitrary paths.

    Each excerpt retains a filename/chunk locator and is
    tied to the supplied file's SHA-256 digest.

    The original upload still needs to be stored separately
    by the future local upload workflow.
    """

    if allow_local_teaching is not True:
        raise PermissionError(
            "Explicit local-teaching permission is required."
        )

    course_id = _required_identifier(
        course_id,
        "course_id",
    )

    objective_id = _required_identifier(
        objective_id,
        "objective_id",
    )

    objective_description = _required_description(
        objective_description
    )

    if (
        type(filename) is not str
        or not filename
        or "\x00" in filename
    ):
        raise ValueError(
            "A valid material filename is required."
        )

    # File names are labels, never filesystem destinations.
    if (
        Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise ValueError(
            "Material filename must not contain a path."
        )

    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            "Only UTF-8 TXT and Markdown are supported "
            "by 14D-1A."
        )

    if type(file_bytes) is not bytes:
        raise TypeError(
            "Course material must be supplied as bytes."
        )

    if not 0 < len(file_bytes) <= MAX_FILE_BYTES:
        raise ValueError(
            "Course material is empty or exceeds "
            "the local upload size limit."
        )

    try:
        text = file_bytes.decode("utf-8-sig")

    except UnicodeDecodeError as exc:
        raise ValueError(
            "Text/Markdown material must use UTF-8."
        ) from exc

    excerpts = split_material_into_excerpts_v01(
        text
    )

    file_sha256 = sha256(
        file_bytes
    ).hexdigest()

    pack_id = (
        "local-material-"
        + file_sha256[:24]
    )

    pack_revision = file_sha256

    sources = []

    for index, excerpt in enumerate(
        excerpts,
        start=1,
    ):
        source_id = (
            f"{pack_id}-excerpt-{index}"
        )

        # A locator records the supplied filename, chunk
        # position, and file identity. It does not claim
        # that the original file has already been retained.
        locator = (
            "local-upload://"
            + quote(filename, safe="")
            + f"?sha256={file_sha256}"
            + f"&excerpt={index}"
        )

        source = CourseSourceV01(
            course_id=course_id,
            source_id=source_id,
            source_revision=file_sha256,
            source_locator=locator,
            content=excerpt,
            content_sha256=sha256(
                excerpt.encode("utf-8")
            ).hexdigest(),
            visibility="student_visible",
            use_permission="approved_for_local_teaching",
            review_status="approved",
        )

        sources.append(source)

    objective = CourseLearningObjectiveV01(
        course_id=course_id,
        objective_id=objective_id,
        description=objective_description,
        review_status="approved",
        source_refs=tuple(
            source.reference()
            for source in sources
        ),
    )

    return CoursePackV01(
        course_id=course_id,
        pack_id=pack_id,
        pack_revision=pack_revision,
        objectives=(objective,),
        sources=tuple(sources),
    )

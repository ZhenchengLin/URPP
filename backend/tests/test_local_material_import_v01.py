"""
URPP 14D-1A: offline local material import tests.

No network, model, database, or filesystem writes.
"""

from hashlib import sha256

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.local_material_import_v01 import (
    MAX_SOURCE_CHARACTERS,
    build_local_material_pack_v01,
    split_material_into_excerpts_v01,
)


def build(
    content=b"LU decomposition: A = LU.",
    **overrides,
):
    arguments = {
        "filename": "my_notes.md",
        "file_bytes": content,
        "course_id": "my-course",
        "objective_id": "my-objective",
        "objective_description": (
            "Explain the contents of my uploaded notes."
        ),
        "allow_local_teaching": True,
    }

    arguments.update(overrides)

    return build_local_material_pack_v01(
        **arguments
    )


def test_markdown_upload_produces_existing_course_pack():
    pack = build(
        b"# My notes\n\nA = LU.\n"
    )

    assert pack.course_id == "my-course"
    assert len(pack.objectives) == 1
    assert len(pack.sources) == 1

    knowledge = resolve_course_knowledge_v01(
        pack=pack,
        course_id="my-course",
        objective_id="my-objective",
        expected_pack_revision=pack.pack_revision,
    )

    assert knowledge.sources == pack.sources

    assert knowledge.sources[0].content == (
        "# My notes\n\nA = LU.\n"
    )


def test_source_provenance_and_digest():
    original = b"Projection is a line integral."

    pack = build(original)

    source = pack.sources[0]

    assert pack.pack_revision == sha256(
        original
    ).hexdigest()

    assert source.content_sha256 == sha256(
        original
    ).hexdigest()

    assert (
        "my_notes.md"
        in source.source_locator
    )

    assert (
        pack.pack_revision
        in source.source_locator
    )


def test_identical_upload_has_identical_pack_identity():
    first = build()
    second = build()

    assert first == second


def test_changed_content_changes_pack_revision():
    first = build(b"First version.")
    second = build(b"Second version.")

    assert first.pack_revision != second.pack_revision
    assert first.pack_id != second.pack_id


def test_multiple_excerpts_keep_document_content():
    content = (
        "A" * MAX_SOURCE_CHARACTERS
        + "B" * 25
    ).encode("utf-8")

    pack = build(content)

    assert len(pack.sources) == 2

    recovered_text = "".join(
        source.content
        for source in pack.sources
    )

    assert recovered_text == content.decode("utf-8")

    assert len(
        pack.objectives[0].source_refs
    ) == 2


def test_overlong_material_is_not_silently_truncated():
    text = (
        "A" * (
            MAX_SOURCE_CHARACTERS * 8 + 1
        )
    )

    with pytest.raises(
        ValueError,
        match="eight-excerpt",
    ):
        split_material_into_excerpts_v01(text)


@pytest.mark.parametrize(
    "filename",
    [
        "../notes.md",
        "/tmp/notes.md",
        r"folder\notes.md",
        "notes.pdf",
        "notes.exe",
    ],
)
def test_unsupported_or_path_filenames_rejected(filename):
    with pytest.raises(ValueError):
        build(filename=filename)


def test_local_teaching_requires_explicit_permission():
    with pytest.raises(PermissionError):
        build(allow_local_teaching=False)


def test_invalid_utf8_is_rejected():
    with pytest.raises(
        ValueError,
        match="UTF-8",
    ):
        build(b"\xff\xfe")


def test_empty_document_is_rejected():
    with pytest.raises(ValueError):
        build(b"  \n  ")


def test_source_digest_detects_tampering():
    pack = build()

    original = pack.sources[0]

    tampered = original.model_copy(
        update={
            "content": "Different content."
        }
    )

    modified_pack = pack.model_copy(
        update={
            "sources": (tampered,)
        }
    )

    with pytest.raises(ValueError):
        resolve_course_knowledge_v01(
            pack=modified_pack,
            course_id=pack.course_id,
            objective_id="my-objective",
            expected_pack_revision=pack.pack_revision,
        )


def test_txt_is_accepted():
    pack = build(
        b"Plain text notes.",
        filename="notes.txt",
    )

    assert pack.sources[0].content == (
        "Plain text notes."
    )

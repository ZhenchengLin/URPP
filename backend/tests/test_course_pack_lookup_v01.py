"""
URPP Implementation 14A-2 tests.

All course content in these tests is synthetic.
An 'approved' fixture field is not an assertion that
a real university has approved or licensed the material.
"""

from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    load_course_pack_v01,
    resolve_course_knowledge_v01,
)
from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


COURSE = "synthetic-course-001"
REVISION = "pack-revision-001"


def make_source(
    source_id="source-001",
    content="Synthetic explanation of a matrix.",
    **overrides,
):
    values = {
        "course_id": COURSE,
        "source_id": source_id,
        "source_revision": "source-revision-001",
        "source_locator": (
            f"synthetic-fixture:{source_id}"
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


def make_objective(
    objective_id="objective-001",
    source=None,
    **overrides,
):
    if source is None:
        source = make_source()

    values = {
        "course_id": COURSE,
        "objective_id": objective_id,
        "description": (
            f"Synthetic learning objective: {objective_id}"
        ),
        "review_status": "approved",
        "source_refs": (source.reference(),),
    }

    values.update(overrides)

    return CourseLearningObjectiveV01(**values)


def make_pack(
    *,
    objectives=None,
    sources=None,
    **overrides,
):
    source = make_source()
    objective = make_objective(source=source)

    values = {
        "course_id": COURSE,
        "pack_id": "synthetic-pack-001",
        "pack_revision": REVISION,
        "objectives": (
            (objective,)
            if objectives is None
            else objectives
        ),
        "sources": (
            (source,)
            if sources is None
            else sources
        ),
    }

    values.update(overrides)

    return CoursePackV01(**values)


def resolve(
    pack,
    *,
    course_id=COURSE,
    objective_id="objective-001",
    expected_pack_revision=REVISION,
):
    return resolve_course_knowledge_v01(
        pack=pack,
        course_id=course_id,
        objective_id=objective_id,
        expected_pack_revision=expected_pack_revision,
    )


def test_resolves_approved_objective_and_source():
    context = resolve(make_pack())

    assert context.course_id == COURSE
    assert context.objective_id == "objective-001"
    assert len(context.sources) == 1

    assert (
        context.sources[0].reference()
        == context.objective.source_refs[0]
    )


def test_local_json_pack_survives_reload(tmp_path):
    original = make_pack()

    file = tmp_path / "synthetic-course-pack.json"

    file.write_text(
        original.model_dump_json(indent=2),
        encoding="utf-8",
    )

    recovered = load_course_pack_v01(file)

    assert recovered == original
    assert resolve(recovered) == resolve(original)


def test_lookup_only_returns_referenced_sources():
    relevant = make_source("source-001")
    unrelated = make_source(
        "source-unrelated",
        visibility="restricted",
        use_permission="not_authorized",
    )

    objective = make_objective(
        source=relevant
    )

    pack = make_pack(
        objectives=(objective,),
        sources=(relevant, unrelated),
    )

    context = resolve(pack)

    assert tuple(
        source.source_id
        for source in context.sources
    ) == ("source-001",)


def test_multiple_referenced_sources_keep_order():
    first = make_source("source-001")
    second = make_source("source-002")

    objective = make_objective(
        source=first,
        source_refs=(
            second.reference(),
            first.reference(),
        ),
    )

    pack = make_pack(
        objectives=(objective,),
        sources=(first, second),
    )

    context = resolve(pack)

    assert tuple(
        source.source_id
        for source in context.sources
    ) == (
        "source-002",
        "source-001",
    )


def test_rejects_wrong_course():
    with pytest.raises(
        ValueError,
        match="does not match Course Pack",
    ):
        resolve(
            make_pack(),
            course_id="another-course",
        )


def test_rejects_stale_pack_revision():
    with pytest.raises(
        ValueError,
        match="Course Pack revision mismatch",
    ):
        resolve(
            make_pack(),
            expected_pack_revision="older-revision",
        )


def test_rejects_unknown_objective():
    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        resolve(
            make_pack(),
            objective_id="unknown-objective",
        )


def test_rejects_missing_required_source():
    existing = make_source("source-001")
    missing = make_source("source-missing")

    objective = make_objective(
        source=missing
    )

    pack = make_pack(
        objectives=(objective,),
        sources=(existing,),
    )

    with pytest.raises(
        ValueError,
        match="Required Course Source was not found",
    ):
        resolve(pack)


def test_rejects_restricted_referenced_source():
    source = make_source(
        visibility="restricted"
    )

    pack = make_pack(
        objectives=(make_objective(source=source),),
        sources=(source,),
    )

    with pytest.raises(
        ValidationError,
        match="not student-visible",
    ):
        resolve(pack)


def test_rejects_unapproved_referenced_source():
    source = make_source(
        review_status="proposed"
    )

    pack = make_pack(
        objectives=(make_objective(source=source),),
        sources=(source,),
    )

    with pytest.raises(
        ValidationError,
        match="Source is not approved",
    ):
        resolve(pack)


def test_rejects_unapproved_objective():
    source = make_source()

    objective = make_objective(
        source=source,
        review_status="proposed",
    )

    pack = make_pack(
        objectives=(objective,),
        sources=(source,),
    )

    with pytest.raises(
        ValidationError,
        match="objective is not approved",
    ):
        resolve(pack)


def test_rejects_source_revision_mismatch():
    first = make_source(
        source_revision="source-revision-001"
    )

    changed = make_source(
        source_revision="source-revision-002"
    )

    objective = make_objective(
        source=first
    )

    pack = make_pack(
        objectives=(objective,),
        sources=(changed,),
    )

    with pytest.raises(
        ValidationError,
        match="reference or revision mismatch",
    ):
        resolve(pack)


def test_rejects_duplicate_source_ids():
    first = make_source("source-001")
    second = make_source(
        "source-001",
        content="A different synthetic excerpt.",
    )

    with pytest.raises(
        ValidationError,
        match="Duplicate source ID",
    ):
        make_pack(sources=(first, second))


def test_rejects_duplicate_objective_ids():
    first = make_objective()
    second = make_objective()

    with pytest.raises(
        ValidationError,
        match="Duplicate objective ID",
    ):
        make_pack(objectives=(first, second))


def test_rejects_cross_course_pack_source():
    source = make_source(
        course_id="another-course"
    )

    with pytest.raises(
        ValidationError,
        match="Source belongs to a different course",
    ):
        make_pack(sources=(source,))


def test_rejects_cross_course_pack_objective():
    objective = make_objective(
        course_id="another-course"
    )

    with pytest.raises(
        ValidationError,
        match="Objective belongs to a different course",
    ):
        make_pack(objectives=(objective,))


def test_rejects_tampered_source_content():
    original = make_source()

    tampered = original.model_copy(
        update={
            "content": "Altered synthetic content."
        }
    )

    # Normal Pack construction must reject altered source
    # content before the lookup operation can begin.
    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        make_pack(
            objectives=(make_objective(source=original),),
            sources=(tampered,),
        )

    # model_copy(update=...) can bypass ordinary Pydantic
    # validation. The lookup must still reject the altered
    # source when constructing its teaching context.
    valid_pack = make_pack(
        objectives=(make_objective(source=original),),
        sources=(original,),
    )

    bypassed_pack = valid_pack.model_copy(
        update={"sources": (tampered,)}
    )

    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        resolve(bypassed_pack)

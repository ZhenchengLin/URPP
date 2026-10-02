"""
URPP Implementation 14A-1 contract tests.

All content below is synthetic test material.
It is not an actual approved university course pack.
"""

from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.services.course_knowledge.models_v01 import (
    CourseKnowledgeContextV01,
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


CONTENT = (
    "A singular value decomposition expresses "
    "a matrix as U Sigma V-transpose."
)


def make_source(**overrides):
    values = {
        "course_id": "test-course-001",
        "source_id": "source-svd-001",
        "source_revision": "revision-001",
        "source_locator": "synthetic-fixture:section-1",
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


def make_objective(source=None, **overrides):
    if source is None:
        source = make_source()

    values = {
        "course_id": "test-course-001",
        "objective_id": "objective-svd-001",
        "description": (
            "Explain the roles of U, Sigma, "
            "and V-transpose."
        ),
        "review_status": "approved",
        "source_refs": (source.reference(),),
    }

    values.update(overrides)

    return CourseLearningObjectiveV01(**values)


def make_context(
    source=None,
    objective=None,
    **overrides,
):
    if source is None:
        source = make_source()

    if objective is None:
        objective = make_objective(source)

    values = {
        "course_id": "test-course-001",
        "objective_id": "objective-svd-001",
        "objective": objective,
        "sources": (source,),
    }

    values.update(overrides)

    return CourseKnowledgeContextV01(**values)


def test_approved_source_and_objective_build_context():
    context = make_context()

    assert context.course_id == "test-course-001"

    assert (
        context.objective_id
        == "objective-svd-001"
    )

    assert context.sources[0].content == CONTENT

    assert (
        context.objective.source_refs[0]
        == context.sources[0].reference()
    )


def test_rejects_objective_from_another_course():
    objective = make_objective(
        course_id="another-course"
    )

    with pytest.raises(
        ValidationError,
        match="different course",
    ):
        make_context(objective=objective)


def test_rejects_wrong_requested_objective():
    with pytest.raises(
        ValidationError,
        match="requested objective",
    ):
        make_context(
            objective_id="another-objective"
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"visibility": "restricted"},
        {"use_permission": "not_authorized"},
        {"review_status": "proposed"},
        {"review_status": "revoked"},
    ],
)
def test_rejects_unavailable_course_sources(
    overrides,
):
    source = make_source(**overrides)

    with pytest.raises(ValidationError):
        make_context(source=source)


def test_rejects_proposed_objective():
    objective = make_objective(
        review_status="proposed"
    )

    with pytest.raises(
        ValidationError,
        match="objective is not approved",
    ):
        make_context(objective=objective)


def test_rejects_cross_course_source():
    source = make_source(
        course_id="another-course"
    )

    with pytest.raises(
        ValidationError,
        match="different course",
    ):
        make_context(source=source)


def test_rejects_source_revision_mismatch():
    original = make_source()

    objective = make_objective(original)

    changed = make_source(
        source_revision="revision-002"
    )

    with pytest.raises(
        ValidationError,
        match="reference or revision mismatch",
    ):
        make_context(
            source=changed,
            objective=objective,
        )


def test_rejects_modified_source_content():
    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        make_source(
            content=CONTENT + " Modified."
        )


def test_rechecks_digest_at_context_boundary():
    source = make_source()

    altered = source.model_copy(
        update={
            "content": CONTENT + " Modified."
        }
    )

    with pytest.raises(
        ValidationError,
        match="content digest mismatch",
    ):
        make_context(source=altered)


def test_rejects_missing_required_source():
    source = make_source()

    with pytest.raises(ValidationError):
        make_context(
            source=source,
            sources=(),
        )


def test_rejects_unreferenced_source():
    source = make_source()

    additional = make_source(
        source_id="source-extra-001"
    )

    with pytest.raises(
        ValidationError,
        match="Unreferenced source",
    ):
        make_context(
            source=source,
            sources=(source, additional),
        )


def test_rejects_duplicate_source_references():
    source = make_source()
    ref = source.reference()

    with pytest.raises(
        ValidationError,
        match="duplicate source IDs",
    ):
        make_objective(
            source,
            source_refs=(ref, ref),
        )


def test_rejects_blank_course_identifier():
    with pytest.raises(ValidationError):
        make_source(course_id="   ")


def test_context_is_immutable_by_normal_assignment():
    context = make_context()

    with pytest.raises(ValidationError):
        context.course_id = "another-course"

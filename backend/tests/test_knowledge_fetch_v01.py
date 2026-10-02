"""14C-3 exact-revision, digest-pinned retrieval; synthetic source fixtures only."""

from dataclasses import replace
from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.knowledge_fetch_v01 import (
    CourseKnowledgeFetcherV01,
    CourseKnowledgeFetchRequestV01,
    InMemoryCoursePackStoreV01,
    course_pack_digest_v01,
)
from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


def source(source_id="s", content="Synthetic LU source.", **changes):
    fields = dict(
        course_id="c", source_id=source_id, source_revision="s-v1",
        source_locator=f"synthetic:{source_id}", content=content,
        content_sha256=sha256(content.encode()).hexdigest(),
        visibility="student_visible", use_permission="approved_for_local_teaching",
        review_status="approved",
    )
    fields.update(changes)
    return CourseSourceV01(**fields)


def pack(*, source_obj=None, objective_source=None, **changes):
    s = source_obj if source_obj is not None else source()
    ref = objective_source if objective_source is not None else s
    obj = CourseLearningObjectiveV01(
        course_id="c", objective_id="o", description="Synthetic objective",
        review_status="approved", source_refs=(ref.reference(),),
    )
    fields = dict(course_id="c", pack_id="p", pack_revision="v1",
                  objectives=(obj,), sources=(s,))
    fields.update(changes)
    return CoursePackV01(**fields)


def request(p):
    return CourseKnowledgeFetchRequestV01(
        course_id=p.course_id, objective_id="o", pack_id=p.pack_id,
        pack_revision=p.pack_revision, expected_pack_sha256=course_pack_digest_v01(p),
    )


def fetch(p, *, requested=None):
    return CourseKnowledgeFetcherV01(InMemoryCoursePackStoreV01((p,))).fetch(
        request(p) if requested is None else requested
    )


def test_fetch_exact_snapshot_returns_only_referenced_source():
    s = source()
    hidden = source("hidden", content="Private synthetic text.", visibility="restricted",
                    use_permission="not_authorized")
    p = pack(source_obj=s, sources=(s, hidden))
    result = fetch(p)
    assert result.pack_sha256 == course_pack_digest_v01(p)
    assert result.pack_id == "p" and result.pack_revision == "v1"
    assert tuple(x.source_id for x in result.knowledge.sources) == ("s",)
    assert result.source_refs == (s.reference(),)
    assert "Private synthetic text." not in str(result)


def test_multiple_versions_are_independently_addressed_and_pinned():
    p1 = pack()
    p2 = pack(source_obj=source(content="Synthetic revised content."), pack_revision="v2")
    f = CourseKnowledgeFetcherV01(InMemoryCoursePackStoreV01((p1, p2)))
    assert f.fetch(request(p1)).pack_sha256 != f.fetch(request(p2)).pack_sha256
    with pytest.raises(LookupError):
        f.fetch(replace(request(p2), pack_revision="v3"))


def test_same_revision_with_modified_text_is_not_accepted_even_with_valid_source_digest():
    p = pack()
    modified = pack(source_obj=source(content="Synthetic changed content."))
    with pytest.raises(ValueError, match="digest mismatch"):
        fetch(modified, requested=request(p))


def test_unknown_course_pack_objective_and_revision_fail_closed():
    p = pack()
    r = request(p)
    for change in (
        {"course_id": "other"}, {"pack_id": "other"},
        {"pack_revision": "other"},
    ):
        with pytest.raises(LookupError):
            fetch(p, requested=replace(r, **change))
    with pytest.raises(ValueError, match="not found"):
        fetch(p, requested=replace(r, objective_id="other"))


def test_duplicate_snapshot_identity_rejected():
    p = pack()
    with pytest.raises(ValueError, match="Duplicate"):
        InMemoryCoursePackStoreV01((p, p))


def test_store_snapshots_not_aliased_to_original_pack():
    p = pack()
    store = InMemoryCoursePackStoreV01((p,))
    corrupted_source = source(content="Altered but invalid digest.")
    corrupted_source = corrupted_source.model_copy(update={"content": "TAMPERED"})
    corrupted_pack = p.model_copy(update={"sources": (corrupted_source,)})
    assert corrupted_pack.sources[0].content == "TAMPERED"
    recovered = store.load_exact(course_id="c", pack_id="p", pack_revision="v1")
    assert recovered == p


def test_rejects_corrupt_content_when_initializing_store():
    p = pack()
    corrupted_source = p.sources[0].model_copy(update={"content": "tampered"})
    corrupted_pack = p.model_copy(update={"sources": (corrupted_source,)})
    with pytest.raises(ValidationError, match="digest mismatch"):
        InMemoryCoursePackStoreV01((corrupted_pack,))


def test_rejects_restricted_referenced_source():
    s = source(visibility="restricted")
    with pytest.raises(ValidationError, match="student-visible"):
        fetch(pack(source_obj=s))


def test_rejects_unapproved_source_and_objective():
    s = source(review_status="revoked")
    with pytest.raises(ValidationError, match="Source is not approved"):
        fetch(pack(source_obj=s))
    p = pack()
    bad_objective = p.objectives[0].model_copy(update={"review_status": "proposed"})
    with pytest.raises(ValidationError, match="objective is not approved"):
        fetch(p.model_copy(update={"objectives": (bad_objective,)}))


def test_missing_and_mismatched_source_revision_fail_closed():
    old = source()
    other = source(content="Different synthetic content.")
    p = pack(source_obj=other, objective_source=old)
    with pytest.raises(ValidationError, match="reference or revision mismatch"):
        fetch(p)
    p2 = pack(source_obj=other, sources=(other,))
    other_ref = source(source_id="missing")
    obj = p2.objectives[0].model_copy(update={"source_refs": (other_ref.reference(),)})
    with pytest.raises(ValueError, match="not found"):
        fetch(p2.model_copy(update={"objectives": (obj,)}))


def test_future_store_wrong_identity_refused():
    p = pack()
    other = pack(pack_id="other")

    class WrongStore:
        def load_exact(self, **_kwargs):
            return other

    with pytest.raises(ValueError, match="wrong snapshot identity"):
        CourseKnowledgeFetcherV01(WrongStore()).fetch(request(p))


def test_future_store_corrupt_digest_refused():
    p = pack()
    bad = p.model_copy(update={"sources": (
        p.sources[0].model_copy(update={"content": "tampered"}),
    )})

    class CorruptStore:
        def load_exact(self, **_kwargs):
            return bad

    with pytest.raises(ValidationError, match="digest mismatch"):
        CourseKnowledgeFetcherV01(CorruptStore()).fetch(request(p))


def test_future_store_wrong_type_refused():
    class InvalidStore:
        def load_exact(self, **_kwargs):
            return "not-a-pack"

    with pytest.raises(TypeError, match="invalid type"):
        CourseKnowledgeFetcherV01(InvalidStore()).fetch(request(pack()))


def test_wrong_request_type_refused():
    with pytest.raises(TypeError, match="Expected CourseKnowledgeFetchRequestV01"):
        CourseKnowledgeFetcherV01(InMemoryCoursePackStoreV01((pack(),))).fetch({})


@pytest.mark.parametrize("change", [
    {"course_id": " "}, {"objective_id": ""}, {"pack_id": ""},
    {"pack_revision": " "}, {"expected_pack_sha256": "BAD"},
])
def test_invalid_request_metadata_refused(change):
    with pytest.raises(ValueError):
        replace(request(pack()), **change)


def test_no_fallback_when_source_not_student_visible_even_if_another_source_is():
    s = source(visibility="restricted")
    public = source("public")
    p = pack(source_obj=s, sources=(s, public))
    with pytest.raises(ValidationError, match="student-visible"):
        fetch(p)

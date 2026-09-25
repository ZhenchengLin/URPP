"""14C-4 local SQLite knowledge storage: synthetic materials ONLY."""

from dataclasses import replace
from hashlib import sha256
import sqlite3

import pytest

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.knowledge_fetch_v01 import (
    CourseKnowledgeFetcherV01,
    CourseKnowledgeFetchRequestV01,
    course_pack_digest_v01,
)
from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)
from app.services.course_knowledge.sqlite_knowledge_store_v01 import (
    SQLiteCoursePackStoreV01,
    initialize_sqlite_knowledge_store_v01,
)


def source(*, sid="s", rev="r1", content="Synthetic content.", **changes):
    fields = dict(
        course_id="synthetic-course", source_id=sid, source_revision=rev,
        source_locator=f"synthetic:{sid}:{rev}", content=content,
        content_sha256=sha256(content.encode()).hexdigest(),
        visibility="student_visible", use_permission="approved_for_local_teaching",
        review_status="approved",
    )
    fields.update(changes)
    return CourseSourceV01(**fields)


def pack(s, *, pid="p", rev="v1", objectives=("o1", "o2"), extras=()):
    return CoursePackV01(
        course_id="synthetic-course", pack_id=pid, pack_revision=rev,
        sources=(s, *extras),
        objectives=tuple(CourseLearningObjectiveV01(
            course_id="synthetic-course", objective_id=name,
            description=f"Synthetic {name}", review_status="approved",
            source_refs=(s.reference(),),
        ) for name in objectives),
    )


def request(p, oid="o1"):
    return CourseKnowledgeFetchRequestV01(
        course_id=p.course_id, pack_id=p.pack_id, pack_revision=p.pack_revision,
        objective_id=oid, expected_pack_sha256=course_pack_digest_v01(p),
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "knowledge.sqlite"
    initialize_sqlite_knowledge_store_v01(path)
    return path


def counts(path):
    with sqlite3.connect(path) as conn:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("course_sources_v01", "course_pack_snapshots_v01",
                                   "course_pack_sources_v01"))


def test_init_is_explicit_and_never_overwrites(tmp_path):
    path = tmp_path / "knowledge.sqlite"
    with pytest.raises(FileNotFoundError):
        SQLiteCoursePackStoreV01(path)
    assert not path.exists()
    initialize_sqlite_knowledge_store_v01(path)
    with pytest.raises(FileExistsError):
        initialize_sqlite_knowledge_store_v01(path)
    assert counts(path) == (0, 0, 0)


def test_disallow_symlink_and_missing_parent(tmp_path):
    real = tmp_path / "knowledge.sqlite"
    initialize_sqlite_knowledge_store_v01(real)
    link = tmp_path / "link.sqlite"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="non-symlink"):
        SQLiteCoursePackStoreV01(link)
    with pytest.raises(ValueError, match="existing directory"):
        initialize_sqlite_knowledge_store_v01(tmp_path / "missing" / "store.sqlite")


def test_publish_and_fetch_after_reopen(db):
    p = pack(source())
    assert SQLiteCoursePackStoreV01(db).publish_exact(p) == course_pack_digest_v01(p)
    reopened = SQLiteCoursePackStoreV01(db)
    for oid in ("o1", "o2"):
        result = CourseKnowledgeFetcherV01(reopened).fetch(request(p, oid))
        assert result.knowledge.objective_id == oid
        assert len(result.knowledge.sources) == 1
        assert result.pack_sha256 == course_pack_digest_v01(p)
    assert counts(db) == (1, 1, 1)


def test_shared_source_row_across_two_pack_snapshots(db):
    s = source()
    first = pack(s, pid="p1")
    second = pack(s, pid="p2")
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(first)
    store.publish_exact(second)
    assert counts(db) == (1, 2, 2)
    assert CourseKnowledgeFetcherV01(store).fetch(request(second)).knowledge.sources == (s,)


def test_republish_same_pack_is_idempotent(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    assert store.publish_exact(p) == store.publish_exact(p)
    assert counts(db) == (1, 1, 1)


def test_same_pack_revision_cannot_be_overwritten(db):
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(pack(source()))
    with pytest.raises(ValueError, match="Immutable Course Pack"):
        store.publish_exact(pack(source(content="Different synthetic content.")))
    assert counts(db) == (1, 1, 1)


def test_same_source_revision_cannot_change_even_across_new_pack_revision(db):
    store = SQLiteCoursePackStoreV01(db)
    original = pack(source())
    store.publish_exact(original)
    with pytest.raises(ValueError, match="Immutable Course Source"):
        store.publish_exact(pack(source(content="Changed synthetic content."), rev="v2"))
    assert counts(db) == (1, 1, 1)
    assert CourseKnowledgeFetcherV01(store).fetch(request(original)).knowledge.sources[0].content == "Synthetic content."


def test_source_revision_and_pack_revision_can_change_together(db):
    store = SQLiteCoursePackStoreV01(db)
    old = pack(source())
    new = pack(source(rev="r2", content="Synthetic revision two."), rev="v2")
    store.publish_exact(old)
    store.publish_exact(new)
    assert counts(db) == (2, 2, 2)
    assert CourseKnowledgeFetcherV01(store).fetch(request(old)).knowledge.sources[0].source_revision == "r1"
    assert CourseKnowledgeFetcherV01(store).fetch(request(new)).knowledge.sources[0].source_revision == "r2"


def test_missing_revision_never_falls_back_to_latest(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with pytest.raises(LookupError):
        CourseKnowledgeFetcherV01(store).fetch(replace(request(p), pack_revision="v2"))


def test_fetcher_rejects_wrong_pack_digest(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with pytest.raises(ValueError, match="digest mismatch"):
        CourseKnowledgeFetcherV01(store).fetch(replace(request(p), expected_pack_sha256="0" * 64))


def test_unreferenced_restricted_source_is_not_fetched(db):
    s = source()
    hidden = source(sid="hidden", content="Synthetic restricted fixture", visibility="restricted",
                    use_permission="not_authorized")
    p = pack(s, extras=(hidden,))
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    result = CourseKnowledgeFetcherV01(store).fetch(request(p))
    assert result.knowledge.sources == (s,)
    assert counts(db) == (2, 1, 2)


def test_referenced_restricted_source_rejected_at_fetch(db):
    s = source(visibility="restricted")
    p = pack(s)
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with pytest.raises(ValueError, match="student-visible"):
        CourseKnowledgeFetcherV01(store).fetch(request(p))


def test_mutated_source_json_detected_before_fetch(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE course_sources_v01 SET source_json=?", ('{"content":"TAMPERED"}',))
    with pytest.raises(ValueError):
        CourseKnowledgeFetcherV01(store).fetch(request(p))


def test_removed_source_link_fails_closed(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM course_pack_sources_v01")
    with pytest.raises(ValueError):
        CourseKnowledgeFetcherV01(store).fetch(request(p))


def test_removed_source_row_fails_closed_even_if_fk_bypassed(db):
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DELETE FROM course_sources_v01")
    with pytest.raises(ValueError, match="Missing or mismatched"):
        CourseKnowledgeFetcherV01(store).fetch(request(p))


def test_invalid_pack_rejected_without_partial_writes(db):
    p = pack(source())
    invalid_s = p.sources[0].model_copy(update={"content": "tampered"})
    invalid = p.model_copy(update={"sources": (invalid_s,)})
    with pytest.raises(ValueError, match="digest mismatch"):
        SQLiteCoursePackStoreV01(db).publish_exact(invalid)
    assert counts(db) == (0, 0, 0)


def test_store_cannot_be_used_as_authentication_proof(db):
    # This store only enforces supplied metadata. Callers must authorize the
    # source and publisher at a separate trusted boundary in production.
    p = pack(source())
    store = SQLiteCoursePackStoreV01(db)
    store.publish_exact(p)
    assert CourseKnowledgeFetcherV01(store).fetch(request(p)).knowledge.sources[0] == p.sources[0]

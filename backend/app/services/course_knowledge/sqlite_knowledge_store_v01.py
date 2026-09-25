"""14C-4: opt-in, local SQLite Course Pack snapshots with shared source rows.

Local persistence adapter for CoursePackStorePortV01, not a hosted central
service or an authentication/licensing authority. No LLM, student, mastery,
or presentation pathways. Only explicit init/publish write; load is read-only.
"""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.knowledge_fetch_v01 import (
    canonical_pack_bytes_v01,
    course_pack_digest_v01,
)


_SCHEMA = """
CREATE TABLE course_sources_v01 (
  course_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  source_json TEXT NOT NULL,
  PRIMARY KEY (course_id, source_id, source_revision)
);
CREATE TABLE course_pack_snapshots_v01 (
  course_id TEXT NOT NULL,
  pack_id TEXT NOT NULL,
  pack_revision TEXT NOT NULL,
  pack_sha256 TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  PRIMARY KEY (course_id, pack_id, pack_revision)
);
CREATE TABLE course_pack_sources_v01 (
  course_id TEXT NOT NULL,
  pack_id TEXT NOT NULL,
  pack_revision TEXT NOT NULL,
  position INTEGER NOT NULL CHECK(position >= 0),
  source_id TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  PRIMARY KEY (course_id, pack_id, pack_revision, position),
  UNIQUE (course_id, pack_id, pack_revision, source_id),
  FOREIGN KEY (course_id, pack_id, pack_revision)
    REFERENCES course_pack_snapshots_v01(course_id, pack_id, pack_revision),
  FOREIGN KEY (course_id, source_id, source_revision)
    REFERENCES course_sources_v01(course_id, source_id, source_revision)
);
"""


def _path(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.is_symlink() or not path.parent.is_dir() or not path.name.endswith(".sqlite"):
        raise ValueError("Knowledge store must be a non-symlink .sqlite path in an existing directory.")
    return path


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    # mode=ro prevents an accidental read from silently creating a database.
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError("Local Course Knowledge store does not exist.")
    conn = sqlite3.connect(path.as_uri() + ("?mode=ro" if read_only else "?mode=rw"),
                           uri=True, timeout=5.0)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite foreign keys must be enabled.")
        return conn
    except BaseException:
        conn.close()
        raise


def initialize_sqlite_knowledge_store_v01(path: str | Path) -> None:
    """Explicit create-once init; never overwrites an existing local file."""
    location = _path(path)
    descriptor = os.open(location, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    conn = _connect(location, read_only=False)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


class SQLiteCoursePackStoreV01:
    """Immutable exact pack snapshots; deduplicate sources by pinned revision.

    Sources shared across pack snapshots occupy one source row. Updating content
    or review/visibility metadata requires a new source revision and a new pack
    revision. CourseKnowledgeFetcherV01 still performs exact digest, scope and
    use-permission checks on all retrieved teaching material.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = _path(path)
        if not self._path.is_file():
            raise FileNotFoundError("Knowledge store is not initialized.")

    def publish_exact(self, pack: CoursePackV01) -> str:
        """Atomically add one explicit snapshot or accept identical re-publish."""
        # Canonical validation happens before any SQLite writes.
        validated = CoursePackV01.model_validate_json(canonical_pack_bytes_v01(pack))
        digest = course_pack_digest_v01(validated)
        key = (validated.course_id, validated.pack_id, validated.pack_revision)
        manifest = validated.model_dump(mode="json", exclude={"sources"})
        manifest_text = _json(manifest)

        conn = _connect(self._path, read_only=False)
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT pack_sha256, manifest_json FROM course_pack_snapshots_v01 "
                "WHERE course_id=? AND pack_id=? AND pack_revision=?", key,
            ).fetchone()
            if existing is not None:
                if existing != (digest, manifest_text):
                    raise ValueError("Immutable Course Pack snapshot identity already has different content.")
                # Verify existing snapshot and its source rows before idempotent success.
                if self._load_connection(conn, key) != validated:
                    raise ValueError("Existing Course Pack snapshot does not match its stored content.")
                conn.commit()
                return digest

            for source in validated.sources:
                source_key = (source.course_id, source.source_id, source.source_revision)
                source_text = _json(source.model_dump(mode="json"))
                existing_source = conn.execute(
                    "SELECT content_sha256, source_json FROM course_sources_v01 "
                    "WHERE course_id=? AND source_id=? AND source_revision=?", source_key,
                ).fetchone()
                if existing_source is not None:
                    if existing_source != (source.content_sha256, source_text):
                        raise ValueError("Immutable Course Source revision already has different content or metadata.")
                else:
                    conn.execute(
                        "INSERT INTO course_sources_v01 "
                        "(course_id, source_id, source_revision, content_sha256, source_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (*source_key, source.content_sha256, source_text),
                    )

            conn.execute(
                "INSERT INTO course_pack_snapshots_v01 "
                "(course_id, pack_id, pack_revision, pack_sha256, manifest_json) "
                "VALUES (?, ?, ?, ?, ?)", (*key, digest, manifest_text),
            )
            for position, source in enumerate(validated.sources):
                conn.execute(
                    "INSERT INTO course_pack_sources_v01 "
                    "(course_id, pack_id, pack_revision, position, source_id, "
                    "source_revision, content_sha256) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (*key, position, source.source_id, source.source_revision,
                     source.content_sha256),
                )
            conn.commit()
            return digest
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _load_connection(conn: sqlite3.Connection, key: tuple[str, str, str]) -> CoursePackV01:
        row = conn.execute(
            "SELECT pack_sha256, manifest_json FROM course_pack_snapshots_v01 "
            "WHERE course_id=? AND pack_id=? AND pack_revision=?", key,
        ).fetchone()
        if row is None:
            raise LookupError("Exact Course Pack snapshot not found.")
        stored_digest, manifest_json = row
        manifest = json.loads(manifest_json)
        if not isinstance(manifest, dict) or "sources" in manifest:
            raise ValueError("Invalid stored Course Pack manifest.")
        if (manifest.get("course_id"), manifest.get("pack_id"),
            manifest.get("pack_revision")) != key:
            raise ValueError("Stored Course Pack manifest identity mismatch.")

        links = conn.execute(
            "SELECT position, source_id, source_revision, content_sha256 "
            "FROM course_pack_sources_v01 "
            "WHERE course_id=? AND pack_id=? AND pack_revision=? "
            "ORDER BY position", key,
        ).fetchall()
        sources: list[dict[str, Any]] = []
        for expected_position, (position, source_id, source_revision, linked_digest) in enumerate(links):
            if position != expected_position:
                raise ValueError("Course Pack source positions are not contiguous.")
            stored = conn.execute(
                "SELECT content_sha256, source_json FROM course_sources_v01 "
                "WHERE course_id=? AND source_id=? AND source_revision=?",
                (key[0], source_id, source_revision),
            ).fetchone()
            if stored is None or stored[0] != linked_digest:
                raise ValueError("Missing or mismatched exact Course Source revision.")
            source_data = json.loads(stored[1])
            if (source_data.get("course_id"), source_data.get("source_id"),
                source_data.get("source_revision"), source_data.get("content_sha256")) != (
                    key[0], source_id, source_revision, linked_digest):
                raise ValueError("Stored Course Source identity or digest mismatch.")
            sources.append(source_data)
        try:
            pack = CoursePackV01.model_validate({**manifest, "sources": sources})
        except (TypeError, ValueError) as exc:
            raise ValueError("Stored Course Pack failed validation.") from exc
        if course_pack_digest_v01(pack) != stored_digest:
            raise ValueError("Stored Course Pack digest mismatch.")
        return pack

    def load_exact(self, *, course_id: str, pack_id: str,
                   pack_revision: str) -> CoursePackV01:
        conn = _connect(self._path, read_only=True)
        try:
            # An explicit read transaction gives a consistent snapshot if publish runs concurrently.
            conn.execute("BEGIN")
            pack = self._load_connection(conn, (course_id, pack_id, pack_revision))
            conn.rollback()
            return pack
        finally:
            conn.close()

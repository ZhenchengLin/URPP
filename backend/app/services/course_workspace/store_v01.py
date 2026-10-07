"""SQLite persistence for the Course Workspace (docs/33).

Attempts and events are append-only. Outline revisions, lessons, and items are
written once and never updated. Local single-user store; not authentication.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_V01 = """
CREATE TABLE IF NOT EXISTS cw_courses_v01 (
    course_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cw_documents_v01 (
    document_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES cw_courses_v01(course_id),
    filename TEXT NOT NULL,
    original_sha256 TEXT NOT NULL,
    pack_sha256 TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    pages_without_text TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (course_id, original_sha256)
);
CREATE TABLE IF NOT EXISTS cw_outlines_v01 (
    course_id TEXT NOT NULL REFERENCES cw_courses_v01(course_id),
    revision INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (course_id, revision)
);
CREATE TABLE IF NOT EXISTS cw_lessons_v01 (
    course_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (course_id, revision, topic_id),
    FOREIGN KEY (course_id, revision) REFERENCES cw_outlines_v01(course_id, revision)
);
CREATE TABLE IF NOT EXISTS cw_items_v01 (
    item_id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (course_id, revision) REFERENCES cw_outlines_v01(course_id, revision)
);
CREATE TABLE IF NOT EXISTS cw_events_v01 (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    item_id TEXT REFERENCES cw_items_v01(item_id),
    kind TEXT NOT NULL CHECK (kind IN ('lesson_opened', 'hint_shown', 'solution_shown')),
    occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cw_attempts_v01 (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL REFERENCES cw_items_v01(item_id),
    course_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
    hint_shown INTEGER NOT NULL CHECK (hint_shown IN (0, 1)),
    solution_shown INTEGER NOT NULL CHECK (solution_shown IN (0, 1)),
    submitted_at TEXT NOT NULL
);
"""


def now_utc_v01() -> str:
    return datetime.now(timezone.utc).isoformat()


class CourseWorkspaceStoreV01:
    def __init__(self, database_path: Path) -> None:
        path = Path(database_path)
        if path.is_symlink():
            raise ValueError("Course workspace database cannot be a symlink.")
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA_V01)
        path.chmod(0o600)

    def close(self) -> None:
        self._connection.close()

    def _write(self, sql: str, params: tuple) -> int:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            return cursor.lastrowid

    def _rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, params)]

    # Courses and documents -------------------------------------------------

    def add_course(self, course_id: str, title: str) -> None:
        self._write(
            "INSERT INTO cw_courses_v01 VALUES (?, ?, ?)",
            (course_id, title, now_utc_v01()),
        )

    def list_courses(self) -> list[dict]:
        return self._rows("SELECT * FROM cw_courses_v01 ORDER BY created_at")

    def get_course(self, course_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM cw_courses_v01 WHERE course_id = ?", (course_id,))
        return rows[0] if rows else None

    def add_document(self, record: dict) -> None:
        self._write(
            "INSERT INTO cw_documents_v01 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["document_id"], record["course_id"], record["filename"],
                record["original_sha256"], record["pack_sha256"],
                record["source_count"], json.dumps(record["pages_without_text"]),
                now_utc_v01(),
            ),
        )

    def list_documents(self, course_id: str) -> list[dict]:
        rows = self._rows(
            "SELECT * FROM cw_documents_v01 WHERE course_id = ? ORDER BY added_at",
            (course_id,),
        )
        for row in rows:
            row["pages_without_text"] = json.loads(row["pages_without_text"])
        return rows

    # Outlines, lessons, items ---------------------------------------------

    def add_outline(self, course_id: str, payload: dict) -> int:
        with self._lock:
            current = self._connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM cw_outlines_v01 WHERE course_id = ?",
                (course_id,),
            ).fetchone()[0]
            revision = current + 1
            self._connection.execute(
                "INSERT INTO cw_outlines_v01 VALUES (?, ?, ?, ?)",
                (course_id, revision, json.dumps({**payload, "revision": revision}),
                 now_utc_v01()),
            )
        return revision

    def latest_outline(self, course_id: str) -> dict | None:
        rows = self._rows(
            "SELECT payload FROM cw_outlines_v01 WHERE course_id = ? "
            "ORDER BY revision DESC LIMIT 1",
            (course_id,),
        )
        return json.loads(rows[0]["payload"]) if rows else None

    def get_lesson(self, course_id: str, revision: int, topic_id: str) -> dict | None:
        rows = self._rows(
            "SELECT payload FROM cw_lessons_v01 WHERE course_id = ? AND revision = ? "
            "AND topic_id = ?",
            (course_id, revision, topic_id),
        )
        return json.loads(rows[0]["payload"]) if rows else None

    def add_lesson(self, course_id: str, revision: int, topic_id: str, payload: dict) -> None:
        self._write(
            "INSERT INTO cw_lessons_v01 VALUES (?, ?, ?, ?, ?)",
            (course_id, revision, topic_id, json.dumps(payload), now_utc_v01()),
        )

    def add_item(self, course_id: str, revision: int, topic_id: str, item: dict) -> None:
        self._write(
            "INSERT INTO cw_items_v01 VALUES (?, ?, ?, ?, ?, ?)",
            (item["item_id"], course_id, revision, topic_id, json.dumps(item),
             now_utc_v01()),
        )

    def list_items(self, course_id: str, revision: int, topic_id: str) -> list[dict]:
        rows = self._rows(
            "SELECT payload FROM cw_items_v01 WHERE course_id = ? AND revision = ? "
            "AND topic_id = ? ORDER BY created_at, item_id",
            (course_id, revision, topic_id),
        )
        return [json.loads(row["payload"]) for row in rows]

    def get_item(self, item_id: str) -> dict | None:
        rows = self._rows(
            "SELECT course_id, revision, topic_id, payload FROM cw_items_v01 "
            "WHERE item_id = ?",
            (item_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return {**json.loads(row["payload"]), "course_id": row["course_id"],
                "revision": row["revision"], "topic_id": row["topic_id"]}

    # Observations ----------------------------------------------------------

    def add_event(self, course_id: str, revision: int, topic_id: str,
                  kind: str, item_id: str | None = None) -> None:
        self._write(
            "INSERT INTO cw_events_v01 (course_id, revision, topic_id, item_id, kind, "
            "occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (course_id, revision, topic_id, item_id, kind, now_utc_v01()),
        )

    def events(self, course_id: str, revision: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM cw_events_v01 WHERE course_id = ? AND revision = ? "
            "ORDER BY event_id",
            (course_id, revision),
        )

    def add_attempt(self, item: dict, answer_text: str, correct: bool,
                    hint_shown: bool, solution_shown: bool) -> int:
        return self._write(
            "INSERT INTO cw_attempts_v01 (item_id, course_id, revision, topic_id, "
            "answer_text, correct, hint_shown, solution_shown, submitted_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item["item_id"], item["course_id"], item["revision"], item["topic_id"],
             answer_text, int(correct), int(hint_shown), int(solution_shown),
             now_utc_v01()),
        )

    def attempts(self, course_id: str, revision: int) -> list[dict]:
        return self._rows(
            "SELECT * FROM cw_attempts_v01 WHERE course_id = ? AND revision = ? "
            "ORDER BY attempt_id",
            (course_id, revision),
        )

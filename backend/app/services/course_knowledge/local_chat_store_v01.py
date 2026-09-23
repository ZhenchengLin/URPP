"""
URPP 14C-7D1: developer-only durable local chat sessions.

SQLite stores complete Student/Professor message pairs and
binds each session to one local profile, course, objective,
and exact Course Pack revision and digest.

This component is not authentication or a public Chat API.

It does not call a model, authorize source access, verify
generated content, create assessment evidence, update mastery,
or claim student-facing delivery.
"""

from __future__ import annotations

import os
import secrets
import sqlite3

from dataclasses import dataclass
from pathlib import Path

from app.services.course_knowledge.local_chat_context_v01 import (
    ConversationMessageV01,
    LocalChatContextV01,
)


@dataclass(frozen=True)
class LocalChatSnapshotV01:
    session_id: str
    local_profile_id: str
    course_id: str
    objective_id: str
    pack_id: str
    pack_revision: str
    pack_sha256: str
    messages: tuple[ConversationMessageV01, ...]
    answer_statuses: tuple[str, ...] = ()  # Per Professor turn; legacy is unclassified.

    @property
    def turn_count(self) -> int:
        return len(self.messages) // 2


class LocalChatStoreV01:
    """
    Developer-only SQLite chat store.

    One turn consists of exactly one Student message followed
    by exactly one Professor message. A failed write cannot
    leave a half-completed turn.
    """

    ANSWER_STATUSES = frozenset({
        "course_grounded", "insufficient_evidence", "general_knowledge",
    })

    CREATE_SCHEMA = """
    CREATE TABLE local_chat_sessions_v01 (
        session_id TEXT PRIMARY KEY,
        local_profile_id TEXT NOT NULL,
        course_id TEXT NOT NULL,
        objective_id TEXT NOT NULL,
        pack_id TEXT NOT NULL,
        pack_revision TEXT NOT NULL,
        pack_sha256 TEXT NOT NULL
    );

    CREATE TABLE local_chat_messages_v01 (
        session_id TEXT NOT NULL,
        position INTEGER NOT NULL CHECK (position >= 0),
        role TEXT NOT NULL
            CHECK (role IN ('student', 'professor')),
        text TEXT NOT NULL
            CHECK (length(text) BETWEEN 1 AND 1500),
        answer_status TEXT CHECK (
            answer_status IS NULL OR (
                role = 'professor' AND answer_status IN (
                    'course_grounded', 'insufficient_evidence', 'general_knowledge'
                )
            )
        ),

        PRIMARY KEY (session_id, position),

        FOREIGN KEY (session_id)
            REFERENCES local_chat_sessions_v01(session_id)
    );
    """

    def __init__(self, database_path: Path) -> None:
        self._path = Path(database_path).expanduser().absolute()

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if (
            type(value) is not str
            or not value.strip()
            or len(value) > 128
        ):
            raise ValueError(
                f"{name} must contain 1–128 nonblank characters."
            )

        return value

    @staticmethod
    def _digest(value: str) -> str:
        if (
            type(value) is not str
            or len(value) != 64
            or any(character not in "0123456789abcdef"
                   for character in value)
        ):
            raise ValueError(
                "Pack SHA-256 must be 64 lowercase hex characters."
            )

        return value

    @classmethod
    def create_new(cls, database_path: Path):
        """
        Create a NEW database without replacing an existing file.

        The caller must select an appropriate local-only path.
        """

        path = Path(database_path).expanduser().absolute()

        if not path.parent.is_dir():
            raise ValueError(
                "Database parent directory does not exist."
            )

        if path.exists() or path.is_symlink():
            raise FileExistsError(
                "Refusing to replace an existing database."
            )

        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )

        os.close(descriptor)

        store = cls(path)

        with store._connect() as connection:
            connection.executescript(cls.CREATE_SCHEMA)

        return store

    @classmethod
    def open_existing(cls, database_path: Path):
        """Open an explicitly selected existing local database."""

        path = Path(database_path).expanduser().absolute()

        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(
                "Existing local Chat database was not found."
            )

        store = cls(path)

        with store._connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table'"
                )
            }

        required = {
            "local_chat_sessions_v01",
            "local_chat_messages_v01",
        }

        if not required.issubset(tables):
            raise ValueError(
                "Database does not contain the expected Chat schema."
            )

        # One atomic SQLite schema change; old rows retain NULL metadata.
        # Do not infer provenance from historical answer text or prefixes.
        with store._connect() as connection:
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(local_chat_messages_v01)"
                )
            }
            if "answer_status" not in columns:
                connection.execute(
                    "ALTER TABLE local_chat_messages_v01 "
                    "ADD COLUMN answer_status TEXT CHECK ("
                    "answer_status IS NULL OR ("
                    "role = 'professor' AND answer_status IN ("
                    "'course_grounded', 'insufficient_evidence', 'general_knowledge'"
                    ")))"
                )

        return store

    def _connect(self):
        # mode=rw prevents SQLite from silently creating a new
        # database when an existing session should be recovered.
        connection = sqlite3.connect(
            self._path.as_uri() + "?mode=rw",
            uri=True,
            timeout=10,
            isolation_level=None,
        )

        connection.execute("PRAGMA foreign_keys=ON")

        return connection

    def create_session(
        self,
        *,
        local_profile_id: str,
        course_id: str,
        objective_id: str,
        pack_id: str,
        pack_revision: str,
        pack_sha256: str,
    ) -> str:
        """Create one explicitly version-bound local session."""

        values = (
            self._identifier(
                local_profile_id, "local_profile_id"
            ),
            self._identifier(course_id, "course_id"),
            self._identifier(objective_id, "objective_id"),
            self._identifier(pack_id, "pack_id"),
            self._identifier(pack_revision, "pack_revision"),
            self._digest(pack_sha256),
        )

        session_id = secrets.token_urlsafe(24)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            try:
                connection.execute(
                    """
                    INSERT INTO local_chat_sessions_v01 (
                        session_id,
                        local_profile_id,
                        course_id,
                        objective_id,
                        pack_id,
                        pack_revision,
                        pack_sha256
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, *values),
                )

                connection.commit()

            except Exception:
                connection.rollback()
                raise

        return session_id

    @staticmethod
    def _load_bound_snapshot(
        connection,
        *,
        session_id: str,
        local_profile_id: str,
        course_id: str,
        objective_id: str,
        pack_id: str,
        pack_revision: str,
        pack_sha256: str,
    ) -> LocalChatSnapshotV01:

        row = connection.execute(
            """
            SELECT
                session_id,
                local_profile_id,
                course_id,
                objective_id,
                pack_id,
                pack_revision,
                pack_sha256
            FROM local_chat_sessions_v01
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

        expected = (
            session_id,
            local_profile_id,
            course_id,
            objective_id,
            pack_id,
            pack_revision,
            pack_sha256,
        )

        if row is None or tuple(row) != expected:
            raise LookupError(
                "Exact local Chat Session binding not found."
            )

        rows = connection.execute(
            """
            SELECT position, role, text, answer_status
            FROM local_chat_messages_v01
            WHERE session_id = ?
            ORDER BY position
            """,
            (session_id,),
        ).fetchall()

        messages = []
        answer_statuses = []

        for expected_position, row in enumerate(rows):
            position, role, text, answer_status = row

            expected_role = (
                "student"
                if expected_position % 2 == 0
                else "professor"
            )

            if (
                position != expected_position
                or role != expected_role
            ):
                raise ValueError(
                    "Stored Chat message sequence is invalid."
                )

            if role == "professor":
                if (answer_status is not None
                        and answer_status not in LocalChatStoreV01.ANSWER_STATUSES):
                    raise ValueError("Stored Professor answer status is invalid.")
                answer_statuses.append(answer_status or "legacy_unclassified")
            elif answer_status is not None:
                raise ValueError("Student message cannot have answer status.")

            messages.append(
                ConversationMessageV01(
                    role=role,
                    text=text,
                )
            )

        if len(messages) % 2:
            raise ValueError(
                "Stored Chat contains an incomplete turn."
            )

        return LocalChatSnapshotV01(
            session_id=session_id,
            local_profile_id=local_profile_id,
            course_id=course_id,
            objective_id=objective_id,
            pack_id=pack_id,
            pack_revision=pack_revision,
            pack_sha256=pack_sha256,
            messages=tuple(messages),
            answer_statuses=tuple(answer_statuses),
        )

    def load_session(
        self,
        *,
        session_id: str,
        local_profile_id: str,
        course_id: str,
        objective_id: str,
        pack_id: str,
        pack_revision: str,
        pack_sha256: str,
    ) -> LocalChatSnapshotV01:
        """
        Recover only an exact caller-supplied Session binding.

        These fields enforce logical scope consistency.
        They do not prove the caller's identity.
        """

        binding = {
            "session_id": self._identifier(
                session_id, "session_id"
            ),
            "local_profile_id": self._identifier(
                local_profile_id, "local_profile_id"
            ),
            "course_id": self._identifier(
                course_id, "course_id"
            ),
            "objective_id": self._identifier(
                objective_id, "objective_id"
            ),
            "pack_id": self._identifier(
                pack_id, "pack_id"
            ),
            "pack_revision": self._identifier(
                pack_revision, "pack_revision"
            ),
            "pack_sha256": self._digest(pack_sha256),
        }

        with self._connect() as connection:
            return self._load_bound_snapshot(
                connection,
                **binding,
            )

    def append_exchange(
        self,
        *,
        expected_message_count: int,
        student_text: str,
        professor_text: str,
        answer_status: str | None = None,
        **binding,
    ) -> LocalChatSnapshotV01:
        """
        Atomically persist one complete generated exchange.

        expected_message_count prevents a stale caller from
        silently appending against a newer conversation.

        This method stores text supplied by its caller.
        It does not independently validate whether the
        Professor content was mathematically correct.
        """

        if (
            type(expected_message_count) is not int
            or expected_message_count < 0
            or expected_message_count % 2
        ):
            raise ValueError(
                "Expected message count must be a nonnegative "
                "even integer."
            )

        if answer_status is not None and (
            type(answer_status) is not str
            or answer_status not in self.ANSWER_STATUSES
        ):
            raise ValueError("Invalid Professor answer status.")

        student = ConversationMessageV01(
            role="student",
            text=student_text,
        )

        professor = ConversationMessageV01(
            role="professor",
            text=professor_text,
        )

        # Validate all binding fields before any write.
        session_id = self._identifier(
            binding["session_id"],
            "session_id",
        )

        profile_id = self._identifier(
            binding["local_profile_id"],
            "local_profile_id",
        )

        course_id = self._identifier(
            binding["course_id"],
            "course_id",
        )

        objective_id = self._identifier(
            binding["objective_id"],
            "objective_id",
        )

        pack_id = self._identifier(
            binding["pack_id"],
            "pack_id",
        )

        pack_revision = self._identifier(
            binding["pack_revision"],
            "pack_revision",
        )

        pack_sha256 = self._digest(
            binding["pack_sha256"]
        )

        exact_binding = {
            "session_id": session_id,
            "local_profile_id": profile_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "pack_id": pack_id,
            "pack_revision": pack_revision,
            "pack_sha256": pack_sha256,
        }

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            try:
                before = self._load_bound_snapshot(
                    connection,
                    **exact_binding,
                )

                if (
                    len(before.messages)
                    != expected_message_count
                ):
                    raise ValueError(
                        "Chat Session advanced since the "
                        "caller loaded its history."
                    )

                connection.execute(
                    """
                    INSERT INTO local_chat_messages_v01
                        (session_id, position, role, text)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        expected_message_count,
                        "student",
                        student.text,
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO local_chat_messages_v01
                        (session_id, position, role, text, answer_status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        expected_message_count + 1,
                        "professor",
                        professor.text,
                        answer_status,
                    ),
                )

                after = self._load_bound_snapshot(
                    connection,
                    **exact_binding,
                )

                connection.commit()

                return after

            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def conversation_context(
        snapshot: LocalChatSnapshotV01,
        *,
        current_student_message: str,
    ) -> LocalChatContextV01:
        """
        Build one bounded model-input window from stored history.

        Complete older exchanges remain in SQLite even when
        excluded from the current model context.
        """

        if not isinstance(snapshot, LocalChatSnapshotV01):
            raise TypeError(
                "Expected LocalChatSnapshotV01."
            )

        if len(snapshot.messages) % 2:
            raise ValueError(
                "Cannot build context from incomplete history."
            )

        current = ConversationMessageV01(
            role="student",
            text=current_student_message,
        )

        selected = []
        total = len(current.text)

        pairs = [
            snapshot.messages[index:index + 2]
            for index in range(
                0,
                len(snapshot.messages),
                2,
            )
        ]

        # Select recent complete exchanges without splitting
        # a Student question from its Professor response.
        for pair in reversed(pairs):
            pair_size = sum(
                len(message.text)
                for message in pair
            )

            if (
                len(selected) + 2 > 6
                or total + pair_size > 6000
            ):
                break

            selected[0:0] = pair
            total += pair_size

        return LocalChatContextV01(
            course_id=snapshot.course_id,
            objective_id=snapshot.objective_id,
            current_student_message=current.text,
            history=tuple(selected),
        )

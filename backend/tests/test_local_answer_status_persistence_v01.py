"""14D-3B2B: durable answer status and legacy-safe SQLite migration (offline)."""
import base64
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.local_learning_api_v01 import create_local_learning_api_v01
from app.services.course_knowledge.local_chat_store_v01 import LocalChatStoreV01
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01


class CourseGateway:
    def __init__(self):
        self.calls = 0

    def generate_structured(self, *, prompt_name, payload):
        self.calls += 1
        if self.calls == 2:
            return {"content": "Do not save this assertion", "source_ids": [],
                    "answer_status": "insufficient_evidence"}
        return {"content": "Projection is a line integral.",
                "source_ids": [payload["sources"][0]["source_id"]],
                "answer_status": "course_grounded"}


class GeneralGateway:
    def generate_general(self, *, context):
        assert context.history == ()
        return "2"


def test_all_statuses_survive_real_api_and_reopen(tmp_path):
    course = CourseGateway()
    root = tmp_path / "private"

    def client():
        workspace = LocalLearningWorkspaceV01(
            data_root=root, gateway_factory=lambda: course,
            general_gateway_factory=GeneralGateway,
        )
        return TestClient(create_local_learning_api_v01(
            workspace=workspace, allow_test_host=True,
        ))

    http = client()
    uploaded = http.post("/api/upload", headers={"X-URPP-Local-Request": "1"}, json={
        "filename": "ct.md", "file_base64": base64.b64encode(
            b"# CT notes\nProjection is a line integral."
        ).decode(), "objective_description": "Explain CT projection.",
        "allow_local_teaching": True,
    })
    assert uploaded.status_code == 200, uploaded.text
    session = uploaded.json()
    response = None
    for count, mode, question in (
        (0, "course", "What is projection?"),
        (2, "course", "What is 1 + 1?"),
        (4, "general", "What is 1 + 1?"),
    ):
        response = http.post("/api/chat", headers={"X-URPP-Local-Request": "1"}, json={
            "session_id": session["session_id"],
            "pack_sha256": session["pack_sha256"],
            "student_text": question,
            "expected_message_count": count, "mode": mode,
        })
        assert response.status_code == 200, response.text
    assert course.calls == 2
    messages = response.json()["messages"]
    assert [entry["answer_status"] for entry in messages if entry["role"] == "professor"] == [
        "course_grounded", "insufficient_evidence", "general_knowledge",
    ]
    assert all("answer_status" not in entry for entry in messages if entry["role"] == "student")
    resumed = client().get(
        "/api/session/" + session["session_id"],
        params={"pack_sha256": session["pack_sha256"]},
    )
    assert resumed.status_code == 200
    assert resumed.json()["messages"] == messages


def test_old_schema_migrates_without_guessing_from_text(tmp_path):
    path = tmp_path / "old.sqlite3"
    # An actual pre-3B2B schema: no answer_status column.
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE local_chat_sessions_v01 (
                session_id TEXT PRIMARY KEY, local_profile_id TEXT NOT NULL,
                course_id TEXT NOT NULL, objective_id TEXT NOT NULL,
                pack_id TEXT NOT NULL, pack_revision TEXT NOT NULL,
                pack_sha256 TEXT NOT NULL
            );
            CREATE TABLE local_chat_messages_v01 (
                session_id TEXT NOT NULL, position INTEGER NOT NULL,
                role TEXT NOT NULL, text TEXT NOT NULL,
                PRIMARY KEY(session_id,position)
            );
        """)
        connection.execute("INSERT INTO local_chat_sessions_v01 VALUES (?,?,?,?,?,?,?)",
                           ("old-session", "profile", "course", "objective", "pack", "v1", "a" * 64))
        connection.execute("INSERT INTO local_chat_messages_v01 VALUES (?,?,?,?)",
                           ("old-session", 0, "student", "1 + 1?"))
        connection.execute("INSERT INTO local_chat_messages_v01 VALUES (?,?,?,?)",
                           ("old-session", 1, "professor",
                            "[GENERAL KNOWLEDGE — not from uploaded material]\\n2"))
    binding = dict(session_id="old-session", local_profile_id="profile",
                   course_id="course", objective_id="objective", pack_id="pack",
                   pack_revision="v1", pack_sha256="a" * 64)
    store = LocalChatStoreV01.open_existing(path)
    old = store.load_session(**binding)
    assert old.answer_statuses == ("legacy_unclassified",)
    assert old.messages[-1].text.startswith("[GENERAL KNOWLEDGE")
    new = store.append_exchange(**binding, expected_message_count=2,
                                student_text="Next?", professor_text="Answer.",
                                answer_status="course_grounded")
    assert new.answer_statuses == ("legacy_unclassified", "course_grounded")
    assert LocalChatStoreV01.open_existing(path).load_session(**binding) == new
    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute(
            "PRAGMA table_info(local_chat_messages_v01)")]
    assert columns.count("answer_status") == 1


def test_status_write_failure_rolls_back_student_too(tmp_path):
    store = LocalChatStoreV01.create_new(tmp_path / "chat.sqlite3")
    sid = store.create_session(local_profile_id="profile", course_id="course",
        objective_id="objective", pack_id="pack", pack_revision="v1",
        pack_sha256="a" * 64)
    binding = dict(session_id=sid, local_profile_id="profile", course_id="course",
        objective_id="objective", pack_id="pack", pack_revision="v1",
        pack_sha256="a" * 64)
    with sqlite3.connect(tmp_path / "chat.sqlite3") as connection:
        connection.execute("""
            CREATE TRIGGER block_status BEFORE INSERT ON local_chat_messages_v01
            WHEN NEW.answer_status = 'course_grounded'
            BEGIN SELECT RAISE(FAIL, 'metadata insert rejected'); END
        """)
    with pytest.raises(sqlite3.IntegrityError):
        store.append_exchange(**binding, expected_message_count=0,
            student_text="Question", professor_text="Answer",
            answer_status="course_grounded")
    assert store.load_session(**binding).messages == ()
    with pytest.raises(ValueError, match="answer status"):
        store.append_exchange(**binding, expected_message_count=0,
            student_text="Question", professor_text="Answer",
            answer_status="not_a_status")
    assert store.load_session(**binding).messages == ()

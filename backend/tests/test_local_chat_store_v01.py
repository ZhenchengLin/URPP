"""
URPP 14C-7D1 offline SQLite Chat Store tests.

Temporary synthetic databases only.
No real model inference, network, or Student State update.
"""

from hashlib import sha256

import pytest

from pydantic import ValidationError

from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatStoreV01,
)


DIGEST = sha256(
    b"synthetic-course-pack-v01"
).hexdigest()


def binding(session_id):
    return {
        "session_id": session_id,
        "local_profile_id": "synthetic-local-profile",
        "course_id": "synthetic-course",
        "objective_id": "synthetic-objective",
        "pack_id": "synthetic-pack",
        "pack_revision": "revision-001",
        "pack_sha256": DIGEST,
    }


def create_store(tmp_path):
    path = tmp_path / "chat.sqlite3"

    store = LocalChatStoreV01.create_new(path)

    session_id = store.create_session(
        local_profile_id="synthetic-local-profile",
        course_id="synthetic-course",
        objective_id="synthetic-objective",
        pack_id="synthetic-pack",
        pack_revision="revision-001",
        pack_sha256=DIGEST,
    )

    return store, path, session_id


def append(store, session_id, count, question, answer):
    return store.append_exchange(
        **binding(session_id),
        expected_message_count=count,
        student_text=question,
        professor_text=answer,
    )


def test_new_session_starts_without_messages(tmp_path):
    store, _, session_id = create_store(tmp_path)

    snapshot = store.load_session(
        **binding(session_id)
    )

    assert snapshot.turn_count == 0
    assert snapshot.messages == ()


def test_two_turns_survive_database_reopen(tmp_path):
    store, path, session_id = create_store(tmp_path)

    first = append(
        store,
        session_id,
        0,
        "What is LU?",
        "LU represents A as L times U.",
    )

    assert first.turn_count == 1

    second = append(
        store,
        session_id,
        2,
        "Why is L positive?",
        "L reverses the elimination step.",
    )

    assert second.turn_count == 2

    reopened = LocalChatStoreV01.open_existing(path)

    recovered = reopened.load_session(
        **binding(session_id)
    )

    assert recovered == second

    assert [
        message.role
        for message in recovered.messages
    ] == [
        "student",
        "professor",
        "student",
        "professor",
    ]

    assert recovered.messages[0].text == "What is LU?"
    assert recovered.messages[-1].text == (
        "L reverses the elimination step."
    )


def test_stale_append_does_not_duplicate_turn(tmp_path):
    store, _, session_id = create_store(tmp_path)

    append(
        store,
        session_id,
        0,
        "First question.",
        "First response.",
    )

    with pytest.raises(ValueError, match="advanced"):
        append(
            store,
            session_id,
            0,
            "Duplicate question.",
            "Duplicate response.",
        )

    recovered = store.load_session(
        **binding(session_id)
    )

    assert recovered.turn_count == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"local_profile_id": "other-profile"},
        {"course_id": "other-course"},
        {"objective_id": "other-objective"},
        {"pack_id": "other-pack"},
        {"pack_revision": "other-revision"},
        {"pack_sha256": "f" * 64},
    ],
)
def test_wrong_scope_or_version_cannot_load(
    tmp_path,
    changed,
):
    store, _, session_id = create_store(tmp_path)

    requested = {
        **binding(session_id),
        **changed,
    }

    with pytest.raises(LookupError):
        store.load_session(**requested)


def test_wrong_scope_cannot_append(tmp_path):
    store, _, session_id = create_store(tmp_path)

    requested = {
        **binding(session_id),
        "course_id": "other-course",
    }

    with pytest.raises(LookupError):
        store.append_exchange(
            **requested,
            expected_message_count=0,
            student_text="Question.",
            professor_text="Response.",
        )

    assert store.load_session(
        **binding(session_id)
    ).messages == ()


def test_invalid_professor_text_cannot_leave_half_turn(
    tmp_path,
):
    store, _, session_id = create_store(tmp_path)

    with pytest.raises(ValidationError):
        append(
            store,
            session_id,
            0,
            "Valid question.",
            "x" * 1501,
        )

    assert store.load_session(
        **binding(session_id)
    ).messages == ()


def test_existing_database_is_not_overwritten(tmp_path):
    store, path, session_id = create_store(tmp_path)

    with pytest.raises(FileExistsError):
        LocalChatStoreV01.create_new(path)

    assert store.load_session(
        **binding(session_id)
    ).turn_count == 0


def test_missing_database_is_not_silently_created(tmp_path):
    path = tmp_path / "missing.sqlite3"

    with pytest.raises(FileNotFoundError):
        LocalChatStoreV01.open_existing(path)

    assert not path.exists()


def test_context_uses_saved_complete_exchanges(tmp_path):
    store, _, session_id = create_store(tmp_path)

    append(
        store,
        session_id,
        0,
        "What is LU?",
        "LU factorizes A.",
    )

    snapshot = append(
        store,
        session_id,
        2,
        "Why is E negative?",
        "E performs subtraction.",
    )

    context = store.conversation_context(
        snapshot,
        current_student_message="Explain L again.",
    )

    assert context.current_student_message == (
        "Explain L again."
    )

    assert [
        (message.role, message.text)
        for message in context.history
    ] == [
        ("student", "What is LU?"),
        ("professor", "LU factorizes A."),
        ("student", "Why is E negative?"),
        ("professor", "E performs subtraction."),
    ]


def test_context_window_keeps_recent_pairs(
    tmp_path,
):
    store, _, session_id = create_store(tmp_path)

    snapshot = store.load_session(
        **binding(session_id)
    )

    for index in range(5):
        snapshot = append(
            store,
            session_id,
            index * 2,
            f"Question {index}",
            f"Answer {index}",
        )

    context = store.conversation_context(
        snapshot,
        current_student_message="Next question.",
    )

    assert len(snapshot.messages) == 10
    assert len(context.history) == 6

    assert context.history[0].text == "Question 2"
    assert context.history[-1].text == "Answer 4"


def test_long_history_remains_stored_when_context_is_short(
    tmp_path,
):
    store, _, session_id = create_store(tmp_path)

    append(
        store,
        session_id,
        0,
        "O" * 1500,
        "A" * 1500,
    )

    snapshot = append(
        store,
        session_id,
        2,
        "Recent question.",
        "B" * 1500,
    )

    context = store.conversation_context(
        snapshot,
        current_student_message="C" * 1500,
    )

    assert len(snapshot.messages) == 4

    assert [
        message.text
        for message in context.history
    ] == [
        "Recent question.",
        "B" * 1500,
    ]

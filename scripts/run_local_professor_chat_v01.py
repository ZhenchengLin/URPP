"""
URPP 14C-7D3: recoverable local Professor terminal chat.

Developer-only, single-user, serial local demonstration.

The Course Pack is a fixed synthetic LU example.
Real model inference uses a locally installed Ollama model.

Chat messages persist in a separate local SQLite database.
They are not assessment evidence or proof of mastery.

This CLI does not implement course-file uploads,
public student authentication, or a web interface.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

from hashlib import sha256
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(REPO_ROOT / "backend"),
)


from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatStoreV01,
)

from app.services.course_knowledge.local_professor_chat_service_v01 import (
    LocalProfessorChatServiceV01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


COURSE_ID = "synthetic-linear-algebra"
OBJECTIVE_ID = "synthetic-lu-elimination"
SOURCE_ID = "synthetic-lu-notes-section-1"

PACK_ID = "synthetic-lu-chat-pack"
PACK_REVISION = "synthetic-lu-chat-revision-001"

PROFILE_ID = "local-developer-profile"
STUDENT_ID = "synthetic-local-chat-student"

DEFAULT_DATABASE = (
    Path.home()
    / "Library"
    / "Caches"
    / "URPP"
    / "local_professor_chat_demo_v01"
    / "chat.sqlite3"
)

NOTES = """
Synthetic LU Decomposition Notes — Section 1

Consider the matrix:

A = [[2, 1],
     [4, 3]]

The elimination multiplier is m = 4 / 2 = 2.

Apply the row operation:

Row 2 <- Row 2 - 2 * Row 1

The resulting upper triangular matrix is:

U = [[2, 1],
     [0, 1]]

The elementary elimination matrix is:

E = [[1,  0],
     [-2, 1]]

It performs the elimination step:

E * A = U.

The lower triangular matrix is:

L = [[1, 0],
     [2, 1]]

It reverses the elimination step:

A = L * U.

Therefore:

L = E^(-1).

E contains the negative multiplier because it subtracts
a multiple of Row 1 during elimination.

L contains the positive multiplier because it reverses
that operation when reconstructing A from U.
""".strip()


def build_pack() -> CoursePackV01:
    """Reconstruct the same versioned synthetic Course Pack."""

    source = CourseSourceV01(
        course_id=COURSE_ID,
        source_id=SOURCE_ID,
        source_revision="synthetic-lu-source-revision-001",
        source_locator="synthetic-lu-notes:section-1",
        content=NOTES,
        content_sha256=sha256(
            NOTES.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        description=(
            "Explain LU decomposition, the elimination "
            "multiplier, and the inverse relationship "
            "between E and L."
        ),
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE_ID,
        pack_id=PACK_ID,
        pack_revision=PACK_REVISION,
        objectives=(objective,),
        sources=(source,),
    )


def build_service(
    store: LocalChatStoreV01,
    gateway,
) -> LocalProfessorChatServiceV01:
    """Reuse URPP's existing durable teaching pipeline."""

    return LocalProfessorChatServiceV01(
        chat_store=store,
        pack=build_pack(),
        gateway=gateway,
        local_profile_id=PROFILE_ID,
        synthetic_student_id=STUDENT_ID,
    )


def open_chat_database(
    path: Path,
    *,
    create_if_missing: bool,
) -> LocalChatStoreV01:
    """
    Only create a database when starting a new local chat.

    Never overwrite an existing database or silently create
    a missing database during Session recovery.
    """

    path = path.expanduser().absolute()

    if path.is_relative_to(REPO_ROOT):
        raise ValueError(
            "Chat database must be stored outside Git Repository."
        )

    if path.is_symlink():
        raise ValueError(
            "Chat database path cannot be a symlink."
        )

    if path.exists():
        return LocalChatStoreV01.open_existing(path)

    if not create_if_missing:
        raise FileNotFoundError(
            "Cannot resume: local Chat database does not exist."
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    if path.parent.is_symlink():
        raise ValueError(
            "Chat database directory cannot be a symlink."
        )

    return LocalChatStoreV01.create_new(path)


class FakeGateway:
    """Offline self-test only. Never contacts Ollama."""

    def __init__(self):
        self.calls = []

    def generate_structured(
        self,
        *,
        prompt_name,
        payload,
    ):
        self.calls.append(
            (prompt_name, payload)
        )

        return {
            "content": (
                "Synthetic explanation for offline CLI testing."
            ),
            "source_ids": [SOURCE_ID],
        }


def run_offline_self_test() -> None:
    """
    Verify the actual Chat Service and database recovery.

    A temporary database is used and automatically cleaned
    up after this test.
    """

    with tempfile.TemporaryDirectory(
        prefix="urpp-local-chat-self-test-"
    ) as directory:

        database = Path(directory) / "chat.sqlite3"

        store = LocalChatStoreV01.create_new(
            database
        )

        fake = FakeGateway()

        service = build_service(
            store,
            fake,
        )

        session_id = service.start_session(
            objective_id=OBJECTIVE_ID
        )

        first = service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE_ID,
            student_text="What is LU?",
            expected_message_count=0,
        )

        assert first.snapshot.turn_count == 1

        reopened_store = LocalChatStoreV01.open_existing(
            database
        )

        resumed_service = build_service(
            reopened_store,
            fake,
        )

        recovered = resumed_service.resume_session(
            session_id=session_id,
            objective_id=OBJECTIVE_ID,
        )

        assert recovered.messages == first.snapshot.messages

        second = resumed_service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE_ID,
            student_text="Explain the elimination matrix.",
            expected_message_count=len(
                recovered.messages
            ),
        )

        assert second.snapshot.turn_count == 2
        assert len(fake.calls) == 2

        second_payload = fake.calls[1][1]

        assert second_payload["teaching_action"] == (
            "conceptual_review"
        )

        assert "What is LU?" in (
            second_payload["instructions"]
        )

        assert (
            "Synthetic explanation for offline CLI testing."
            in second_payload["instructions"]
        )

        final_recovery = resumed_service.resume_session(
            session_id=session_id,
            objective_id=OBJECTIVE_ID,
        )

        assert final_recovery.messages == second.snapshot.messages

    print("PASS: Two teaching turns saved.")
    print("PASS: Session recovered after reopening SQLite.")
    print("PASS: Previous dialogue reached the second request.")
    print("PASS: No network or real model inference.")


def display_history(snapshot) -> None:
    """Show the saved conversation in chronological order."""

    if not snapshot.messages:
        print("\nNo saved messages yet.")
        return

    print("\n========== SAVED CONVERSATION ==========")

    for message in snapshot.messages:
        label = (
            "You"
            if message.role == "student"
            else "Professor"
        )

        print(f"\n{label}:\n{message.text}")

    print("\n========================================")


def run_interactive_chat(
    *,
    database: Path,
    new_session: bool,
    resume_id: str | None,
) -> None:
    """
    Run a single-user, serial, local teaching conversation.

    A full exchange is stored before the answer is displayed.
    If model generation or persistence fails, do not claim
    that a new turn was saved.
    """

    store = open_chat_database(
        database,
        create_if_missing=new_session,
    )

    gateway = LocalOllamaProfessorGatewayV01(
        model="qwen3.5:4b"
    )

    service = build_service(
        store,
        gateway,
    )

    if new_session:
        session_id = service.start_session(
            objective_id=OBJECTIVE_ID
        )
    else:
        assert resume_id is not None
        session_id = resume_id

    snapshot = service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE_ID,
    )

    print("\n========================================")
    print("URPP LOCAL PROFESSOR CHAT")
    print("========================================")

    print("Model: qwen3.5:4b — local Ollama")
    print("Course: Synthetic LU Decomposition")
    print("Mode: Developer-only teaching demonstration")
    print("Database:", database.expanduser().absolute())

    print("\nSESSION ID:")
    print(session_id)

    print(
        "\n保存上面的 Session ID。退出后可以用它恢复对话。"
    )

    print(
        "\nCommands: history = show saved messages; "
        "quit = exit."
    )

    print(
        "当前版本只执行 explanation，不进行测验或 Mastery 更新。"
    )

    if snapshot.messages:
        print(
            f"\nRecovered {snapshot.turn_count} saved turns."
        )
        display_history(snapshot)

    while True:
        try:
            question = input("\nYou > ").strip()

        except (EOFError, KeyboardInterrupt):
            print("\nChat exited. Saved turns remain in SQLite.")
            return

        if question.lower() in {"quit", "exit", ":quit"}:
            print("\nChat exited. Saved turns remain in SQLite.")
            return

        if question.lower() in {"history", ":history"}:
            display_history(snapshot)
            continue

        if not question:
            print("Enter a question, history, or quit.")
            continue

        if len(question) > 1500:
            print(
                "Question exceeds the 1,500-character "
                "local pilot limit."
            )
            continue

        print("\nProfessor is generating locally...")

        try:
            turn = service.send_explanation(
                session_id=session_id,
                objective_id=OBJECTIVE_ID,
                student_text=question,
                expected_message_count=len(
                    snapshot.messages
                ),
            )

        except Exception as exc:
            print(
                "\nTURN FAILED:",
                type(exc).__name__,
                str(exc),
            )

            print(
                "No successful exchange was returned. "
                "Reloading the saved Session."
            )

            snapshot = service.resume_session(
                session_id=session_id,
                objective_id=OBJECTIVE_ID,
            )

            print(
                "Saved turns:",
                snapshot.turn_count,
            )

            print(
                "The question was not automatically retried."
            )

            continue

        snapshot = turn.snapshot

        print("\nProfessor:\n")
        print(turn.professor_text)

        print(
            f"\n[Saved turn {snapshot.turn_count}; "
            "generated content, not Mastery Evidence.]"
        )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "URPP developer-only recoverable "
            "Local Professor Chat."
        )
    )

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--new",
        action="store_true",
        help="Start a new Session.",
    )

    mode.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="Recover a previously saved Session.",
    )

    mode.add_argument(
        "--self-test",
        action="store_true",
        help="Run an offline test without model inference.",
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Local SQLite path outside the repository.",
    )

    args = parser.parse_args()

    if args.self_test:
        run_offline_self_test()
        return 0

    # Protect newly created local database files.
    os.umask(0o077)

    try:
        run_interactive_chat(
            database=args.database,
            new_session=args.new,
            resume_id=args.resume,
        )

    except (
        FileExistsError,
        FileNotFoundError,
        LookupError,
        ValueError,
        OSError,
    ) as exc:

        print(
            "LOCAL CHAT STARTUP FAILED:",
            type(exc).__name__,
            str(exc),
            file=sys.stderr,
        )

        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

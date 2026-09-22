"""
URPP 14B-3-2B: interactive synthetic activity integration.

Each CLI invocation runs in a separate Python process.
All SQLite databases are created inside pytest temp directories.

Submitted text remains raw input. No assessment, scoring,
mastery evidence, or Student State update is performed.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]

SCRIPT = (
    BACKEND
    / "scripts"
    / "course_teaching_demo_v01.py"
)

FILENAME = "urpp-course-teaching-demo.sqlite"

ANSWER = (
    "  Decomposition can expose matrix structure "
    "for later computation.  "
)


def invoke(
    database,
    action,
    *,
    answer=None,
    success=True,
):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            action,
            "--database",
            str(database),
        ],
        cwd=BACKEND,
        input=answer,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if success:
        assert completed.returncode == 0, (
            completed.stdout
            + completed.stderr
        )
    else:
        assert completed.returncode != 0

    messages = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]

    return messages, completed


def initialized(tmp_path):
    database = tmp_path / FILENAME

    messages, _ = invoke(database, "init")

    assert messages[0]["status"] == "initialized"

    return database


def taught_and_presented(database):
    taught, _ = invoke(database, "teach")

    assert taught[0]["status"] == "generated"

    displayed, _ = invoke(database, "present")

    assert displayed[-1]["status"] == (
        "presentation_reported"
    )

    return taught[0]


def test_activity_answer_and_recovery_across_processes(
    tmp_path,
):
    database = initialized(tmp_path)

    original_teaching = taught_and_presented(
        database
    )

    activity, _ = invoke(database, "activity")

    assert activity[0]["status"] == (
        "synthetic_activity_prompt"
    )
    assert activity[0]["activity_id"] == (
        "synthetic-activity-001"
    )
    assert "SYNTHETIC ACTIVITY" in (
        activity[0]["activity_prompt"]
    )

    before, _ = invoke(database, "response")

    assert before[0]["status"] == "not_submitted"

    entered, completed = invoke(
        database,
        "answer",
        answer=ANSWER + "\\n",
    )

    assert len(entered) == 2
    assert entered[0]["status"] == (
        "synthetic_activity_prompt"
    )
    assert entered[1]["status"] == (
        "response_recorded"
    )
    assert entered[1]["response_text"] == ANSWER
    assert entered[1]["already_submitted"] is False
    assert "Your answer" in completed.stderr

    # A new Python process reads the stored original input.
    recovered, _ = invoke(database, "response")

    assert recovered[0]["status"] == "response_recorded"
    assert recovered[0]["response_text"] == ANSWER
    assert recovered[0]["activity_prompt"] == (
        activity[0]["activity_prompt"]
    )

    # Activity input must not regenerate teaching content.
    taught_again, _ = invoke(database, "teach")

    assert taught_again[0]["content"] == (
        original_teaching["content"]
    )

    with sqlite3.connect(database) as connection:
        response_count = connection.execute(
            "SELECT COUNT(*) "
            "FROM course_learning_responses_v01"
        ).fetchone()[0]

    assert response_count == 1


def test_duplicate_answer_returns_original_without_reading_stdin(
    tmp_path,
):
    database = initialized(tmp_path)

    taught_and_presented(database)

    first, _ = invoke(
        database,
        "answer",
        answer="First submitted answer.\\n",
    )

    repeated, _ = invoke(
        database,
        "answer",
        answer="Changed answer that must not be stored.\\n",
    )

    assert first[-1]["response_text"] == (
        "First submitted answer."
    )

    assert len(repeated) == 1
    assert repeated[0]["already_submitted"] is True
    assert repeated[0]["response_text"] == (
        "First submitted answer."
    )

    restored, _ = invoke(database, "response")

    assert restored[0]["response_text"] == (
        "First submitted answer."
    )


def test_activity_and_answer_require_presentation(
    tmp_path,
):
    database = initialized(tmp_path)

    invoke(database, "teach")

    _, activity_result = invoke(
        database,
        "activity",
        success=False,
    )

    _, answer_result = invoke(
        database,
        "answer",
        answer="Do not store this.\\n",
        success=False,
    )

    assert "Run present" in activity_result.stderr
    assert "Run present" in answer_result.stderr

    response, _ = invoke(database, "response")

    assert response[0]["status"] == "not_submitted"


def test_empty_or_missing_input_does_not_save_a_response(
    tmp_path,
):
    database = initialized(tmp_path)

    taught_and_presented(database)

    _, no_input = invoke(
        database,
        "answer",
        answer="",
        success=False,
    )

    assert "No response was received" in (
        no_input.stderr
    )

    _, blank_input = invoke(
        database,
        "answer",
        answer="   \\n",
        success=False,
    )

    assert "response_text" in blank_input.stderr

    recovered, _ = invoke(database, "response")

    assert recovered[0]["status"] == "not_submitted"


def test_status_and_presentation_remain_separate_from_response(
    tmp_path,
):
    database = initialized(tmp_path)

    taught_and_presented(database)

    invoke(
        database,
        "answer",
        answer="My actual typed text.\\n",
    )

    delivery, _ = invoke(database, "status")
    response, _ = invoke(database, "response")

    assert delivery[0]["status"] == (
        "presentation_reported"
    )
    assert response[0]["status"] == (
        "response_recorded"
    )
    assert delivery[0]["presentation_event_id"] == (
        "synthetic-presentation-001"
    )

    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT activity_id, response_text "
            "FROM course_learning_responses_v01"
        ).fetchall()

    assert rows == [
        (
            "synthetic-activity-001",
            "My actual typed text.",
        )
    ]


def test_activity_response_does_not_modify_teaching_trace(
    tmp_path,
):
    database = initialized(tmp_path)

    initial = taught_and_presented(database)

    with sqlite3.connect(database) as connection:
        before = connection.execute(
            "SELECT payload "
            "FROM course_teaching_traces_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()[0]

    invoke(
        database,
        "answer",
        answer="Student input is not mastery evidence.\\n",
    )

    with sqlite3.connect(database) as connection:
        after = connection.execute(
            "SELECT payload "
            "FROM course_teaching_traces_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()[0]

    assert before == after

    recovered, _ = invoke(database, "teach")

    assert recovered[0]["content"] == initial["content"]

"""
URPP 14B-3-2C-2 integration tests.

All course content, inputs, and feedback are synthetic.
Each CLI command executes in a separate Python process.
No assessment, mastery evidence, or Student State update.
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
    "  A matrix decomposition can expose useful "
    "structure for computation.  "
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
            completed.stdout + completed.stderr
        )
    else:
        assert completed.returncode != 0

    messages = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]

    return messages, completed


def initialize(tmp_path):
    database = tmp_path / FILENAME

    initialized, _ = invoke(
        database,
        "init",
    )

    assert initialized[0]["status"] == "initialized"

    return database


def prepare_response(database):
    teaching, _ = invoke(database, "teach")

    presented, _ = invoke(database, "present")

    assert presented[-1]["status"] == (
        "presentation_reported"
    )

    submitted, _ = invoke(
        database,
        "answer",
        answer=ANSWER + "\n",
    )

    assert submitted[-1]["status"] == (
        "response_recorded"
    )

    assert submitted[-1]["response_text"] == ANSWER

    return teaching[0]


def test_feedback_generation_and_recovery_across_processes(
    tmp_path,
):
    database = initialize(tmp_path)
    original_teaching = prepare_response(database)

    before, _ = invoke(
        database,
        "feedback-status",
    )

    assert before[0]["status"] == (
        "feedback_not_generated"
    )

    first, _ = invoke(
        database,
        "feedback",
    )

    assert len(first) == 1
    assert first[0]["status"] == "generated_feedback"
    assert first[0]["recovered"] is False
    assert first[0]["feedback_id"] == (
        "synthetic-feedback-001"
    )
    assert first[0]["response_id"] == (
        "synthetic-response-001"
    )
    assert "SYNTHETIC FEEDBACK" in (
        first[0]["feedback_text"]
    )
    assert "Generation token:" in (
        first[0]["feedback_text"]
    )

    # Both commands launch fresh Python processes.
    # Neither may call the Agent again.
    retried, _ = invoke(
        database,
        "feedback",
    )

    recovered, _ = invoke(
        database,
        "feedback-status",
    )

    assert retried[0]["recovered"] is True
    assert recovered[0]["recovered"] is True
    assert retried[0]["feedback_text"] == (
        first[0]["feedback_text"]
    )
    assert recovered[0]["feedback_text"] == (
        first[0]["feedback_text"]
    )

    original_response, _ = invoke(
        database,
        "response",
    )

    original_trace, _ = invoke(
        database,
        "teach",
    )

    assert original_response[0]["response_text"] == ANSWER
    assert original_trace[0]["content"] == (
        original_teaching["content"]
    )

    with sqlite3.connect(database) as connection:
        feedback_rows = connection.execute(
            "SELECT response_id, status, feedback_text "
            "FROM course_learning_feedback_v01"
        ).fetchall()

        response_rows = connection.execute(
            "SELECT response_text "
            "FROM course_learning_responses_v01"
        ).fetchall()

    assert feedback_rows == [
        (
            "synthetic-response-001",
            "completed",
            first[0]["feedback_text"],
        )
    ]

    assert response_rows == [(ANSWER,)]


def test_feedback_requires_saved_student_response(tmp_path):
    database = initialize(tmp_path)

    invoke(database, "teach")
    invoke(database, "present")

    _, failed = invoke(
        database,
        "feedback",
        success=False,
    )

    assert "Student response was not found" in (
        failed.stderr
    )

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            "SELECT COUNT(*) "
            "FROM course_learning_feedback_v01"
        ).fetchone()[0]

    assert count == 0


def test_feedback_status_is_read_only(tmp_path):
    database = initialize(tmp_path)

    prepare_response(database)

    first, _ = invoke(
        database,
        "feedback-status",
    )

    second, _ = invoke(
        database,
        "feedback-status",
    )

    assert first == second
    assert first[0]["status"] == (
        "feedback_not_generated"
    )

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            "SELECT COUNT(*) "
            "FROM course_learning_feedback_v01"
        ).fetchone()[0]

    assert count == 0


def test_feedback_does_not_modify_original_records(tmp_path):
    database = initialize(tmp_path)

    prepare_response(database)

    with sqlite3.connect(database) as connection:
        trace_before = connection.execute(
            "SELECT payload FROM course_teaching_traces_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()[0]

        response_before = connection.execute(
            "SELECT activity_prompt, response_text "
            "FROM course_learning_responses_v01 "
            "WHERE response_id = ?",
            ("synthetic-response-001",),
        ).fetchone()

        presentation_before = connection.execute(
            "SELECT event_id, reported_at_utc "
            "FROM course_teaching_presentations_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()

    invoke(database, "feedback")

    with sqlite3.connect(database) as connection:
        trace_after = connection.execute(
            "SELECT payload FROM course_teaching_traces_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()[0]

        response_after = connection.execute(
            "SELECT activity_prompt, response_text "
            "FROM course_learning_responses_v01 "
            "WHERE response_id = ?",
            ("synthetic-response-001",),
        ).fetchone()

        presentation_after = connection.execute(
            "SELECT event_id, reported_at_utc "
            "FROM course_teaching_presentations_v01 "
            "WHERE trace_id = ?",
            ("synthetic-trace-001",),
        ).fetchone()

    assert trace_after == trace_before
    assert response_after == response_before
    assert presentation_after == presentation_before


def test_existing_demo_is_not_implicitly_migrated(tmp_path):
    database = initialize(tmp_path)

    prepare_response(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DROP TABLE course_learning_feedback_v01"
        )

    _, failed = invoke(
        database,
        "feedback",
        success=False,
    )

    assert "course_learning_feedback_v01" in failed.stderr

    with sqlite3.connect(database) as connection:
        exists = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = ?",
            ("course_learning_feedback_v01",),
        ).fetchone()[0]

    assert exists == 0

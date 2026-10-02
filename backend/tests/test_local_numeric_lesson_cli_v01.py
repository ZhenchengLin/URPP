"""
URPP Implementation 13E-3C.

End-to-end tests launch the executable CLI as a separate
process and interact with its real stdin/stdout.

The resulting new SQLite file is inspected independently
after the process exits.

These tests do not simulate a browser or authenticated
student and do not establish independent performance.
"""

import json
import sqlite3
import subprocess
import sys

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CLI = (
    PROJECT_ROOT
    / "scripts"
    / "run_local_numeric_lesson_v01.py"
)


def launch_cli(
    database_path,
    *,
    inputs,
):
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--database",
            str(database_path),
        ],
        input=inputs,
        text=True,
        capture_output=True,
        cwd=PROJECT_ROOT,
        timeout=25,
        check=False,
    )


def inspect_database(database_path):
    with sqlite3.connect(database_path) as connection:
        assignments = connection.execute(
            """
            SELECT status, completed_attempt_id
            FROM numeric_assignments_v01
            """
        ).fetchall()

        assistance = connection.execute(
            """
            SELECT kind, source, content_sha256
            FROM assessment_assistance_events_v01
            ORDER BY occurred_at_utc, event_id
            """
        ).fetchall()

        attempts = connection.execute(
            """
            SELECT payload
            FROM student_attempts_v02
            """
        ).fetchall()

    return assignments, assistance, attempts


def test_real_cli_hint_answer_and_sqlite_recovery(
    tmp_path,
):
    database = (
        tmp_path
        / "local_teaching_demo.sqlite"
    )

    completed = launch_cli(
        database,
        inputs="hint\n5\n",
    )

    assert completed.returncode == 0, (
        completed.stdout
        + "\n"
        + completed.stderr
    )

    assert "Answer was not accepted:" not in completed.stdout
    assert "Assignment remains pending" not in completed.stdout
    assert "Decision cannot precede" not in completed.stderr
    assert "=== RECOVERED STUDENT STATE ===" in completed.stdout

    assert "[HINT]" in completed.stdout

    assert (
        "Assistance event recorded: "
        "hint, source=application_reported"
    ) in completed.stdout

    assert "Next Action: conceptual_review" in (
        completed.stdout
    )

    assert "Agent Kind: professor" in (
        completed.stdout
    )

    assignments, assistance, attempts = (
        inspect_database(database)
    )

    assert len(assignments) == 1

    assert assignments[0][0] == "completed"

    assert assignments[0][1] is not None

    assert len(assistance) == 1

    assert assistance[0][0] == "hint"

    assert assistance[0][1] == (
        "application_reported"
    )

    assert len(assistance[0][2]) == 64

    assert len(attempts) == 1

    attempt = json.loads(
        attempts[0][0]
    )

    assert attempt["response_text"] == "5"

    assert attempt["assistance_level"] is None

    assert attempt["prior_solution_exposure"] is None

    assert "Included Evidence: 0" in (
        completed.stdout
    )

    assert "Independent Successes: 0" in (
        completed.stdout
    )


def test_real_cli_solution_is_separately_recorded(
    tmp_path,
):
    database = (
        tmp_path
        / "solution_demo.sqlite"
    )

    completed = launch_cli(
        database,
        inputs="solution\n5\n",
    )

    assert completed.returncode == 0, (
        completed.stdout
        + "\n"
        + completed.stderr
    )

    assert "[SOLUTION]" in completed.stdout

    assignments, assistance, attempts = (
        inspect_database(database)
    )

    assert len(assignments) == 1

    assert assignments[0][0] == "completed"

    assert len(assistance) == 1

    assert assistance[0][0] == "solution"

    assert len(attempts) == 1

    attempt = json.loads(
        attempts[0][0]
    )

    assert attempt["assistance_level"] is None

    assert attempt["prior_solution_exposure"] is None


def test_real_cli_no_help_does_not_imply_independence(
    tmp_path,
):
    database = (
        tmp_path
        / "no_help_demo.sqlite"
    )

    completed = launch_cli(
        database,
        inputs="5\n",
    )

    assert completed.returncode == 0, (
        completed.stdout
        + "\n"
        + completed.stderr
    )

    assignments, assistance, attempts = (
        inspect_database(database)
    )

    assert len(assignments) == 1

    assert assignments[0][0] == "completed"

    assert assistance == []

    assert "Answer was not accepted:" not in completed.stdout
    assert "Assignment remains pending" not in completed.stdout
    assert "Decision cannot precede" not in completed.stderr
    assert "=== RECOVERED STUDENT STATE ===" in completed.stdout

    assert len(attempts) == 1

    attempt = json.loads(
        attempts[0][0]
    )

    assert attempt["assistance_level"] is None

    assert attempt["prior_solution_exposure"] is None

    assert "Included Evidence: 0" in (
        completed.stdout
    )

    assert "Independent Successes: 0" in (
        completed.stdout
    )


def test_cli_refuses_existing_database_without_modifying_it(
    tmp_path,
):
    database = (
        tmp_path
        / "existing.sqlite"
    )

    original_contents = (
        b"Existing data must not be overwritten."
    )

    database.write_bytes(
        original_contents
    )

    result = launch_cli(
        database,
        inputs="5\n",
    )

    assert result.returncode == 2

    assert "Refusing to open an existing database" in (
        result.stderr
    )

    assert database.read_bytes() == original_contents


def test_cli_quit_keeps_assignment_pending(
    tmp_path,
):
    database = (
        tmp_path
        / "quit_demo.sqlite"
    )

    result = launch_cli(
        database,
        inputs="quit\n",
    )

    assert result.returncode == 0, (
        result.stdout
        + "\n"
        + result.stderr
    )

    assignments, assistance, attempts = (
        inspect_database(database)
    )

    assert len(assignments) == 1

    assert assignments[0][0] == "pending"

    assert assistance == []

    assert attempts == []

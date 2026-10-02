"""
URPP 14B-3-1: cross-process synthetic CLI integration tests.

All databases are temporary. No production URPP data,
real course material, or student-learning evidence is used.
"""

import json
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = (
    BACKEND
    / "scripts"
    / "course_teaching_demo_v01.py"
)

DEMO_FILENAME = "urpp-course-teaching-demo.sqlite"


def invoke(database, action, *, expect_success=True):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            action,
            "--database",
            str(database),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if expect_success:
        assert completed.returncode == 0, (
            completed.stdout + completed.stderr
        )
    else:
        assert completed.returncode != 0

    return [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]


def test_complete_demo_survives_separate_processes(tmp_path):
    database = tmp_path / DEMO_FILENAME

    assert invoke(database, "init")[0]["status"] == "initialized"

    before = invoke(database, "status")[0]

    assert before["status"] == "not_generated"

    # Each invocation starts a NEW Python process.
    first = invoke(database, "teach")[0]

    assert first["status"] == "generated"
    assert first["trace_id"] == "synthetic-trace-001"
    assert first["decision_id"] == "synthetic-decision-001"

    assert first["source_locators"] == [
        "synthetic-fixture:section-1"
    ]

    assert "SYNTHETIC DEMO" in first["content"]

    # The Fake Professor includes a unique generation token.
    # A retry must recover the original content, not regenerate.
    second = invoke(database, "teach")[0]

    assert second == first

    generated = invoke(database, "status")[0]

    assert generated["status"] == "generated"
    assert generated["content"] == first["content"]

    displayed = invoke(database, "present")

    assert len(displayed) == 2

    assert displayed[0]["display_content"] == first["content"]

    assert displayed[1]["status"] == "presentation_reported"
    assert displayed[1]["already_reported"] is False

    recovered = invoke(database, "status")[0]

    assert recovered["status"] == "presentation_reported"
    assert recovered["content"] == first["content"]

    assert (
        recovered["presentation_event_id"]
        == "synthetic-presentation-001"
    )

    # Repeating present must not create a second event
    # or print the content again.
    repeated = invoke(database, "present")

    assert len(repeated) == 1
    assert repeated[0]["already_reported"] is True

    assert invoke(database, "teach")[0]["content"] == first["content"]


def test_demo_refuses_missing_database_and_implicit_creation(
    tmp_path,
):
    database = tmp_path / DEMO_FILENAME

    invoke(
        database,
        "teach",
        expect_success=False,
    )

    assert not database.exists()


def test_demo_refuses_non_demo_database_name(tmp_path):
    database = tmp_path / "production.sqlite"

    invoke(
        database,
        "init",
        expect_success=False,
    )

    assert not database.exists()


def test_demo_refuses_existing_non_demo_database(tmp_path):
    database = tmp_path / DEMO_FILENAME

    database.write_bytes(b"not-a-demo-database")

    invoke(
        database,
        "init",
        expect_success=False,
    )

    invoke(
        database,
        "teach",
        expect_success=False,
    )

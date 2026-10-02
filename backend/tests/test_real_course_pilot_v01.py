"""14A-3 independent local Course Pack CLI checks; synthetic fixture only.

The actual MIT course pack is smoke-tested separately from local data;
course excerpts must not be added to source control as test fixtures.
"""

import json
import sqlite3
import subprocess
import sys
from hashlib import sha256
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "real_course_pilot_v01.py"
DB_NAME = "urpp-real-course-pilot.sqlite"


def make_pack(tmp_path, *, content="SYNTHETIC LOCAL PILOT EXCERPT"):
    source = {
        "course_id": "synthetic-pilot-course",
        "source_id": "synthetic-pilot-source",
        "source_revision": "synthetic-pilot-revision-001",
        "source_locator": "synthetic-fixture:section-1",
        "content": content,
        "content_sha256": sha256(content.encode("utf-8")).hexdigest(),
        "visibility": "student_visible",
        "use_permission": "approved_for_local_teaching",
        "review_status": "approved",
    }
    pack = {
        "course_id": source["course_id"],
        "pack_id": "synthetic-pilot-pack",
        "pack_revision": "synthetic-pilot-pack-revision-001",
        "objectives": [{
            "course_id": source["course_id"],
            "objective_id": "synthetic-pilot-objective",
            "description": "Explain the synthetic excerpt.",
            "review_status": "approved",
            "source_refs": [{key: source[key] for key in (
                "source_id", "source_revision", "source_locator", "content_sha256"
            )}],
        }],
        "sources": [source],
    }
    path = tmp_path / "synthetic-pilot-pack.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    return path


def invoke(db, pack, action, *, success=True):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), action,
         "--database", str(db), "--pack", str(pack)],
        cwd=BACKEND, capture_output=True, text=True, timeout=30,
    )
    if success:
        assert completed.returncode == 0, completed.stdout + completed.stderr
    else:
        assert completed.returncode != 0, completed.stdout + completed.stderr
    messages = [json.loads(line) for line in completed.stdout.splitlines()
                if line.strip()]
    return messages, completed


def test_full_local_pilot_recovers_original_across_processes(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    created, _ = invoke(db, pack, "init")
    assert created[0]["status"] == "initialized"
    assert created[0]["course_id"] == "synthetic-pilot-course"
    assert invoke(db, pack, "status")[0][0]["status"] == "not_generated"

    first, _ = invoke(db, pack, "teach")
    assert first[0]["status"] == "generated"
    assert first[0]["source_locators"] == ["synthetic-fixture:section-1"]
    assert "SYNTHETIC LOCAL PILOT EXCERPT" in first[0]["content"]
    assert "NOT AI-GENERATED TEACHING" in first[0]["content"]

    repeated, _ = invoke(db, pack, "teach")
    assert repeated == first
    assert invoke(db, pack, "status")[0][0]["content"] == first[0]["content"]

    displayed, _ = invoke(db, pack, "present")
    assert len(displayed) == 2
    assert displayed[0]["display_content"] == first[0]["content"]
    assert displayed[1]["status"] == "presentation_reported"
    assert displayed[1]["already_reported"] is False
    repeated_presentation, _ = invoke(db, pack, "present")
    assert repeated_presentation[0]["already_reported"] is True
    assert len(repeated_presentation) == 1
    assert invoke(db, pack, "status")[0][0]["status"] == "presentation_reported"
    assert invoke(db, pack, "teach")[0] == [
        {**first[0], "status": "presentation_reported"}
    ]

    with sqlite3.connect(db) as connection:
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "course_teaching_traces_v01" in names
        assert "course_teaching_turn_intents_v01" in names
        assert "course_teaching_presentations_v01" in names
        assert "course_learning_responses_v01" not in names
        assert "course_learning_feedback_v01" not in names
        assert connection.execute(
            "SELECT COUNT(*) FROM course_teaching_traces_v01").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM course_teaching_presentations_v01").fetchone()[0] == 1


def test_pilot_refuses_pack_change_before_teaching_or_presentation(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    invoke(db, pack, "init")
    first, _ = invoke(db, pack, "teach")
    original_bytes = pack.read_bytes()
    changed_pack = make_pack(tmp_path, content="CHANGED SYNTHETIC EXCERPT")
    assert pack == changed_pack
    for action in ("teach", "present", "status"):
        _, failed = invoke(db, pack, action, success=False)
        assert "Course Pack mismatch" in failed.stderr
    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM course_teaching_traces_v01").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM course_teaching_presentations_v01").fetchone()[0] == 0
    # Restore the exact original file bytes, not a reconstructed fixture.
    pack.write_bytes(original_bytes)
    assert invoke(db, pack, "teach")[0] == first


def test_invalid_or_missing_course_pack_never_creates_database(tmp_path):
    db = tmp_path / DB_NAME
    pack = make_pack(tmp_path)
    source = json.loads(pack.read_text(encoding="utf-8"))
    source["sources"][0]["content"] = "tampered without updating SHA"
    pack.write_text(json.dumps(source), encoding="utf-8")
    _, failed = invoke(db, pack, "init", success=False)
    assert "digest mismatch" in failed.stderr
    assert not db.exists()

    _, failed = invoke(db, tmp_path / "missing.json", "init", success=False)
    assert failed.returncode != 0
    assert not db.exists()


def test_pilot_refuses_existing_database_and_wrong_name(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    invoke(db, pack, "init")
    _, failed = invoke(db, pack, "init", success=False)
    assert "already exists" in failed.stderr
    wrong = tmp_path / "production.sqlite"
    _, failed = invoke(wrong, pack, "init", success=False)
    assert "filename" in failed.stderr
    assert not wrong.exists()


def test_existing_non_pilot_database_is_not_modified(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
        connection.execute("INSERT INTO unrelated VALUES (42)")
    before = db.read_bytes()
    _, failed = invoke(db, pack, "teach", success=False)
    assert "pilot_identity" in failed.stderr
    assert db.read_bytes() == before


def test_requires_presentation_after_generation(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    invoke(db, pack, "init")
    _, failed = invoke(db, pack, "present", success=False)
    assert "Teaching Trace was not found" in failed.stderr
    assert invoke(db, pack, "status")[0][0]["status"] == "not_generated"


def test_cannot_silently_switch_to_unapproved_source(tmp_path):
    pack = make_pack(tmp_path)
    db = tmp_path / DB_NAME
    payload = json.loads(pack.read_text(encoding="utf-8"))
    payload["sources"][0]["use_permission"] = "not_authorized"
    pack.write_text(json.dumps(payload), encoding="utf-8")
    _, failed = invoke(db, pack, "init", success=False)
    assert "not approved for local teaching" in failed.stderr
    assert not db.exists()

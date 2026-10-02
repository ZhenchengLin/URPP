"""
URPP Design 01D — SQLite Numeric Assignment Migration tests.

Every test uses a temporary, synthetic database.

No user database or real student information is accessed.
"""

import sqlite3

from pathlib import Path

import pytest

from app.repositories.migrate_numeric_assignment_v01_sqlite import (
    MigrationSafetyError,
    inspect,
    migrate,
)


LEGACY_ASSIGNMENT_DDL = """
CREATE TABLE numeric_assignments_v01 (
    assignment_id VARCHAR(128) NOT NULL PRIMARY KEY,
    decision_id VARCHAR(128) NOT NULL,
    student_id VARCHAR(128) NOT NULL,
    course_id VARCHAR(128) NOT NULL,
    objective_id VARCHAR(128) NOT NULL,
    session_id VARCHAR(128) NOT NULL,
    assessment_item_id VARCHAR(128) NOT NULL,
    item_revision INTEGER NOT NULL,
    assigned_at_utc VARCHAR(48) NOT NULL,
    status VARCHAR(16) NOT NULL,
    completed_attempt_id VARCHAR(128) UNIQUE,
    CONSTRAINT numeric_assignment_status_consistency CHECK (
        (
            status = 'pending'
            AND completed_attempt_id IS NULL
        )
        OR
        (
            status = 'completed'
            AND completed_attempt_id IS NOT NULL
        )
    ),
    FOREIGN KEY (
        assessment_item_id,
        item_revision
    )
    REFERENCES assessment_items_v02 (
        assessment_item_id,
        revision
    ),
    FOREIGN KEY (
        completed_attempt_id
    )
    REFERENCES student_attempts_v02 (
        attempt_id
    )
)
"""


def insert_assignment(
    connection,
    *,
    assignment_id,
    decision_id,
    session_id="session-001",
    status="pending",
    completed_attempt_id=None,
    pending_session_key=None,
    current_schema=False,
):
    columns = """
        assignment_id,
        decision_id,
        student_id,
        course_id,
        objective_id,
        session_id,
        assessment_item_id,
        item_revision,
        assigned_at_utc,
        status,
        completed_attempt_id
    """

    values = [
        assignment_id,
        decision_id,
        "student-001",
        "course-001",
        "objective-001",
        session_id,
        "item-001",
        1,
        "2026-09-19T00:00:00+00:00",
        status,
        completed_attempt_id,
    ]

    if current_schema:
        columns += ", pending_session_key"
        values.append(pending_session_key)

    placeholders = ", ".join("?" for _ in values)

    connection.execute(
        f"""
        INSERT INTO numeric_assignments_v01 (
            {columns}
        )
        VALUES ({placeholders})
        """,
        values,
    )


def create_legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")

        connection.executescript(
            """
            CREATE TABLE assessment_items_v02 (
                assessment_item_id VARCHAR(128) NOT NULL,
                revision INTEGER NOT NULL,
                PRIMARY KEY (assessment_item_id, revision)
            );

            CREATE TABLE student_attempts_v02 (
                attempt_id VARCHAR(128) NOT NULL PRIMARY KEY
            );
            """
        )

        connection.execute(
            """
            INSERT INTO assessment_items_v02
            (assessment_item_id, revision)
            VALUES ('item-001', 1)
            """
        )

        connection.execute(
            """
            INSERT INTO student_attempts_v02
            (attempt_id)
            VALUES ('attempt-001')
            """
        )

        connection.execute(LEGACY_ASSIGNMENT_DDL)

        insert_assignment(
            connection,
            assignment_id="assignment-001",
            decision_id="decision-001",
        )


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "urpp_legacy.sqlite"
    create_legacy_database(path)
    return path


def test_default_check_does_not_change_legacy_database(
    database,
):
    result = migrate(database)

    assert "READ-ONLY CHECK: legacy schema" in result

    with sqlite3.connect(database) as connection:
        assert "pending_session_key" not in {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(numeric_assignments_v01)"
            )
        }


def test_apply_requires_explicit_new_backup(database):
    with pytest.raises(
        MigrationSafetyError,
        match="requires --backup",
    ):
        migrate(database, apply=True)

    assert "legacy schema" in migrate(database)


def test_migration_preserves_rows_and_backup(database, tmp_path):
    backup = tmp_path / "urpp_legacy_backup.sqlite"

    result = migrate(
        database,
        apply=True,
        backup_path=backup,
    )

    assert "MIGRATION COMPLETE" in result
    assert backup.is_file()

    with sqlite3.connect(database) as connection:
        assert inspect(connection) == ("current", 1)

        row = connection.execute(
            """
            SELECT status, pending_session_key
            FROM numeric_assignments_v01
            WHERE assignment_id = 'assignment-001'
            """
        ).fetchone()

        assert row == ("pending", "session-001")

    with sqlite3.connect(backup) as connection:
        assert inspect(connection) == ("legacy", 1)


def test_pending_uniqueness_and_slot_release(
    database,
    tmp_path,
):
    migrate(
        database,
        apply=True,
        backup_path=tmp_path / "backup.sqlite",
    )

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")

        with pytest.raises(sqlite3.IntegrityError):
            insert_assignment(
                connection,
                assignment_id="assignment-002",
                decision_id="decision-002",
                pending_session_key="session-001",
                current_schema=True,
            )

        connection.execute(
            """
            UPDATE numeric_assignments_v01
            SET
                status = 'completed',
                completed_attempt_id = 'attempt-001',
                pending_session_key = NULL
            WHERE assignment_id = 'assignment-001'
            """
        )

        insert_assignment(
            connection,
            assignment_id="assignment-002",
            decision_id="decision-002",
            pending_session_key="session-001",
            current_schema=True,
        )

        assert inspect(connection) == ("current", 2)


def test_decision_id_is_unique_after_completion(
    database,
    tmp_path,
):
    migrate(
        database,
        apply=True,
        backup_path=tmp_path / "backup.sqlite",
    )

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")

        connection.execute(
            """
            UPDATE numeric_assignments_v01
            SET
                status = 'completed',
                completed_attempt_id = 'attempt-001',
                pending_session_key = NULL
            WHERE assignment_id = 'assignment-001'
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            insert_assignment(
                connection,
                assignment_id="assignment-002",
                decision_id="decision-001",
                pending_session_key="session-001",
                current_schema=True,
            )


def test_trigger_rejects_wrong_pending_session_key(
    database,
    tmp_path,
):
    migrate(
        database,
        apply=True,
        backup_path=tmp_path / "backup.sqlite",
    )

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE numeric_assignments_v01
                SET pending_session_key = 'another-session'
                WHERE assignment_id = 'assignment-001'
                """
            )

        assert inspect(connection) == ("current", 1)


def test_duplicate_pending_legacy_rows_stop_migration(
    database,
    tmp_path,
):
    with sqlite3.connect(database) as connection:
        insert_assignment(
            connection,
            assignment_id="assignment-002",
            decision_id="decision-002",
        )

    backup = tmp_path / "backup.sqlite"

    with pytest.raises(
        MigrationSafetyError,
        match="Multiple pending assignments",
    ):
        migrate(
            database,
            apply=True,
            backup_path=backup,
        )

    assert not backup.exists()


def test_duplicate_decision_legacy_rows_stop_migration(
    database,
    tmp_path,
):
    with sqlite3.connect(database) as connection:
        insert_assignment(
            connection,
            assignment_id="assignment-002",
            decision_id="decision-001",
            session_id="session-002",
            status="completed",
            completed_attempt_id="attempt-001",
        )

        # This second row is valid by itself, but duplicates
        # the first row's decision ID once moved to the same session.
        connection.execute(
            """
            UPDATE numeric_assignments_v01
            SET session_id = 'session-001'
            WHERE assignment_id = 'assignment-002'
            """
        )

    with pytest.raises(
        MigrationSafetyError,
        match="Repeated decision ID",
    ):
        migrate(
            database,
            apply=True,
            backup_path=tmp_path / "backup.sqlite",
        )


def test_current_migration_is_idempotent(
    database,
    tmp_path,
):
    backup = tmp_path / "first_backup.sqlite"

    migrate(
        database,
        apply=True,
        backup_path=backup,
    )

    result = migrate(
        database,
        apply=True,
    )

    assert "ALREADY CURRENT" in result
    assert inspect(sqlite3.connect(database)) == ("current", 1)


def test_refuses_missing_database_without_creating_one(
    tmp_path,
):
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(
        MigrationSafetyError,
        match="does not exist",
    ):
        migrate(missing)

    assert not missing.exists()

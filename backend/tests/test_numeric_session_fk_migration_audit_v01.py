"""
URPP Design 01D — Session FK Migration Audit tests.

All databases in this file are synthetic and temporary.

The test suite does not inspect or modify the user's
actual database.
"""

import sqlite3

from pathlib import Path

import pytest

from sqlalchemy import create_engine

from app.repositories.assessment_records_v02 import Base

import app.repositories.numeric_assignment_v01
import app.repositories.numeric_session_records_v01

from app.repositories.migrate_numeric_assignment_v01_sqlite import (
    migrate,
)

from app.repositories.audit_numeric_session_fk_migration_v01 import (
    SessionFKMigrationAuditError,
    audit_sqlite_session_fk_migration,
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


def create_pre09_database(
    path: Path,
    *,
    include_session=True,
    session_student="student-001",
    session_start="2026-09-18T00:00:00+00:00",
):
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")

        connection.executescript(
            """
            CREATE TABLE assessment_items_v02 (
                assessment_item_id VARCHAR(128) NOT NULL,
                revision INTEGER NOT NULL,
                PRIMARY KEY (
                    assessment_item_id,
                    revision
                )
            );

            CREATE TABLE student_attempts_v02 (
                attempt_id VARCHAR(128) NOT NULL PRIMARY KEY
            );

            CREATE TABLE numeric_teaching_sessions_v01 (
                session_id VARCHAR(128) NOT NULL PRIMARY KEY,
                student_id VARCHAR(128) NOT NULL,
                course_id VARCHAR(128) NOT NULL,
                objective_id VARCHAR(128) NOT NULL,
                started_at_utc VARCHAR(48) NOT NULL
            );

            INSERT INTO assessment_items_v02 (
                assessment_item_id,
                revision
            ) VALUES ('item-001', 1);
            """
        )

        connection.execute(LEGACY_ASSIGNMENT_DDL)

        if include_session:
            connection.execute(
                """
                INSERT INTO numeric_teaching_sessions_v01
                (
                    session_id,
                    student_id,
                    course_id,
                    objective_id,
                    started_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "session-001",
                    session_student,
                    "course-001",
                    "objective-001",
                    session_start,
                ),
            )

        connection.execute(
            """
            INSERT INTO numeric_assignments_v01
            (
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
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "assignment-001",
                "decision-001",
                "student-001",
                "course-001",
                "objective-001",
                "session-001",
                "item-001",
                1,
                "2026-09-19T00:00:00+00:00",
                "pending",
                None,
            ),
        )


def upgrade_to_post09(path: Path):
    backup = path.with_name(
        path.stem + "_pre09_backup.sqlite"
    )

    migrate(
        path,
        apply=True,
        backup_path=backup,
    )

    assert backup.is_file()


@pytest.fixture
def pre09_database(tmp_path):
    path = tmp_path / "pre09.sqlite"

    create_pre09_database(path)

    return path


@pytest.fixture
def post12b_database(tmp_path):
    path = tmp_path / "post12b.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    Base.metadata.create_all(engine)

    engine.dispose()

    return path


def test_pre09_schema_is_not_mistaken_for_12b(
    pre09_database,
):
    result = audit_sqlite_session_fk_migration(
        pre09_database
    )

    assert result.schema_stage == "pre-09"
    assert result.assignment_count == 1


def test_valid_post09_records_are_a_migration_candidate(
    pre09_database,
):
    upgrade_to_post09(pre09_database)

    result = audit_sqlite_session_fk_migration(
        pre09_database
    )

    assert result.schema_stage == "post-09/pre-12B"
    assert result.assignment_count == 1
    assert result.session_count == 1
    assert "NOT an upgraded database" in result.result


def test_orphan_assignment_blocks_migration(
    tmp_path,
):
    path = tmp_path / "orphan.sqlite"

    create_pre09_database(
        path,
        include_session=False,
    )

    upgrade_to_post09(path)

    with pytest.raises(
        SessionFKMigrationAuditError,
        match="missing Teaching Session",
    ):
        audit_sqlite_session_fk_migration(path)


def test_student_scope_mismatch_blocks_migration(
    tmp_path,
):
    path = tmp_path / "wrong_student.sqlite"

    create_pre09_database(
        path,
        session_student="another-student",
    )

    upgrade_to_post09(path)

    with pytest.raises(
        SessionFKMigrationAuditError,
        match="inconsistent",
    ):
        audit_sqlite_session_fk_migration(path)


def test_assignment_predating_session_blocks_migration(
    tmp_path,
):
    path = tmp_path / "wrong_time.sqlite"

    create_pre09_database(
        path,
        session_start="2026-09-20T00:00:00+00:00",
    )

    upgrade_to_post09(path)

    with pytest.raises(
        SessionFKMigrationAuditError,
        match="predates",
    ):
        audit_sqlite_session_fk_migration(path)


def test_fresh_12b_database_is_distinguished_from_post09(
    post12b_database,
):
    result = audit_sqlite_session_fk_migration(
        post12b_database
    )

    assert result.schema_stage == "post-12B"
    assert result.assignment_count == 0


def test_12b_database_with_unbound_assignment_is_rejected(
    post12b_database,
):
    with sqlite3.connect(post12b_database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")

        connection.execute(
            """
            INSERT INTO assessment_items_v02
            (
                assessment_item_id,
                revision,
                item_type,
                payload
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "item-001",
                1,
                "numeric",
                "{}",
            ),
        )

        connection.execute(
            """
            INSERT INTO numeric_teaching_sessions_v01
            (
                session_id,
                student_id,
                course_id,
                objective_id,
                started_at_utc
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "session-001",
                "student-001",
                "course-001",
                "objective-001",
                "2026-09-18T00:00:00+00:00",
            ),
        )

        connection.execute(
            """
            INSERT INTO numeric_assignments_v01
            (
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
                pending_session_key,
                registered_session_id,
                completed_attempt_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "assignment-001",
                "decision-001",
                "student-001",
                "course-001",
                "objective-001",
                "session-001",
                "item-001",
                1,
                "2026-09-19T00:00:00+00:00",
                "pending",
                "session-001",
                None,
                None,
            ),
        )

    with pytest.raises(
        SessionFKMigrationAuditError,
        match="Legacy unbound assignments",
    ):
        audit_sqlite_session_fk_migration(
            post12b_database
        )


def test_missing_database_is_never_created(
    tmp_path,
):
    path = tmp_path / "does_not_exist.sqlite"

    with pytest.raises(
        SessionFKMigrationAuditError,
        match="does not exist",
    ):
        audit_sqlite_session_fk_migration(path)

    assert not path.exists()

"""
URPP Design 01D — SQLite Session FK Schema Migration tests.

Every database here is created under pytest's temporary
directory. No real application database is used.
"""

import sqlite3

from pathlib import Path

import pytest

from sqlalchemy import create_engine

from app.repositories.assessment_records_v02 import Base

import app.repositories.numeric_assignment_v01
import app.repositories.numeric_session_records_v01

import app.repositories.migrate_numeric_session_fk_v01_sqlite as migration

from app.repositories.migrate_numeric_session_fk_v01_sqlite import (
    SessionFKSchemaMigrationError,
    migrate_sqlite_session_fk,
)

from app.repositories.numeric_database_readiness_v01 import (
    check_sqlite_numeric_database,
)

from app.repositories.audit_numeric_session_fk_migration_v01 import (
    audit_sqlite_session_fk_migration,
)

from test_numeric_session_fk_migration_audit_v01 import (
    create_pre09_database,
    upgrade_to_post09,
)


@pytest.fixture
def post09_database(tmp_path):
    path = tmp_path / "post09.sqlite"

    create_pre09_database(path)

    upgrade_to_post09(path)

    return path


def _columns(path: Path):
    with sqlite3.connect(path) as connection:
        return {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(numeric_assignments_v01)"
            )
        }


def _assignment_rows(path: Path):
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT
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
                completed_attempt_id
            FROM numeric_assignments_v01
            ORDER BY assignment_id
            """
        ).fetchall()


def test_default_audit_never_upgrades_database(
    post09_database,
):
    before = _assignment_rows(
        post09_database
    )

    result = migrate_sqlite_session_fk(
        post09_database
    )

    assert "READ-ONLY AUDIT" in result

    assert "registered_session_id" not in _columns(
        post09_database
    )

    assert _assignment_rows(
        post09_database
    ) == before


def test_explicit_upgrade_requires_new_backup(
    post09_database,
):
    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="requires --backup",
    ):
        migrate_sqlite_session_fk(
            post09_database,
            apply=True,
        )

    assert "registered_session_id" not in _columns(
        post09_database
    )


def test_upgrade_preserves_rows_and_backup(
    post09_database,
    tmp_path,
):
    before = _assignment_rows(
        post09_database
    )

    backup = tmp_path / "before_12b.sqlite"

    result = migrate_sqlite_session_fk(
        post09_database,
        apply=True,
        backup_path=backup,
    )

    assert "MIGRATION COMPLETE" in result
    assert backup.is_file()

    assert _assignment_rows(
        post09_database
    ) == before

    assert "registered_session_id" in _columns(
        post09_database
    )

    with sqlite3.connect(
        post09_database
    ) as connection:
        bound_id = connection.execute(
            """
            SELECT registered_session_id
            FROM numeric_assignments_v01
            WHERE assignment_id = 'assignment-001'
            """
        ).fetchone()[0]

        assert bound_id == "session-001"

        assert connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall() == []

    readiness = check_sqlite_numeric_database(
        post09_database
    )

    assert readiness.schema_version == "current"
    assert readiness.assignment_count == 1

    final_audit = audit_sqlite_session_fk_migration(
        post09_database
    )

    assert final_audit.schema_stage == "post-12B"

    backup_audit = audit_sqlite_session_fk_migration(
        backup
    )

    assert backup_audit.schema_stage == "post-09/pre-12B"


def test_upgraded_database_enforces_session_fk(
    post09_database,
    tmp_path,
):
    migrate_sqlite_session_fk(
        post09_database,
        apply=True,
        backup_path=tmp_path / "backup.sqlite",
    )

    with sqlite3.connect(
        post09_database
    ) as connection:
        connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        with pytest.raises(
            sqlite3.IntegrityError
        ):
            connection.execute(
                """
                DELETE FROM numeric_teaching_sessions_v01
                WHERE session_id = 'session-001'
                """
            )

        with pytest.raises(
            sqlite3.IntegrityError
        ):
            connection.execute(
                """
                UPDATE numeric_assignments_v01
                SET student_id = 'different-student'
                WHERE assignment_id = 'assignment-001'
                """
            )


def test_existing_backup_is_never_overwritten(
    post09_database,
    tmp_path,
):
    backup = tmp_path / "existing_backup.sqlite"
    backup.write_bytes(b"do-not-overwrite")

    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="already exists",
    ):
        migrate_sqlite_session_fk(
            post09_database,
            apply=True,
            backup_path=backup,
        )

    assert backup.read_bytes() == b"do-not-overwrite"

    assert "registered_session_id" not in _columns(
        post09_database
    )


def test_pre09_database_is_not_silently_chained(
    tmp_path,
):
    path = tmp_path / "pre09.sqlite"

    create_pre09_database(path)

    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="Implementation-09 migration is required",
    ):
        migrate_sqlite_session_fk(
            path,
            apply=True,
            backup_path=tmp_path / "backup.sqlite",
        )

    assert not (
        tmp_path / "backup.sqlite"
    ).exists()


def test_orphan_assignment_blocks_upgrade(
    tmp_path,
):
    path = tmp_path / "orphan.sqlite"

    create_pre09_database(
        path,
        include_session=False,
    )

    upgrade_to_post09(path)

    with pytest.raises(
        migration.SessionFKMigrationAuditError,
        match="missing Teaching Session",
    ):
        migrate_sqlite_session_fk(
            path,
            apply=True,
            backup_path=tmp_path / "backup.sqlite",
        )

    assert "registered_session_id" not in _columns(
        path
    )


def test_scope_mismatch_blocks_upgrade(
    tmp_path,
):
    path = tmp_path / "scope_mismatch.sqlite"

    create_pre09_database(
        path,
        session_student="another-student",
    )

    upgrade_to_post09(path)

    with pytest.raises(
        migration.SessionFKMigrationAuditError,
        match="inconsistent",
    ):
        migrate_sqlite_session_fk(
            path,
            apply=True,
            backup_path=tmp_path / "backup.sqlite",
        )

    assert "registered_session_id" not in _columns(
        path
    )


def test_inbound_foreign_key_blocks_table_rebuild(
    post09_database,
    tmp_path,
):
    with sqlite3.connect(
        post09_database
    ) as connection:
        connection.execute(
            """
            CREATE TABLE assignment_links (
                link_id INTEGER PRIMARY KEY,
                assignment_id VARCHAR(128),
                FOREIGN KEY (assignment_id)
                    REFERENCES numeric_assignments_v01(
                        assignment_id
                    )
            )
            """
        )

    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="Another table references",
    ):
        migrate_sqlite_session_fk(
            post09_database,
            apply=True,
            backup_path=tmp_path / "backup.sqlite",
        )

    assert "registered_session_id" not in _columns(
        post09_database
    )


def test_failed_transaction_restores_source_schema(
    post09_database,
    tmp_path,
    monkeypatch,
):
    before = _assignment_rows(
        post09_database
    )

    backup = tmp_path / "rollback_backup.sqlite"

    def fail_verification(_connection, _expected_count):
        raise SessionFKSchemaMigrationError(
            "Injected verification failure"
        )

    monkeypatch.setattr(
        migration,
        "_verify_rebuilt_table",
        fail_verification,
    )

    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="Injected verification failure",
    ):
        migrate_sqlite_session_fk(
            post09_database,
            apply=True,
            backup_path=backup,
        )

    assert backup.is_file()

    assert "registered_session_id" not in _columns(
        post09_database
    )

    assert _assignment_rows(
        post09_database
    ) == before

    with sqlite3.connect(
        post09_database
    ) as connection:
        shadow = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (
                migration.SHADOW_TABLE,
            ),
        ).fetchone()

        assert shadow is None


def test_migration_is_idempotent_after_upgrade(
    post09_database,
    tmp_path,
):
    migrate_sqlite_session_fk(
        post09_database,
        apply=True,
        backup_path=tmp_path / "first_backup.sqlite",
    )

    second_backup = (
        tmp_path / "unnecessary_second_backup.sqlite"
    )

    result = migrate_sqlite_session_fk(
        post09_database,
        apply=True,
        backup_path=second_backup,
    )

    assert "ALREADY UPGRADED" in result
    assert not second_backup.exists()


def test_missing_database_is_not_created(
    tmp_path,
):
    path = tmp_path / "missing.sqlite"

    with pytest.raises(
        SessionFKSchemaMigrationError,
        match="does not exist",
    ):
        migrate_sqlite_session_fk(
            path
        )

    assert not path.exists()

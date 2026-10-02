"""
URPP Design 01D — Numeric Assignment SQLite Migration V0.1.

Upgrades the legacy numeric_assignments_v01 table to support:
- one pending assignment per session;
- one use of each decision ID per session;
- a pending_session_key consistent with assignment status.

This migration targets the SQLite schema that existed immediately
before Design 01D Implementation 09.

It does not support PostgreSQL or arbitrary SQLite schemas.

Operational requirements:
- Stop the application and all other database writers first.
- Inspect the database using the default read-only check.
- Supply a NEW backup path when explicitly applying the migration.
- Keep the backup until the upgraded application is verified.

SQLite ALTER TABLE cannot directly add the replacement CHECK
constraint used by SQLAlchemy's fresh schema. For an upgraded
legacy database, two triggers enforce the same pending-key
consistency rule. Freshly created databases continue to use
the CHECK constraint defined by the SQLAlchemy model.
"""

import argparse
import sqlite3

from pathlib import Path


TABLE = "numeric_assignments_v01"

PENDING_INDEX = (
    "uq_numeric_assignment_pending_session_v01"
)

DECISION_INDEX = (
    "uq_numeric_assignment_session_decision_v01"
)

INSERT_TRIGGER = (
    "trg_numeric_assignment_status_insert_v01"
)

UPDATE_TRIGGER = (
    "trg_numeric_assignment_status_update_v01"
)

LEGACY_COLUMNS = {
    "assignment_id",
    "decision_id",
    "student_id",
    "course_id",
    "objective_id",
    "session_id",
    "assessment_item_id",
    "item_revision",
    "assigned_at_utc",
    "status",
    "completed_attempt_id",
}


class MigrationSafetyError(RuntimeError):
    """The database is not safe to migrate automatically."""


def _scalar(connection: sqlite3.Connection, sql: str):
    row = connection.execute(sql).fetchone()
    return None if row is None else row[0]


def _require_database(path: str | Path) -> Path:
    database = Path(path).expanduser().absolute()

    if not database.is_file():
        raise MigrationSafetyError(
            f"Database file does not exist: {database}"
        )

    if database.is_symlink():
        raise MigrationSafetyError(
            "Refusing to migrate a database through a symbolic link."
        )

    return database


def _check_database_health(connection: sqlite3.Connection) -> None:
    result = _scalar(connection, "PRAGMA quick_check")

    if result != "ok":
        raise MigrationSafetyError(
            f"SQLite quick_check failed: {result}"
        )

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if foreign_key_errors:
        raise MigrationSafetyError(
            "Existing foreign-key violations were found. "
            "Resolve them before migration."
        )


def _table_sql(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'table' AND name = ?",
        (TABLE,),
    ).fetchone()

    if row is None or not row[0]:
        raise MigrationSafetyError(
            f"Required table {TABLE} was not found."
        )

    return row[0]


def _columns(connection: sqlite3.Connection) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({TABLE})"
        )
    }


def _unique_column_sets(
    connection: sqlite3.Connection,
) -> set[tuple[str, ...]]:
    unique_columns = set()

    for index in connection.execute(
        f"PRAGMA index_list({TABLE})"
    ):
        # PRAGMA index_list:
        # sequence, name, unique, origin, partial
        if index[2] != 1:
            continue

        index_name = index[1].replace('"', '""')

        columns = tuple(
            row[2]
            for row in connection.execute(
                f'PRAGMA index_info("{index_name}")'
            )
        )

        unique_columns.add(columns)

    return unique_columns


def _validate_rows(
    connection: sqlite3.Connection,
    *,
    current_schema: bool,
) -> int:
    invalid_statuses = _scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {TABLE}
        WHERE status NOT IN ('pending', 'completed')
           OR status IS NULL
           OR (
                status = 'pending'
                AND completed_attempt_id IS NOT NULL
           )
           OR (
                status = 'completed'
                AND completed_attempt_id IS NULL
           )
        """,
    )

    if invalid_statuses:
        raise MigrationSafetyError(
            f"Found {invalid_statuses} assignments with "
            "invalid status/completed-attempt combinations."
        )

    duplicate_pending = connection.execute(
        f"""
        SELECT session_id, COUNT(*)
        FROM {TABLE}
        WHERE status = 'pending'
        GROUP BY session_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()

    if duplicate_pending:
        raise MigrationSafetyError(
            "Multiple pending assignments exist in session "
            f"{duplicate_pending[0]!r}. "
            "Manual reconciliation is required."
        )

    duplicate_decision = connection.execute(
        f"""
        SELECT session_id, decision_id, COUNT(*)
        FROM {TABLE}
        GROUP BY session_id, decision_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()

    if duplicate_decision:
        raise MigrationSafetyError(
            "Repeated decision ID exists in session "
            f"{duplicate_decision[0]!r}: "
            f"{duplicate_decision[1]!r}. "
            "Manual reconciliation is required."
        )

    if current_schema:
        invalid_keys = _scalar(
            connection,
            f"""
            SELECT COUNT(*)
            FROM {TABLE}
            WHERE (
                status = 'pending'
                AND (
                    pending_session_key IS NULL
                    OR pending_session_key != session_id
                )
            )
            OR (
                status = 'completed'
                AND pending_session_key IS NOT NULL
            )
            """,
        )

        if invalid_keys:
            raise MigrationSafetyError(
                f"Found {invalid_keys} assignments with "
                "inconsistent pending_session_key values."
            )

    return _scalar(
        connection,
        f"SELECT COUNT(*) FROM {TABLE}",
    )


def inspect(
    connection: sqlite3.Connection,
) -> tuple[str, int]:
    """
    Return ('legacy'|'current', assignment_count).

    Refuse unknown or partially upgraded schema states.
    """

    _check_database_health(connection)

    table_sql = _table_sql(connection)
    columns = _columns(connection)

    if not LEGACY_COLUMNS.issubset(columns):
        raise MigrationSafetyError(
            "Assignment table does not match the expected "
            "legacy schema."
        )

    if "numeric_assignment_status_consistency" not in table_sql:
        raise MigrationSafetyError(
            "Expected legacy assignment CHECK constraint "
            "was not found."
        )

    foreign_key_targets = {
        row[2]
        for row in connection.execute(
            f"PRAGMA foreign_key_list({TABLE})"
        )
    }

    if not {
        "assessment_items_v02",
        "student_attempts_v02",
    }.issubset(foreign_key_targets):
        raise MigrationSafetyError(
            "Expected assignment foreign keys were not found."
        )

    current_schema = "pending_session_key" in columns

    if not current_schema:
        unexpected_columns = columns - LEGACY_COLUMNS

        if unexpected_columns:
            raise MigrationSafetyError(
                "Legacy assignment table contains unexpected "
                f"columns: {sorted(unexpected_columns)}"
            )

        count = _validate_rows(
            connection,
            current_schema=False,
        )

        return "legacy", count

    unique_columns = _unique_column_sets(connection)

    if ("pending_session_key",) not in unique_columns:
        raise MigrationSafetyError(
            "Current schema is missing the unique "
            "pending_session_key constraint."
        )

    if ("session_id", "decision_id") not in unique_columns:
        raise MigrationSafetyError(
            "Current schema is missing the unique "
            "session/decision constraint."
        )

    # Fresh SQLAlchemy-created tables have the updated CHECK.
    # Upgraded legacy tables enforce it with these triggers.
    fresh_check = (
        "pending_session_key" in table_sql
        and "numeric_assignment_status_consistency" in table_sql
    )

    trigger_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'trigger' AND tbl_name = ?",
            (TABLE,),
        )
    }

    migrated_triggers = {
        INSERT_TRIGGER,
        UPDATE_TRIGGER,
    }.issubset(trigger_names)

    if not fresh_check and not migrated_triggers:
        raise MigrationSafetyError(
            "Current schema has no recognized pending-key "
            "consistency enforcement."
        )

    count = _validate_rows(
        connection,
        current_schema=True,
    )

    return "current", count


def _install_consistency_triggers(
    connection: sqlite3.Connection,
) -> None:
    valid_new_row = """
        COALESCE(
            (
                (
                    NEW.status = 'pending'
                    AND NEW.completed_attempt_id IS NULL
                    AND NEW.pending_session_key IS NOT NULL
                    AND NEW.pending_session_key = NEW.session_id
                )
                OR
                (
                    NEW.status = 'completed'
                    AND NEW.completed_attempt_id IS NOT NULL
                    AND NEW.pending_session_key IS NULL
                )
            ),
            0
        ) = 1
    """

    connection.execute(
        f"""
        CREATE TRIGGER {INSERT_TRIGGER}
        BEFORE INSERT ON {TABLE}
        WHEN NOT ({valid_new_row})
        BEGIN
            SELECT RAISE(
                ABORT,
                'Invalid numeric assignment status or pending key'
            );
        END
        """
    )

    connection.execute(
        f"""
        CREATE TRIGGER {UPDATE_TRIGGER}
        BEFORE UPDATE ON {TABLE}
        WHEN NOT ({valid_new_row})
        BEGIN
            SELECT RAISE(
                ABORT,
                'Invalid numeric assignment status or pending key'
            );
        END
        """
    )


def migrate(
    database_path: str | Path,
    *,
    apply: bool = False,
    backup_path: str | Path | None = None,
) -> str:
    """
    Inspect a SQLite database or explicitly apply the migration.

    Default: read-only inspection.

    Apply:
    - requires a new backup path;
    - writes a consistent SQLite backup;
    - obtains an exclusive transaction;
    - validates data before altering the schema;
    - changes schema and existing rows in one transaction.

    The application must be stopped before apply=True.
    """

    database = _require_database(database_path)

    # Using mode=ro avoids accidentally creating or modifying
    # the database during the default inspection.
    if not apply:
        connection = sqlite3.connect(
            database.as_uri() + "?mode=ro",
            uri=True,
            timeout=5,
        )

        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA query_only=ON")

            version, count = inspect(connection)

            return (
                f"READ-ONLY CHECK: {version} schema; "
                f"{count} assignments. No changes made."
            )

        finally:
            connection.close()

    connection = sqlite3.connect(
        str(database),
        isolation_level=None,
        timeout=5,
    )

    backup: Path | None = None

    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

        version, count = inspect(connection)

        if version == "current":
            return (
                f"ALREADY CURRENT: {count} assignments. "
                "No migration or backup needed."
            )

        if backup_path is None:
            raise MigrationSafetyError(
                "Applying the migration requires --backup "
                "with a new backup-file path."
            )

        backup = Path(
            backup_path
        ).expanduser().absolute()

        if backup == database:
            raise MigrationSafetyError(
                "Backup path cannot equal database path."
            )

        if backup.exists() or backup.is_symlink():
            raise MigrationSafetyError(
                "Backup destination already exists. "
                "Choose a new filename; existing backups "
                "will never be overwritten."
            )

        if not backup.parent.is_dir():
            raise MigrationSafetyError(
                "Backup parent directory does not exist."
            )

        # Detect writes by another SQLite connection between
        # the backup and acquisition of the exclusive lock.
        # This supplements, but does not replace, the requirement
        # to stop the application before migrating.
        version_before_backup = _scalar(
            connection,
            "PRAGMA data_version",
        )

        # Reserve the filename without overwriting an existing file.
        with backup.open("xb"):
            pass

        backup_connection = sqlite3.connect(
            str(backup),
            timeout=5,
        )

        try:
            connection.backup(backup_connection)

            backup_version, backup_count = inspect(
                backup_connection
            )

            if (
                backup_version != "legacy"
                or backup_count != count
            ):
                raise MigrationSafetyError(
                    "Backup validation did not match "
                    "the original database."
                )

        finally:
            backup_connection.close()

        try:
            connection.execute("BEGIN EXCLUSIVE")

            if (
                _scalar(connection, "PRAGMA data_version")
                != version_before_backup
            ):
                raise MigrationSafetyError(
                    "Database changed while preparing the backup. "
                    "Stop all writers and retry with a NEW "
                    "backup filename."
                )

            locked_version, locked_count = inspect(
                connection
            )

            if (
                locked_version != "legacy"
                or locked_count != count
            ):
                raise MigrationSafetyError(
                    "Database changed before the migration lock."
                )

            connection.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN pending_session_key VARCHAR(128)
                """
            )

            connection.execute(
                f"""
                UPDATE {TABLE}
                SET pending_session_key = session_id
                WHERE status = 'pending'
                """
            )

            connection.execute(
                f"""
                CREATE UNIQUE INDEX {PENDING_INDEX}
                ON {TABLE}(pending_session_key)
                """
            )

            connection.execute(
                f"""
                CREATE UNIQUE INDEX {DECISION_INDEX}
                ON {TABLE}(session_id, decision_id)
                """
            )

            _install_consistency_triggers(connection)

            new_version, new_count = inspect(connection)

            if new_version != "current" or new_count != count:
                raise MigrationSafetyError(
                    "Post-migration verification failed."
                )

            connection.execute("COMMIT")

        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

        final_version, final_count = inspect(connection)

        if final_version != "current" or final_count != count:
            raise MigrationSafetyError(
                "Migration committed, but final verification failed. "
                "Stop the application and investigate."
            )

        return (
            f"MIGRATION COMPLETE: {final_count} assignments; "
            f"backup retained at {backup}"
        )

    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or migrate the legacy URPP numeric "
            "assignment SQLite table."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to an existing SQLite database file.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Explicitly upgrade the database. "
            "Stop all application writers first."
        ),
    )

    parser.add_argument(
        "--backup",
        help=(
            "New, nonexistent backup-file path. "
            "Required when a legacy database is upgraded."
        ),
    )

    args = parser.parse_args()

    try:
        result = migrate(
            args.database,
            apply=args.apply,
            backup_path=args.backup,
        )

    except (MigrationSafetyError, sqlite3.Error) as exc:
        parser.exit(
            status=1,
            message=f"STOP: {exc}\n",
        )

    print(result)


if __name__ == "__main__":
    main()

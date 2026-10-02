"""
URPP Design 01D — SQLite Session FK Migration V0.1.

Upgrades an existing post-Implementation-09 / pre-12B
numeric_assignments_v01 table to the 12B schema.

The migration:

1. Requires an existing database.
2. Performs the read-only Session FK migration audit.
3. Requires a new backup path for an explicit upgrade.
4. Creates and verifies a SQLite backup.
5. Acquires a write transaction and repeats critical checks.
6. Rebuilds the Assignment table using the current SQLAlchemy
   model's SQLite CREATE TABLE definition.
7. Binds every existing Assignment to its matching Session.
8. Verifies row preservation, constraints, and FK integrity.
9. Commits only after in-transaction verification.

Default behavior is read-only.

This migration does not:
- create missing Sessions;
- invent or modify student identity or scope;
- repair inconsistent Assignment records;
- support PostgreSQL;
- support arbitrary database schemas;
- permit application writers to run during migration;
- start or configure the application.

IMPORTANT: The application and all other database writers must
be stopped before any explicit migration is attempted.
"""

import argparse
import sqlite3

from pathlib import Path

from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.schema import CreateTable

from app.repositories.assessment_records_v02 import Base

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)

from app.repositories.numeric_session_records_v01 import (
    NumericTeachingSessionRowV01,
)

from app.repositories.audit_numeric_session_fk_migration_v01 import (
    SessionFKMigrationAuditError,
    _has_complete_registered_session_fk,
    audit_sqlite_session_fk_migration,
)

from app.repositories.migrate_numeric_assignment_v01_sqlite import (
    MigrationSafetyError,
    inspect as inspect_pending_key_schema,
)

from app.repositories.numeric_database_readiness_v01 import (
    DatabaseNotReadyError,
    _check_session_assignment_scope,
    check_sqlite_numeric_database,
)


ASSIGNMENT_TABLE = "numeric_assignments_v01"

SESSION_TABLE = "numeric_teaching_sessions_v01"

SHADOW_TABLE = "__urpp_numeric_assignments_new_12c3"

SESSION_UNIQUE_INDEX = (
    "uq_urpp_numeric_session_scope_12c3"
)

SOURCE_COLUMNS = (
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
    "pending_session_key",
    "completed_attempt_id",
)

EXPECTED_SOURCE_COLUMNS = set(SOURCE_COLUMNS)

EXPECTED_SOURCE_INDEXES = {
    "uq_numeric_assignment_pending_session_v01",
    "uq_numeric_assignment_session_decision_v01",
}

EXPECTED_SOURCE_TRIGGERS = {
    "trg_numeric_assignment_status_insert_v01",
    "trg_numeric_assignment_status_update_v01",
}


class SessionFKSchemaMigrationError(RuntimeError):
    """The Session FK schema upgrade cannot proceed safely."""


def _scalar(
    connection: sqlite3.Connection,
    sql: str,
):
    row = connection.execute(sql).fetchone()
    return None if row is None else row[0]


def _existing_database(
    database_path: str | Path,
) -> Path:
    path = Path(database_path).expanduser().absolute()

    if path.is_symlink():
        raise SessionFKSchemaMigrationError(
            "Refusing to migrate through a symbolic link."
        )

    if not path.is_file():
        raise SessionFKSchemaMigrationError(
            "Database does not exist. "
            "This migration never creates application databases."
        )

    return path


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    quoted = _quote_identifier(table_name)

    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({quoted})"
        )
    }


def _unique_column_sets(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[tuple[str, ...]]:
    quoted_table = _quote_identifier(table_name)

    result = set()

    for index in connection.execute(
        f"PRAGMA index_list({quoted_table})"
    ):
        if index[2] != 1:
            continue

        quoted_index = _quote_identifier(index[1])

        columns = tuple(
            row[2]
            for row in connection.execute(
                f"PRAGMA index_info({quoted_index})"
            )
        )

        result.add(columns)

    return result


def _check_source_schema(
    connection: sqlite3.Connection,
) -> int:
    """
    Require exactly the known post-09/pre-12B Assignment
    columns and reject unidentified dependent schema objects.
    """

    version, count = inspect_pending_key_schema(
        connection
    )

    if version != "current":
        raise SessionFKSchemaMigrationError(
            "Implementation-09 migration is required first."
        )

    columns = _table_columns(
        connection,
        ASSIGNMENT_TABLE,
    )

    if columns != EXPECTED_SOURCE_COLUMNS:
        raise SessionFKSchemaMigrationError(
            "Assignment columns do not match the expected "
            "post-09/pre-12B schema."
        )

    if _has_complete_registered_session_fk(connection):
        raise SessionFKSchemaMigrationError(
            "The Assignment table already has a registered "
            "Session FK. Use the Readiness Check instead."
        )

    tables = {
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
    }

    if SHADOW_TABLE in tables:
        raise SessionFKSchemaMigrationError(
            "Migration shadow table already exists. "
            "Manual schema review is required."
        )

    # This implementation does not rewrite inbound foreign
    # keys from other tables during the Assignment table swap.
    for table_name in tables:

        if table_name.startswith("sqlite_"):
            continue

        if table_name == ASSIGNMENT_TABLE:
            continue

        quoted = _quote_identifier(table_name)

        for foreign_key in connection.execute(
            f"PRAGMA foreign_key_list({quoted})"
        ):
            if foreign_key[2] == ASSIGNMENT_TABLE:
                raise SessionFKSchemaMigrationError(
                    "Another table references the Assignment "
                    "table. Automatic table rebuilding is refused."
                )

    # Rebuilding a table discards its manually defined indexes
    # and triggers. Refuse unknown objects rather than losing
    # application-specific behavior.
    indexes = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
          AND tbl_name = ?
          AND sql IS NOT NULL
        """,
        (ASSIGNMENT_TABLE,),
    ).fetchall()

    unexpected_indexes = {
        row[0] for row in indexes
    } - EXPECTED_SOURCE_INDEXES

    if unexpected_indexes:
        raise SessionFKSchemaMigrationError(
            "Assignment table has unexpected indexes: "
            + ", ".join(sorted(unexpected_indexes))
        )

    triggers = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'trigger'
          AND tbl_name = ?
        """,
        (ASSIGNMENT_TABLE,),
    ).fetchall()

    unexpected_triggers = {
        row[0] for row in triggers
    } - EXPECTED_SOURCE_TRIGGERS

    if unexpected_triggers:
        raise SessionFKSchemaMigrationError(
            "Assignment table has unexpected triggers: "
            + ", ".join(sorted(unexpected_triggers))
        )

    # Views and triggers on OTHER tables may depend on the
    # Assignment table even without declaring an FK.
    dependent_objects = connection.execute(
        """
        SELECT type, name
        FROM sqlite_master
        WHERE type IN ('view', 'trigger')
          AND COALESCE(tbl_name, '') != ?
          AND LOWER(COALESCE(sql, ''))
              LIKE '%numeric_assignments_v01%'
        """,
        (ASSIGNMENT_TABLE,),
    ).fetchall()

    if dependent_objects:
        raise SessionFKSchemaMigrationError(
            "Views or external triggers reference the "
            "Assignment table. Manual migration is required."
        )

    # The current ORM uses a four-column composite reference.
    # SQLite requires the parent key to have a matching UNIQUE
    # constraint or UNIQUE index.
    expected_session_columns = {
        "session_id",
        "student_id",
        "course_id",
        "objective_id",
        "started_at_utc",
    }

    if SESSION_TABLE not in tables:
        raise SessionFKSchemaMigrationError(
            "Teaching Session table is missing."
        )

    if _table_columns(
        connection,
        SESSION_TABLE,
    ) != expected_session_columns:
        raise SessionFKSchemaMigrationError(
            "Teaching Session columns do not match "
            "the expected schema."
        )

    _check_session_assignment_scope(
        connection
    )

    return count


def _ensure_session_parent_unique_key(
    connection: sqlite3.Connection,
) -> None:
    expected = (
        "session_id",
        "student_id",
        "course_id",
        "objective_id",
    )

    existing = _unique_column_sets(
        connection,
        SESSION_TABLE,
    )

    if expected in existing:
        return

    connection.execute(
        f"""
        CREATE UNIQUE INDEX
            {SESSION_UNIQUE_INDEX}
        ON {SESSION_TABLE}
        (
            session_id,
            student_id,
            course_id,
            objective_id
        )
        """
    )


def _new_assignment_table_ddl() -> str:
    """
    Compile the currently declared SQLAlchemy Assignment
    model rather than maintaining a second handwritten copy
    of its CHECK, UNIQUE, and FOREIGN KEY definitions.
    """

    table = Base.metadata.tables.get(
        ASSIGNMENT_TABLE
    )

    if table is None:
        raise SessionFKSchemaMigrationError(
            "Current SQLAlchemy Assignment model is missing."
        )

    # Both models are imported above so their FK targets are
    # registered with the shared SQLAlchemy metadata.
    if (
        NumericAssignmentRow.__table__ is not table
        or NumericTeachingSessionRowV01.__table__.name
        != SESSION_TABLE
    ):
        raise SessionFKSchemaMigrationError(
            "Unexpected SQLAlchemy model registration."
        )

    ddl = str(
        CreateTable(table).compile(
            dialect=sqlite_dialect()
        )
    )

    original_header = (
        "CREATE TABLE numeric_assignments_v01"
    )

    if ddl.count(original_header) != 1:
        raise SessionFKSchemaMigrationError(
            "Unexpected SQLAlchemy CREATE TABLE output. "
            "Refusing to rewrite an unrecognized DDL statement."
        )

    return ddl.replace(
        original_header,
        f"CREATE TABLE {SHADOW_TABLE}",
        1,
    )


def _verify_row_copy(
    connection: sqlite3.Connection,
    expected_count: int,
) -> None:
    """
    Compare all original Assignment columns in both directions
    before the old table is dropped.
    """

    source_columns = ", ".join(
        SOURCE_COLUMNS
    )

    copied_count = _scalar(
        connection,
        f"SELECT COUNT(*) FROM {SHADOW_TABLE}",
    )

    if copied_count != expected_count:
        raise SessionFKSchemaMigrationError(
            "Assignment row count changed while copying."
        )

    missing_from_new = connection.execute(
        f"""
        SELECT {source_columns}
        FROM {ASSIGNMENT_TABLE}

        EXCEPT

        SELECT {source_columns}
        FROM {SHADOW_TABLE}

        LIMIT 1
        """
    ).fetchone()

    unexpected_in_new = connection.execute(
        f"""
        SELECT {source_columns}
        FROM {SHADOW_TABLE}

        EXCEPT

        SELECT {source_columns}
        FROM {ASSIGNMENT_TABLE}

        LIMIT 1
        """
    ).fetchone()

    if (
        missing_from_new is not None
        or unexpected_in_new is not None
    ):
        raise SessionFKSchemaMigrationError(
            "Assignment source and copied rows differ."
        )

    unbound = _scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {SHADOW_TABLE}
        WHERE registered_session_id IS NULL
           OR registered_session_id != session_id
        """,
    )

    if unbound:
        raise SessionFKSchemaMigrationError(
            "Not all copied Assignments are bound "
            "to their registered Sessions."
        )


def _verify_rebuilt_table(
    connection: sqlite3.Connection,
    expected_count: int,
) -> None:
    """
    Called BEFORE COMMIT so a verification failure can
    roll back the entire table rebuild.
    """

    version, actual_count = inspect_pending_key_schema(
        connection
    )

    if (
        version != "current"
        or actual_count != expected_count
    ):
        raise SessionFKSchemaMigrationError(
            "Rebuilt Assignment table failed the "
            "existing pending-key schema checks."
        )

    if not _has_complete_registered_session_fk(
        connection
    ):
        raise SessionFKSchemaMigrationError(
            "Rebuilt Assignment table is missing its "
            "Composite Session Foreign Key."
        )

    _check_session_assignment_scope(
        connection
    )

    unbound = _scalar(
        connection,
        f"""
        SELECT COUNT(*)
        FROM {ASSIGNMENT_TABLE}
        WHERE registered_session_id IS NULL
           OR registered_session_id != session_id
        """,
    )

    if unbound:
        raise SessionFKSchemaMigrationError(
            "Rebuilt Assignment table contains "
            "unbound records."
        )

    if _scalar(
        connection,
        "PRAGMA quick_check",
    ) != "ok":
        raise SessionFKSchemaMigrationError(
            "SQLite integrity check failed before commit."
        )

    if connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall():
        raise SessionFKSchemaMigrationError(
            "Foreign-key violations were found before commit."
        )


def migrate_sqlite_session_fk(
    database_path: str | Path,
    *,
    apply: bool = False,
    backup_path: str | Path | None = None,
) -> str:
    """
    Default: read-only audit.

    Explicit apply:
    - requires a new backup path;
    - requires post-09/pre-12B source schema;
    - refuses unmatched legacy Assignment records;
    - requires the application and all database writers
      to be stopped;
    - performs the table rebuild transactionally.

    No application code calls this automatically.
    """

    database = _existing_database(
        database_path
    )

    initial_audit = audit_sqlite_session_fk_migration(
        database
    )

    if initial_audit.schema_stage == "post-12B":
        return (
            "ALREADY UPGRADED: post-12B schema; "
            "no migration or backup needed."
        )

    if initial_audit.schema_stage == "pre-09":
        raise SessionFKSchemaMigrationError(
            "Implementation-09 migration is required first. "
            "This migration does not chain schema upgrades."
        )

    if initial_audit.schema_stage != "post-09/pre-12B":
        raise SessionFKSchemaMigrationError(
            "Unrecognized migration audit result."
        )

    if not apply:
        return (
            "READ-ONLY AUDIT: "
            f"{initial_audit.assignment_count} Assignments; "
            "post-09/pre-12B schema; "
            "existing Session links passed the data audit. "
            "No changes made."
        )

    if backup_path is None:
        raise SessionFKSchemaMigrationError(
            "Applying this migration requires --backup "
            "with a new backup-file path."
        )

    backup = Path(
        backup_path
    ).expanduser().absolute()

    if backup == database:
        raise SessionFKSchemaMigrationError(
            "Backup path cannot equal the database path."
        )

    if backup.exists() or backup.is_symlink():
        raise SessionFKSchemaMigrationError(
            "Backup destination already exists. "
            "Existing backups are never overwritten."
        )

    if not backup.parent.is_dir():
        raise SessionFKSchemaMigrationError(
            "Backup parent directory does not exist."
        )

    connection = sqlite3.connect(
        str(database),
        isolation_level=None,
        timeout=5,
    )

    try:
        connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        connection.execute(
            "PRAGMA busy_timeout=5000"
        )

        if _scalar(
            connection,
            "PRAGMA foreign_keys",
        ) != 1:
            raise SessionFKSchemaMigrationError(
                "SQLite Foreign Key enforcement is disabled."
            )

        # Recheck source schema before generating a backup.
        expected_count = _check_source_schema(
            connection
        )

        data_version = _scalar(
            connection,
            "PRAGMA data_version",
        )

        # Reserve the backup filename. If backup preparation
        # fails, a partial backup file may remain and must
        # not be treated as a verified recovery copy.
        with backup.open("xb"):
            pass

        backup_connection = sqlite3.connect(
            str(backup),
            timeout=5,
        )

        try:
            connection.backup(
                backup_connection
            )

            backup_audit = (
                audit_sqlite_session_fk_migration(
                    backup
                )
            )

            if (
                backup_audit.schema_stage
                != "post-09/pre-12B"
                or backup_audit.assignment_count
                != expected_count
            ):
                raise SessionFKSchemaMigrationError(
                    "Backup verification did not match "
                    "the source database."
                )

        finally:
            backup_connection.close()

        try:
            connection.execute(
                "BEGIN EXCLUSIVE"
            )

            if _scalar(
                connection,
                "PRAGMA data_version",
            ) != data_version:
                raise SessionFKSchemaMigrationError(
                    "Database changed while the backup "
                    "was being prepared. Stop all writers "
                    "and retry with a NEW backup path."
                )

            locked_count = _check_source_schema(
                connection
            )

            if locked_count != expected_count:
                raise SessionFKSchemaMigrationError(
                    "Assignment count changed before migration."
                )

            # Guarantee the exact parent key referenced by
            # the new four-column Composite Foreign Key.
            _ensure_session_parent_unique_key(
                connection
            )

            connection.execute(
                _new_assignment_table_ddl()
            )

            source_columns = ", ".join(
                SOURCE_COLUMNS
            )

            destination_columns = (
                source_columns
                + ", registered_session_id"
            )

            connection.execute(
                f"""
                INSERT INTO {SHADOW_TABLE}
                ({destination_columns})

                SELECT
                    {source_columns},
                    session_id
                FROM {ASSIGNMENT_TABLE}
                """
            )

            _verify_row_copy(
                connection,
                expected_count,
            )

            # There are no incoming FKs or unknown dependent
            # triggers/views at this point, as checked above.
            # Dropping the old table and renaming the new one
            # are both performed inside the same transaction.
            connection.execute(
                f"DROP TABLE {ASSIGNMENT_TABLE}"
            )

            connection.execute(
                f"""
                ALTER TABLE {SHADOW_TABLE}
                RENAME TO {ASSIGNMENT_TABLE}
                """
            )

            _verify_rebuilt_table(
                connection,
                expected_count,
            )

            connection.execute(
                "COMMIT"
            )

        except Exception:
            if connection.in_transaction:
                connection.execute(
                    "ROLLBACK"
                )
            raise

    except (
        sqlite3.Error,
        MigrationSafetyError,
        SessionFKMigrationAuditError,
        DatabaseNotReadyError,
    ) as exc:
        raise SessionFKSchemaMigrationError(
            f"Session FK migration stopped: {exc}"
        ) from exc

    finally:
        connection.close()

    # This verification occurs after commit, using the same
    # public read-only checks available to application startup.
    # If it fails, retain the backup and stop deployment.
    try:
        readiness = check_sqlite_numeric_database(
            database
        )

        final_audit = audit_sqlite_session_fk_migration(
            database
        )

    except (
        DatabaseNotReadyError,
        SessionFKMigrationAuditError,
    ) as exc:
        raise SessionFKSchemaMigrationError(
            "Migration committed, but final readiness "
            "verification failed. Stop the application "
            f"and investigate using the retained backup: {exc}"
        ) from exc

    if (
        readiness.assignment_count != expected_count
        or final_audit.schema_stage != "post-12B"
    ):
        raise SessionFKSchemaMigrationError(
            "Migration committed, but the final row count "
            "or schema stage is unexpected. "
            "Stop the application and retain the backup."
        )

    return (
        "MIGRATION COMPLETE: "
        f"{expected_count} Assignments preserved; "
        "registered Session FK installed; "
        f"backup retained at {backup}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or explicitly upgrade the existing "
            "URPP SQLite Session–Assignment schema."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to an existing SQLite database.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Explicitly apply the migration. "
            "The application and database writers "
            "must be stopped first."
        ),
    )

    parser.add_argument(
        "--backup",
        help=(
            "New, nonexistent backup-file path. "
            "Required when --apply performs an upgrade."
        ),
    )

    args = parser.parse_args()

    try:
        result = migrate_sqlite_session_fk(
            args.database,
            apply=args.apply,
            backup_path=args.backup,
        )

    except SessionFKSchemaMigrationError as exc:
        parser.exit(
            status=1,
            message=f"STOP: {exc}\n",
        )

    print(result)


if __name__ == "__main__":
    main()

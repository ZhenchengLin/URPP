"""
URPP Design 01D — Session FK Migration Audit V0.1.

Read-only inspection of an existing SQLite database.

Distinguishes:
- pre-Implementation-09 Assignment schema;
- post-09 Assignment schema requiring Session FK migration;
- post-12B Assignment schema with a registered Session FK.

For post-09 databases, checks that every existing Assignment
can be associated with an existing Teaching Session with matching
student/course/objective scope and valid time ordering.

This module does NOT:
- migrate a database;
- create missing Sessions;
- change Assignment scope;
- infer student identity;
- establish that a database is safe for production;
- replace the application's full Database Readiness Check.
"""

import argparse
import sqlite3

from dataclasses import dataclass
from pathlib import Path

from app.repositories.migrate_numeric_assignment_v01_sqlite import (
    MigrationSafetyError,
    inspect,
)

from app.repositories.numeric_database_readiness_v01 import (
    DatabaseNotReadyError,
    _check_session_assignment_scope,
    check_sqlite_numeric_database,
)


ASSIGNMENT_TABLE = "numeric_assignments_v01"

SESSION_TABLE = "numeric_teaching_sessions_v01"

REQUIRED_SESSION_COLUMNS = {
    "session_id",
    "student_id",
    "course_id",
    "objective_id",
    "started_at_utc",
}

EXPECTED_SESSION_FK = {
    ("registered_session_id", "session_id"),
    ("student_id", "student_id"),
    ("course_id", "course_id"),
    ("objective_id", "objective_id"),
}


class SessionFKMigrationAuditError(RuntimeError):
    """The database cannot pass this migration audit."""


@dataclass(frozen=True)
class SessionFKMigrationAuditV01:
    schema_stage: str
    assignment_count: int
    session_count: int
    result: str


def _require_existing_database(
    database_path: str | Path,
) -> Path:
    path = Path(database_path).expanduser().absolute()

    if path.is_symlink():
        raise SessionFKMigrationAuditError(
            "Refusing to inspect a symbolic-link database path."
        )

    if not path.is_file():
        raise SessionFKMigrationAuditError(
            "Database file does not exist. "
            "This audit never creates databases."
        )

    return path


def _column_names(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    # table_name is supplied only by internal module constants.
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        )
    }


def _has_complete_registered_session_fk(
    connection: sqlite3.Connection,
) -> bool:
    """
    Require all four FK components to belong to the SAME
    SQLite foreign-key group. Merely finding four independent
    foreign keys is insufficient.
    """

    groups = {}

    for row in connection.execute(
        f"PRAGMA foreign_key_list({ASSIGNMENT_TABLE})"
    ):
        (
            fk_id,
            _sequence,
            target_table,
            source_column,
            target_column,
            on_update,
            on_delete,
            _match,
        ) = row

        if target_table != SESSION_TABLE:
            continue

        group = groups.setdefault(
            fk_id,
            {
                "pairs": set(),
                "on_update": on_update,
                "on_delete": on_delete,
            },
        )

        group["pairs"].add(
            (source_column, target_column)
        )

    return any(
        group["pairs"] == EXPECTED_SESSION_FK
        and group["on_update"] == "RESTRICT"
        and group["on_delete"] == "RESTRICT"
        for group in groups.values()
    )


def audit_sqlite_session_fk_migration(
    database_path: str | Path,
) -> SessionFKMigrationAuditV01:
    """
    Audit an existing database via SQLite mode=ro.

    A positive pre-12B result establishes DATA reconciliation
    only. It does not mean the schema migration has been
    implemented or is ready to execute.
    """

    database = _require_existing_database(
        database_path
    )

    connection = sqlite3.connect(
        database.as_uri() + "?mode=ro",
        uri=True,
        timeout=5,
    )

    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")

        # Reuse the existing Implementation-09 integrity,
        # pending-key, and duplicate-decision checks.
        pending_key_stage, assignment_count = inspect(
            connection
        )

        if pending_key_stage == "legacy":
            return SessionFKMigrationAuditV01(
                schema_stage="pre-09",
                assignment_count=assignment_count,
                session_count=0,
                result=(
                    "Implementation-09 migration is required first. "
                    "No Session-FK migration was attempted."
                ),
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

        if SESSION_TABLE not in tables:
            raise SessionFKMigrationAuditError(
                "Teaching Session table is missing. "
                "Existing Assignments cannot be bound safely."
            )

        session_columns = _column_names(
            connection,
            SESSION_TABLE,
        )

        if not REQUIRED_SESSION_COLUMNS.issubset(
            session_columns
        ):
            raise SessionFKMigrationAuditError(
                "Teaching Session table has an unexpected schema."
            )

        session_count = connection.execute(
            f"SELECT COUNT(*) FROM {SESSION_TABLE}"
        ).fetchone()[0]

        assignment_columns = _column_names(
            connection,
            ASSIGNMENT_TABLE,
        )

        has_binding_column = (
            "registered_session_id" in assignment_columns
        )

        has_binding_fk = (
            _has_complete_registered_session_fk(
                connection
            )
        )

        if has_binding_column != has_binding_fk:
            raise SessionFKMigrationAuditError(
                "Partial or unrecognized registered-session "
                "schema was found. Manual review is required."
            )

        if has_binding_column:
            # An existing post-12B database must pass the
            # full Readiness Check, including detection of
            # legacy unbound Assignments.
            connection.close()

            try:
                check_sqlite_numeric_database(
                    database
                )
            except DatabaseNotReadyError as exc:
                raise SessionFKMigrationAuditError(
                    f"Post-12B database is not ready: {exc}"
                ) from exc

            return SessionFKMigrationAuditV01(
                schema_stage="post-12B",
                assignment_count=assignment_count,
                session_count=session_count,
                result=(
                    "Registered-session schema and existing "
                    "records passed the readiness check. "
                    "No migration was performed."
                ),
            )

        # The pre-12B schema has no registered-session FK.
        # Check whether its existing rows could be bound
        # to registered Sessions without inventing data.
        try:
            _check_session_assignment_scope(
                connection
            )
        except DatabaseNotReadyError as exc:
            raise SessionFKMigrationAuditError(
                "Existing Assignment records require manual "
                f"reconciliation before migration: {exc}"
            ) from exc

        return SessionFKMigrationAuditV01(
            schema_stage="post-09/pre-12B",
            assignment_count=assignment_count,
            session_count=session_count,
            result=(
                "Existing Assignment-to-Session data passed "
                "the scope and time-order audit. "
                "This is a migration candidate, NOT an "
                "upgraded database. The schema migration "
                "has not been implemented or executed."
            ),
        )

    except (
        MigrationSafetyError,
        sqlite3.Error,
    ) as exc:
        raise SessionFKMigrationAuditError(
            f"SQLite audit failed: {exc}"
        ) from exc

    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only pre-migration audit of URPP's "
            "SQLite Session–Assignment relationship."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to an existing SQLite database.",
    )

    args = parser.parse_args()

    try:
        result = audit_sqlite_session_fk_migration(
            args.database
        )

    except SessionFKMigrationAuditError as exc:
        parser.exit(
            status=1,
            message=f"MIGRATION AUDIT STOPPED: {exc}\n",
        )

    print("READ-ONLY SESSION FK MIGRATION AUDIT")
    print("Schema stage:", result.schema_stage)
    print("Assignments:", result.assignment_count)
    print("Teaching Sessions:", result.session_count)
    print("Result:", result.result)
    print("No database changes were made.")


if __name__ == "__main__":
    main()

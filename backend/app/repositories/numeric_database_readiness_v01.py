"""
URPP Design 01D — Numeric Database Readiness V0.1.

Read-only verification of an EXISTING SQLite database.

Checks:
1. All four numeric-assessment tables exist.
2. Assignment schema and its constraints are current.
3. SQLite integrity and foreign-key checks succeed.
4. Every Assignment belongs to an existing Teaching Session.
5. Assignment and Session student/course/objective scopes agree.
6. An Assignment cannot predate its registered Session.

This is a preflight checker, NOT a database initializer.

It does not:
- create a database;
- perform migrations;
- authenticate a student;
- validate every stored response payload;
- establish PostgreSQL concurrency behavior;
- automatically install itself into FastAPI startup.
"""

import argparse
import sqlite3

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.repositories.migrate_numeric_assignment_v01_sqlite import (
    MigrationSafetyError,
    inspect,
)


REQUIRED_TABLES = (
    "assessment_items_v02",
    "student_attempts_v02",
    "numeric_assignments_v01",
    "numeric_teaching_sessions_v01",
)


class DatabaseNotReadyError(RuntimeError):
    """The existing database does not satisfy readiness checks."""


@dataclass(frozen=True)
class NumericDatabaseReadinessV01:
    database_path: str
    schema_version: str
    assessment_item_count: int
    attempt_count: int
    assignment_count: int
    teaching_session_count: int


def _existing_database(path: str | Path) -> Path:
    database = Path(path).expanduser().absolute()

    if database.is_symlink():
        raise DatabaseNotReadyError(
            "Refusing to inspect a database through a symbolic link."
        )

    if not database.is_file():
        raise DatabaseNotReadyError(
            "Database file does not exist. "
            "Readiness checks never create databases."
        )

    return database


def _require_aware_datetime(
    raw_value: str,
    *,
    field_name: str,
) -> datetime:
    try:
        value = datetime.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise DatabaseNotReadyError(
            f"Stored {field_name} is not a valid ISO datetime."
        ) from exc

    if value.tzinfo is None or value.utcoffset() is None:
        raise DatabaseNotReadyError(
            f"Stored {field_name} must be timezone-aware."
        )

    return value


def _check_session_assignment_scope(
    connection: sqlite3.Connection,
) -> None:
    """
    Inspect the Session relationship that the current ORM schema
    does not yet enforce through a database foreign key.

    This is a read-only audit of existing records. A later
    implementation must add write-time referential enforcement.
    """

    rows = connection.execute(
        """
        SELECT
            a.student_id,
            a.course_id,
            a.objective_id,
            a.assigned_at_utc,
            s.session_id,
            s.student_id,
            s.course_id,
            s.objective_id,
            s.started_at_utc
        FROM numeric_assignments_v01 AS a
        LEFT JOIN numeric_teaching_sessions_v01 AS s
            ON s.session_id = a.session_id
        """
    )

    for row in rows:
        (
            assignment_student,
            assignment_course,
            assignment_objective,
            assigned_at_raw,
            stored_session_id,
            session_student,
            session_course,
            session_objective,
            started_at_raw,
        ) = row

        if stored_session_id is None:
            raise DatabaseNotReadyError(
                "An Assignment references a missing Teaching Session."
            )

        if (
            assignment_student != session_student
            or assignment_course != session_course
            or assignment_objective != session_objective
        ):
            raise DatabaseNotReadyError(
                "An Assignment and its Teaching Session "
                "have inconsistent student/course/objective scope."
            )

        assigned_at = _require_aware_datetime(
            assigned_at_raw,
            field_name="assigned_at_utc",
        )

        started_at = _require_aware_datetime(
            started_at_raw,
            field_name="started_at_utc",
        )

        if assigned_at < started_at:
            raise DatabaseNotReadyError(
                "An Assignment predates its Teaching Session."
            )


def check_sqlite_numeric_database(
    database_path: str | Path,
) -> NumericDatabaseReadinessV01:
    """
    Verify an existing SQLite database without changing it.

    SQLite mode=ro prevents this function from silently creating
    the supplied database file.

    A successful result means the inspected schema and existing
    Session/Assignment relationships passed this preflight.
    It is not a complete application-security certification.
    """

    database = _existing_database(database_path)

    connection = sqlite3.connect(
        database.as_uri() + "?mode=ro",
        uri=True,
        timeout=5,
    )

    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")

        existing_tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        missing_tables = (
            set(REQUIRED_TABLES) - existing_tables
        )

        if missing_tables:
            raise DatabaseNotReadyError(
                "Database is missing required tables: "
                + ", ".join(sorted(missing_tables))
            )

        try:
            schema_version, assignment_count = inspect(
                connection
            )
        except (
            MigrationSafetyError,
            sqlite3.Error,
        ) as exc:
            raise DatabaseNotReadyError(
                "Assignment schema or database integrity "
                f"check failed: {exc}"
            ) from exc

        if schema_version != "current":
            raise DatabaseNotReadyError(
                "Legacy Assignment schema detected. "
                "Do not start the current numeric teaching service "
                "against this database. Review the guarded migration "
                "procedure first."
            )

        _check_session_assignment_scope(connection)

        def count_rows(table_name: str) -> int:
            # Only fixed, internal table names are supplied here.
            return connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]

        return NumericDatabaseReadinessV01(
            database_path=str(database),
            schema_version=schema_version,
            assessment_item_count=count_rows(
                "assessment_items_v02"
            ),
            attempt_count=count_rows(
                "student_attempts_v02"
            ),
            assignment_count=assignment_count,
            teaching_session_count=count_rows(
                "numeric_teaching_sessions_v01"
            ),
        )

    except sqlite3.Error as exc:
        raise DatabaseNotReadyError(
            f"SQLite readiness inspection failed: {exc}"
        ) from exc

    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only readiness check for an existing "
            "URPP numeric teaching SQLite database."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help="Path to an existing SQLite database file.",
    )

    args = parser.parse_args()

    try:
        result = check_sqlite_numeric_database(
            args.database
        )

    except DatabaseNotReadyError as exc:
        parser.exit(
            status=1,
            message=f"NOT READY: {exc}\n",
        )

    print("DATABASE READY FOR INTERNAL NUMERIC-SERVICE PREFLIGHT")
    print("Schema:", result.schema_version)
    print("Assessment items:", result.assessment_item_count)
    print("Attempts:", result.attempt_count)
    print("Assignments:", result.assignment_count)
    print("Teaching sessions:", result.teaching_session_count)
    print("Read-only inspection complete. No changes made.")


if __name__ == "__main__":
    main()

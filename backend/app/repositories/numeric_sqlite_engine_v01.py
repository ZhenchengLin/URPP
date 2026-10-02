"""
URPP Design 01D — Numeric SQLite Engine V0.1.

Create a SQLAlchemy Engine for an EXISTING, ready URPP
numeric-teaching SQLite database.

The factory:
1. Rejects missing databases and incomplete schemas.
2. Runs the existing read-only Database Readiness Check.
3. Confirms the registered-session Composite Foreign Key.
4. Opens SQLite with mode=rw, preventing silent file creation.
5. Enables foreign_keys on every newly created connection.
6. Verifies foreign_keys whenever a connection is checked out
   from SQLAlchemy's connection pool.

This is a database connection boundary, not an application
startup implementation.

It does NOT:
- create or migrate a database;
- authenticate students;
- prevent arbitrary external SQLite clients from disabling
  foreign-key enforcement;
- replace a database transaction or authorization policy;
- automatically configure existing URPP services.

Application services must actually use the returned Engine
for these connection-level checks to protect their writes.
"""

import sqlite3

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from app.repositories.audit_numeric_session_fk_migration_v01 import (
    SessionFKMigrationAuditError,
    audit_sqlite_session_fk_migration,
)

from app.repositories.numeric_database_readiness_v01 import (
    DatabaseNotReadyError,
    check_sqlite_numeric_database,
)


class NumericSQLiteEngineError(RuntimeError):
    """The SQLite database or its connection policy is unsafe."""


def _require_existing_database(
    database_path: str | Path,
) -> Path:
    database = (
        Path(database_path)
        .expanduser()
        .absolute()
    )

    if database.is_symlink():
        raise NumericSQLiteEngineError(
            "Refusing to connect through a symbolic-link "
            "database path."
        )

    if not database.is_file():
        raise NumericSQLiteEngineError(
            "Numeric SQLite database does not exist. "
            "The Engine factory never creates databases."
        )

    return database


def create_numeric_sqlite_engine(
    database_path: str | Path,
    *,
    timeout_seconds: float = 5.0,
) -> Engine:
    """
    Return an Engine only for an existing, ready SQLite DB.

    Readiness inspection occurs before Engine creation.

    The SQLite mode=rw connection URI also prevents the
    database from being silently recreated if the file
    disappears between inspection and first connection.
    """

    database = _require_existing_database(
        database_path
    )

    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not 0 < timeout_seconds <= 60
    ):
        raise ValueError(
            "timeout_seconds must be greater than 0 "
            "and no greater than 60."
        )

    try:
        check_sqlite_numeric_database(
            database
        )

        audit = audit_sqlite_session_fk_migration(
            database
        )

    except (
        DatabaseNotReadyError,
        SessionFKMigrationAuditError,
    ) as exc:
        raise NumericSQLiteEngineError(
            "Numeric SQLite database failed readiness "
            f"verification: {exc}"
        ) from exc

    if audit.schema_stage != "post-12B":
        raise NumericSQLiteEngineError(
            "Numeric SQLite database does not have "
            "the required post-12B schema."
        )

    # sqlite3.connect(..., mode=rw) opens an existing DB.
    # Unlike SQLite's default mode, it does not create one.
    uri = database.as_uri() + "?mode=rw"

    def open_existing_database() -> sqlite3.Connection:
        return sqlite3.connect(
            uri,
            uri=True,
            timeout=float(timeout_seconds),
            check_same_thread=False,
        )

    engine = create_engine(
        "sqlite+pysqlite://",
        creator=open_existing_database,
        poolclass=QueuePool,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(
        connection: sqlite3.Connection,
        _connection_record,
    ) -> None:
        connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()

        if enabled is None or enabled[0] != 1:
            raise NumericSQLiteEngineError(
                "SQLite foreign_keys could not be enabled "
                "on a new database connection."
            )

    @event.listens_for(engine, "checkout")
    def check_foreign_keys(
        connection: sqlite3.Connection,
        _connection_record,
        _connection_proxy,
    ) -> None:
        """
        Fail closed if a previously pooled connection has
        had its foreign-key enforcement disabled.

        This verifies the connection at checkout. Callers
        must not disable the PRAGMA after checkout.
        """

        enabled = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()

        if enabled is None or enabled[0] != 1:
            raise NumericSQLiteEngineError(
                "SQLite foreign_keys is disabled on "
                "a pooled database connection."
            )

    return engine

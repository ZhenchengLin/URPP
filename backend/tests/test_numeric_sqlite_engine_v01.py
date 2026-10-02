"""
URPP Design 01D — Numeric SQLite Engine tests.

Only temporary SQLite databases are used.

No actual application database is created, opened,
migrated, or modified by this test module.
"""

import sqlite3

import pytest

from sqlalchemy import create_engine

from app.repositories.assessment_records_v02 import Base

import app.repositories.numeric_assignment_v01
import app.repositories.numeric_session_records_v01

from app.repositories.numeric_sqlite_engine_v01 import (
    NumericSQLiteEngineError,
    create_numeric_sqlite_engine,
)


@pytest.fixture
def ready_database(tmp_path):
    path = tmp_path / "ready_numeric.sqlite"

    initialization_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    Base.metadata.create_all(
        initialization_engine
    )

    initialization_engine.dispose()

    return path


def test_missing_database_is_not_created(
    tmp_path,
):
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(
        NumericSQLiteEngineError,
        match="does not exist",
    ):
        create_numeric_sqlite_engine(
            missing
        )

    assert not missing.exists()


def test_incomplete_database_is_rejected(
    tmp_path,
):
    path = tmp_path / "incomplete.sqlite"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"
        )

    with pytest.raises(
        NumericSQLiteEngineError,
        match="failed readiness",
    ):
        create_numeric_sqlite_engine(
            path
        )


def test_engine_enables_foreign_keys_on_every_connection(
    ready_database,
):
    engine = create_numeric_sqlite_engine(
        ready_database
    )

    try:
        # Keeping both connections checked out requires
        # the QueuePool to open two SQLite connections.
        with engine.connect() as first:
            with engine.connect() as second:

                assert first.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

                assert second.exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

    finally:
        engine.dispose()


def test_pool_rejects_connection_with_foreign_keys_disabled(
    ready_database,
):
    engine = create_numeric_sqlite_engine(
        ready_database
    )

    try:
        with engine.connect() as connection:

            raw_connection = (
                connection.connection.driver_connection
            )

            raw_connection.execute(
                "PRAGMA foreign_keys=OFF"
            )

            assert raw_connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0] == 0

        # Returning the connection to the pool does not
        # make its disabled PRAGMA acceptable.
        with pytest.raises(
            NumericSQLiteEngineError,
            match="foreign_keys is disabled",
        ):
            with engine.connect():
                pass

    finally:
        engine.dispose()


def test_database_is_not_recreated_if_removed_before_connect(
    ready_database,
):
    engine = create_numeric_sqlite_engine(
        ready_database
    )

    try:
        # Simulate the DB file disappearing after readiness
        # inspection but before the first DBAPI connection.
        ready_database.unlink()

        with pytest.raises(
            Exception
        ):
            with engine.connect():
                pass

        assert not ready_database.exists()

    finally:
        engine.dispose()

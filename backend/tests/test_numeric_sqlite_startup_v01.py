"""
URPP Design 01D — Optional Numeric SQLite startup tests.

All SQLite databases used in this module are synthetic
temporary test databases.

These tests exercise the actual FastAPI lifespan without
starting an external server or opening a real application DB.
"""

import asyncio
import sqlite3

import pytest

from sqlalchemy import create_engine

from app.main import app as fastapi_app

from app.repositories.assessment_records_v02 import Base

import app.repositories.numeric_assignment_v01
import app.repositories.numeric_session_records_v01

from app.repositories.numeric_sqlite_engine_v01 import (
    NumericSQLiteEngineError,
)


ENVIRONMENT_VARIABLE = (
    "URPP_NUMERIC_SQLITE_DATABASE_PATH"
)


async def _run_app_lifespan(assertion=None):
    async with fastapi_app.router.lifespan_context(fastapi_app):
        if assertion is not None:
            assertion()


@pytest.fixture
def ready_database(tmp_path):
    path = tmp_path / "ready_startup.sqlite"

    initialization_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    Base.metadata.create_all(
        initialization_engine
    )

    initialization_engine.dispose()

    return path


def test_health_only_startup_needs_no_database(
    monkeypatch,
):
    monkeypatch.delenv(
        ENVIRONMENT_VARIABLE,
        raising=False,
    )

    def check_running_app():
        assert not hasattr(
            fastapi_app.state,
            "numeric_sqlite_engine",
        )

    asyncio.run(
        _run_app_lifespan(check_running_app)
    )


def test_opt_in_startup_rejects_missing_database(
    monkeypatch,
    tmp_path,
):
    missing = tmp_path / "missing.sqlite"

    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(missing),
    )

    with pytest.raises(
        NumericSQLiteEngineError,
        match="does not exist",
    ):
        asyncio.run(
            _run_app_lifespan()
        )

    assert not missing.exists()

    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )


def test_opt_in_startup_rejects_incomplete_schema(
    monkeypatch,
    tmp_path,
):
    path = tmp_path / "incomplete.sqlite"

    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"
        )

    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(path),
    )

    with pytest.raises(
        NumericSQLiteEngineError,
        match="failed readiness",
    ):
        asyncio.run(
            _run_app_lifespan()
        )

    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )


def test_opt_in_startup_rejects_empty_path(
    monkeypatch,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        "  ",
    )

    with pytest.raises(
        RuntimeError,
        match="is set but is empty",
    ):
        asyncio.run(
            _run_app_lifespan()
        )

    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )


def test_ready_database_engine_is_available_during_lifespan(
    monkeypatch,
    ready_database,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(ready_database),
    )

    observed = {}

    def check_running_app():
        engine = fastapi_app.state.numeric_sqlite_engine

        observed["engine"] = engine

        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar_one() == 1

        observed["running"] = True

    asyncio.run(
        _run_app_lifespan(check_running_app)
    )

    assert observed["running"] is True

    # Shutdown removes the application reference and disposes
    # the Engine. Existing repository instances are not
    # automatically reconfigured by this integration.
    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )

    assert observed["engine"].pool.checkedout() == 0

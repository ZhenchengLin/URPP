"""
URPP Design 01D — Numeric Repository Bundle V0.1.

Construct the numeric-teaching repositories with ONE shared
SQLAlchemy Session factory bound to an existing Engine.

The FastAPI lifespan supplies the guarded Numeric SQLite
Engine created by numeric_sqlite_engine_v01.

The bundle itself does not:
- create a database;
- run migrations;
- authenticate students;
- expose a student-facing API;
- automatically reconfigure independently created services.

The Engine owner, currently the FastAPI lifespan, is
responsible for disposing the Engine at shutdown.
"""

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)


class NumericRepositoryBundleError(RuntimeError):
    """Repository binding did not meet its connection requirements."""


@dataclass(frozen=True)
class NumericRepositoryBundleV01:
    engine: Engine
    session_factory: sessionmaker
    assessment_repository: AssessmentRecordRepositoryV02
    assignment_repository: NumericAssignmentRepositoryV01
    teaching_session_repository: NumericSessionRecordRepositoryV01


def create_numeric_repository_bundle(
    engine: Engine,
) -> NumericRepositoryBundleV01:
    """
    Bind the numeric repositories to an existing Engine.

    Call this with create_numeric_sqlite_engine()'s result.
    The explicit foreign_keys check is a second safeguard;
    it does not replace that Engine factory's schema and
    connection-policy checks.
    """

    if not isinstance(engine, Engine):
        raise TypeError(
            "engine must be a SQLAlchemy Engine."
        )

    if engine.dialect.name != "sqlite":
        raise NumericRepositoryBundleError(
            "NumericRepositoryBundleV01 currently requires SQLite."
        )

    # Creating the repositories is not enough: verify that
    # the supplied Engine actually yields an FK-enabled
    # connection before any service receives the bundle.
    with engine.connect() as connection:
        foreign_keys_enabled = connection.exec_driver_sql(
            "PRAGMA foreign_keys"
        ).scalar_one()

    if foreign_keys_enabled != 1:
        raise NumericRepositoryBundleError(
            "The supplied SQLite Engine does not enforce "
            "foreign keys. Use create_numeric_sqlite_engine()."
        )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(
        factory
    )

    assignments = NumericAssignmentRepositoryV01(
        assessments
    )

    teaching_sessions = NumericSessionRecordRepositoryV01(
        assessments
    )

    return NumericRepositoryBundleV01(
        engine=engine,
        session_factory=factory,
        assessment_repository=assessments,
        assignment_repository=assignments,
        teaching_session_repository=teaching_sessions,
    )

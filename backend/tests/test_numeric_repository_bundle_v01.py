"""
URPP Design 01D — Numeric Repository Bundle tests.

All databases are created under pytest's temporary directory.

These tests verify that FastAPI's registered repositories
use the guarded startup Engine for actual database operations.
"""

import asyncio
import importlib

from datetime import datetime, timezone

import pytest

from sqlalchemy import create_engine

from app.main import app as fastapi_app

from app.repositories.assessment_records_v02 import (
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)

from app.repositories.numeric_repository_bundle_v01 import (
    NumericRepositoryBundleV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericTeachingSessionRowV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    AssessmentDeliveryV01,
)


ENVIRONMENT_VARIABLE = "URPP_NUMERIC_SQLITE_DATABASE_PATH"

NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


@pytest.fixture
def ready_database(tmp_path):
    path = tmp_path / "repository_bundle.sqlite"

    initialization_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    Base.metadata.create_all(
        initialization_engine
    )

    initialization_engine.dispose()

    return path


def test_health_only_startup_has_no_repository_bundle(
    monkeypatch,
):
    monkeypatch.delenv(
        ENVIRONMENT_VARIABLE,
        raising=False,
    )

    async def run():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            assert not hasattr(
                fastapi_app.state,
                "numeric_sqlite_engine",
            )

            assert not hasattr(
                fastapi_app.state,
                "numeric_repositories",
            )

    asyncio.run(run())


def test_startup_bundle_uses_guarded_engine(
    monkeypatch,
    ready_database,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(ready_database),
    )

    async def run():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            engine = fastapi_app.state.numeric_sqlite_engine

            repositories = (
                fastapi_app.state.numeric_repositories
            )

            assert isinstance(
                repositories,
                NumericRepositoryBundleV01,
            )

            assert repositories.engine is engine

            assert (
                repositories.session_factory.kw["bind"]
                is engine
            )

            # This Session comes from the factory injected
            # into the actual Repository Bundle.
            with repositories.session_factory() as session:
                assert session.connection().exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

    asyncio.run(run())

    assert not hasattr(
        fastapi_app.state,
        "numeric_repositories",
    )

    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )


def test_repositories_persist_through_injected_engine(
    monkeypatch,
    ready_database,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(ready_database),
    )

    async def run():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            repositories = (
                fastapi_app.state.numeric_repositories
            )

            repositories.assessment_repository.save_item(
                AssessmentItemV02(
                    assessment_item_id="item-bundle-001",
                    course_id="course-bundle-001",
                    objective_id="objective-bundle-001",
                    prompt="What is 2 + 3?",
                    rubric=NumericRubricV02(
                        expected_value=5.0,
                        absolute_tolerance=0.0,
                        rubric_version="numeric-rubric-v1",
                    ),
                    alignment_verified=True,
                ),
                revision=1,
            )

            repositories.teaching_session_repository.register(
                session_id="session-bundle-001",
                student_id="student-bundle-001",
                course_id="course-bundle-001",
                objective_id="objective-bundle-001",
                started_at=NOW,
            )

            repositories.assignment_repository.issue_assignment(
                AssessmentDeliveryV01(
                    assignment_id="assignment-bundle-001",
                    decision_id="decision-bundle-001",
                    assessment_item_id="item-bundle-001",
                    item_revision=1,
                    prompt="What is 2 + 3?",
                    selected_action=(
                        TeachingActionV01.DIAGNOSTIC_ASSESSMENT
                    ),
                    assigned_at=NOW,
                ),
                student_id="student-bundle-001",
                course_id="course-bundle-001",
                objective_id="objective-bundle-001",
                session_id="session-bundle-001",
            )

            # Verify the records using the SAME injected
            # Session factory, rather than constructing
            # a separate database connection.
            with repositories.session_factory() as session:
                stored_session = session.get(
                    NumericTeachingSessionRowV01,
                    "session-bundle-001",
                )

                stored_assignment = session.get(
                    NumericAssignmentRow,
                    "assignment-bundle-001",
                )

                assert stored_session is not None
                assert stored_assignment is not None

                assert (
                    stored_assignment.registered_session_id
                    == stored_session.session_id
                )

                assert session.connection().exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

    asyncio.run(run())


def test_repository_setup_failure_cleans_up_app_state(
    monkeypatch,
    ready_database,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(ready_database),
    )

    main_module = importlib.import_module(
        "app.main"
    )

    def fail_bundle_creation(_engine):
        raise RuntimeError(
            "Injected repository setup failure"
        )

    monkeypatch.setattr(
        main_module,
        "create_numeric_repository_bundle",
        fail_bundle_creation,
    )

    async def run():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            pytest.fail(
                "Startup must not succeed after "
                "Repository Bundle construction fails."
            )

    with pytest.raises(
        RuntimeError,
        match="Injected repository setup failure",
    ):
        asyncio.run(run())

    assert not hasattr(
        fastapi_app.state,
        "numeric_repositories",
    )

    assert not hasattr(
        fastapi_app.state,
        "numeric_sqlite_engine",
    )

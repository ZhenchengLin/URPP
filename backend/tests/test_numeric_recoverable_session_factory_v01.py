"""
URPP Design 01D — Recoverable Session Factory tests.

All databases are created under pytest's temporary directory.

The Decision Orchestrator is simulated in the lifecycle test.
The actual Assessment, Assignment, Session, Attempt, and
Student State persistence services are used.
"""

import asyncio

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sqlalchemy import create_engine

from app.main import app as fastapi_app

from app.repositories.assessment_records_v02 import Base

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)

from app.repositories.numeric_repository_bundle_v01 import (
    NumericRepositoryBundleV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.numeric_recoverable_session_factory_v01 import (
    create_recoverable_numeric_session_service,
)


ENVIRONMENT_VARIABLE = (
    "URPP_NUMERIC_SQLITE_DATABASE_PATH"
)

NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)

STUDENT_ID = "student-factory-001"
COURSE_ID = "course-factory-001"
OBJECTIVE_ID = "objective-factory-001"
SESSION_ID = "session-factory-001"
ITEM_ID = "item-factory-001"


@pytest.fixture
def ready_database(tmp_path):
    path = tmp_path / "recoverable_factory.sqlite"

    initialization_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    Base.metadata.create_all(
        initialization_engine
    )

    initialization_engine.dispose()

    return path


def make_orchestrator():
    """
    Simulate only the Teaching Decision boundary.

    The rest of the test uses real persistence services.
    """

    orchestrator = Mock()

    orchestrator.run_turn.return_value = SimpleNamespace(
        agent_kind="assessment",
        decision=SimpleNamespace(
            selected_action=(
                TeachingActionV01.DIAGNOSTIC_ASSESSMENT
            ),
        ),
    )

    return orchestrator


def make_session_service(repositories, orchestrator=None):
    return create_recoverable_numeric_session_service(
        repositories,
        turn_orchestrator=(
            orchestrator
            if orchestrator is not None
            else make_orchestrator()
        ),
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        session_id=SESSION_ID,
    )


def save_numeric_item(repositories):
    repositories.assessment_repository.save_item(
        AssessmentItemV02(
            assessment_item_id=ITEM_ID,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
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


def test_factory_rejects_non_bundle():
    with pytest.raises(
        TypeError,
        match="NumericRepositoryBundleV01",
    ):
        make_session_service(
            repositories=object(),
        )


def test_health_only_startup_has_no_numeric_bundle(
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
                "numeric_repositories",
            )

    asyncio.run(run())


def test_factory_uses_exact_startup_repository_instances(
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

            assert isinstance(
                repositories,
                NumericRepositoryBundleV01,
            )

            service = make_session_service(
                repositories
            )

            assert (
                service._assessments
                is repositories.assessment_repository
            )

            assert (
                service._assignments
                is repositories.assignment_repository
            )

            assert (
                service._sessions
                is repositories.teaching_session_repository
            )

            assert (
                service._completed_state_service
                ._assessment_repository
                is repositories.assessment_repository
            )

            assert (
                service._completed_state_service
                ._assignment_repository
                is repositories.assignment_repository
            )

            assert (
                repositories.session_factory.kw["bind"]
                is fastapi_app.state.numeric_sqlite_engine
            )

            with repositories.session_factory() as session:
                assert session.connection().exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

    asyncio.run(run())


def test_delivery_submission_state_and_restart_use_shared_database(
    monkeypatch,
    ready_database,
):
    monkeypatch.setenv(
        ENVIRONMENT_VARIABLE,
        str(ready_database),
    )

    saved = {}

    async def first_startup():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            repositories = (
                fastapi_app.state.numeric_repositories
            )

            save_numeric_item(repositories)

            orchestrator = make_orchestrator()

            service = make_session_service(
                repositories,
                orchestrator,
            )

            initial = service.start(
                started_at=NOW
            )

            assert initial.pending is None
            assert initial.state is not None

            delivery = service.deliver_numeric_assessment(
                assessment_item_id=ITEM_ID,
                item_revision=1,
                decision_id="decision-factory-001",
                requested_at=NOW + timedelta(minutes=1),
            )

            assert delivery.prompt == "What is 2 + 3?"

            orchestrator.run_turn.assert_called_once()

            with repositories.session_factory() as session:
                stored = session.get(
                    NumericAssignmentRow,
                    delivery.assignment_id,
                )

                assert stored is not None

                assert stored.registered_session_id == SESSION_ID
                assert stored.status == "pending"

                assert session.connection().exec_driver_sql(
                    "PRAGMA foreign_keys"
                ).scalar_one() == 1

            # Use a future observation time because the actual
            # submission timestamp is generated by the repository.
            progress = service.submit_numeric_answer(
                assignment_id=delivery.assignment_id,
                response_text="5",
                as_of=NOW + timedelta(days=7),
            )

            assert progress.pending is None
            assert progress.state is not None

            saved["assignment_id"] = delivery.assignment_id

            with repositories.session_factory() as session:
                stored = session.get(
                    NumericAssignmentRow,
                    delivery.assignment_id,
                )

                assert stored.status == "completed"
                assert stored.completed_attempt_id is not None

    asyncio.run(first_startup())

    assert not hasattr(
        fastapi_app.state,
        "numeric_repositories",
    )

    # A second lifespan constructs a NEW guarded Engine and a
    # NEW Repository Bundle from the same persistent test DB.
    # No in-memory Session Service is reused.
    async def second_startup():
        async with fastapi_app.router.lifespan_context(
            fastapi_app
        ):
            repositories = (
                fastapi_app.state.numeric_repositories
            )

            recovered_service = make_session_service(
                repositories
            )

            recovered = recovered_service.resume(
                as_of=NOW + timedelta(days=7),
            )

            assert recovered.pending is None
            assert recovered.state is not None

            with repositories.session_factory() as session:
                stored = session.get(
                    NumericAssignmentRow,
                    saved["assignment_id"],
                )

                assert stored is not None
                assert stored.status == "completed"
                assert stored.registered_session_id == SESSION_ID
                assert stored.completed_attempt_id is not None

    asyncio.run(second_startup())

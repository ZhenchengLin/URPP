"""
URPP Design 01D — Recoverable Numeric Session Factory V0.1.

Construct a RecoverableNumericSessionServiceV01 using the
repositories supplied by the guarded FastAPI startup Bundle.

All repositories are taken from ONE NumericRepositoryBundleV01.
This factory does not create an Engine, a sessionmaker, or
another independently configured repository.

The caller supplies the teaching-session identity and an
existing TeachingTurnOrchestratorV01.

Usage during the optional numeric database lifespan:

    bundle = request.app.state.numeric_repositories

    service = create_recoverable_numeric_session_service(
        bundle,
        turn_orchestrator=orchestrator,
        student_id=...,
        course_id=...,
        objective_id=...,
        session_id=...,
    )

This is an INTERNAL construction boundary.

It does not:
- authenticate the supplied student_id;
- authorize access to a session;
- expose a public student-facing endpoint;
- create or migrate a database;
- construct a real LLM Agent or NanoJev controller;
- keep database operations atomic across an entire lesson.
"""

from app.repositories.numeric_repository_bundle_v01 import (
    NumericRepositoryBundleV01,
)

from app.services.decision.recoverable_numeric_session_v01 import (
    RecoverableNumericSessionServiceV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    TeachingTurnOrchestratorV01,
)


def create_recoverable_numeric_session_service(
    repositories: NumericRepositoryBundleV01,
    *,
    turn_orchestrator: TeachingTurnOrchestratorV01,
    student_id: str,
    course_id: str,
    objective_id: str,
    session_id: str,
) -> RecoverableNumericSessionServiceV01:
    """
    Create a session-bound service without opening a new
    database connection or constructing new repositories.

    The repositories argument should come from the guarded
    FastAPI lifespan's app.state.numeric_repositories.
    """

    if not isinstance(
        repositories,
        NumericRepositoryBundleV01,
    ):
        raise TypeError(
            "repositories must be a NumericRepositoryBundleV01 "
            "from the guarded numeric database startup."
        )

    return RecoverableNumericSessionServiceV01(
        assessment_repository=(
            repositories.assessment_repository
        ),
        assignment_repository=(
            repositories.assignment_repository
        ),
        session_repository=(
            repositories.teaching_session_repository
        ),
        turn_orchestrator=turn_orchestrator,
        student_id=student_id,
        course_id=course_id,
        objective_id=objective_id,
        session_id=session_id,
    )

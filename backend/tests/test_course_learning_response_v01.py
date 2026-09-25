"""
14B-3-2A: response persistence tests.

Synthetic teaching fixture only. All database files
live under pytest's temporary directory.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from app.repositories.course_learning_response_v01 import (
    CourseLearningResponseRepositoryV01,
    course_learning_responses_v01,
)

from app.repositories.course_teaching_presentation_v01 import (
    CourseTeachingPresentationRepositoryV01,
    course_teaching_presentations_v01,
)

from app.repositories.course_teaching_trace_v01 import (
    course_teaching_traces_v01,
)

from app.services.course_knowledge.durable_teaching_turn_v01 import (
    DurableCourseTeachingTurnV01,
    course_teaching_turn_intents_v01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
)

from scripts.course_teaching_demo_v01 import (
    COURSE_ID,
    DECISION_ID,
    FakeCourseProfessor,
    OBJECTIVE_ID,
    PACK_REVISION,
    REQUESTED_AT,
    STUDENT_ID,
    TRACE_ID,
    make_pack,
    make_request,
    make_state,
)


PRESENTED_AT = REQUESTED_AT + timedelta(seconds=1)
SUBMITTED_AT = PRESENTED_AT + timedelta(seconds=1)

ACTIVITY_ID = "synthetic-activity-001"

ACTIVITY_PROMPT = (
    "SYNTHETIC ACTIVITY: Explain one reason a "
    "matrix decomposition can be useful."
)

ANSWER = (
    "A decomposition can expose a matrix structure "
    "that is useful for subsequent computation."
)


def make_engine(path: Path):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    return engine


def setup_storage(
    tmp_path,
    *,
    create_response_table=True,
    report_presentation=True,
):
    database = tmp_path / "student-responses.sqlite"
    engine = make_engine(database)

    # Explicit test-only schema provisioning.
    course_teaching_traces_v01.create(
        engine,
        checkfirst=False,
    )

    course_teaching_turn_intents_v01.create(
        engine,
        checkfirst=False,
    )

    course_teaching_presentations_v01.create(
        engine,
        checkfirst=False,
    )

    if create_response_table:
        course_learning_responses_v01.create(
            engine,
            checkfirst=False,
        )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    teaching = DurableCourseTeachingTurnV01(
        session_factory=factory,
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=FakeCourseProfessor(),
    )

    teaching.run_or_resume(
        make_state(),
        pack=make_pack(),
        trace_id=TRACE_ID,
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        expected_pack_revision=PACK_REVISION,
        decision_id=DECISION_ID,
        requested_at=REQUESTED_AT,
        generated_at=REQUESTED_AT,
        student_request=make_request(),
    )

    if report_presentation:
        presentations = (
            CourseTeachingPresentationRepositoryV01(
                factory
            )
        )

        presentations.record_presentation(
            trace_id=TRACE_ID,
            student_id=STUDENT_ID,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
            event_id="synthetic-presentation-001",
            reported_at=PRESENTED_AT,
            surface="synthetic_test_cli",
        )

    repository = CourseLearningResponseRepositoryV01(
        factory
    )

    return database, engine, factory, repository


def submit(repository, **overrides):
    values = {
        "response_id": "synthetic-response-001",
        "trace_id": TRACE_ID,
        "student_id": STUDENT_ID,
        "course_id": COURSE_ID,
        "objective_id": OBJECTIVE_ID,
        "activity_id": ACTIVITY_ID,
        "activity_prompt": ACTIVITY_PROMPT,
        "response_text": ANSWER,
        "submitted_at": SUBMITTED_AT,
    }

    values.update(overrides)

    return repository.record_response(**values)


def load(repository, **overrides):
    values = {
        "response_id": "synthetic-response-001",
        "trace_id": TRACE_ID,
        "student_id": STUDENT_ID,
        "course_id": COURSE_ID,
        "objective_id": OBJECTIVE_ID,
    }

    values.update(overrides)

    return repository.load(**values)


def test_submitted_response_survives_database_reopen(tmp_path):
    database, engine, _, repository = setup_storage(
        tmp_path
    )

    stored = submit(repository)

    assert stored.response_text == ANSWER
    assert stored.activity_prompt == ACTIVITY_PROMPT
    assert stored.trace_id == TRACE_ID
    assert (
        stored.presentation_event_id
        == "synthetic-presentation-001"
    )

    engine.dispose()

    reopened_engine = make_engine(database)

    reopened_factory = sessionmaker(
        bind=reopened_engine,
        expire_on_commit=False,
    )

    recovered = load(
        CourseLearningResponseRepositoryV01(
            reopened_factory
        )
    )

    assert recovered == stored

    reopened_engine.dispose()


def test_response_requires_presentation_report(tmp_path):
    _, engine, _, repository = setup_storage(
        tmp_path,
        report_presentation=False,
    )

    with pytest.raises(
        ValueError,
        match="presentation_reported",
    ):
        submit(repository)

    engine.dispose()


def test_identical_submission_is_idempotent(tmp_path):
    _, engine, _, repository = setup_storage(
        tmp_path
    )

    first = submit(repository)
    repeated = submit(repository)

    assert repeated == first

    engine.dispose()


def test_changed_answer_cannot_overwrite_first_submission(
    tmp_path,
):
    _, engine, _, repository = setup_storage(
        tmp_path
    )

    first = submit(repository)

    with pytest.raises(
        ValueError,
        match="conflicts with the original",
    ):
        submit(
            repository,
            response_text="A different response.",
        )

    assert load(repository) == first

    engine.dispose()


def test_second_response_id_for_same_activity_is_rejected(
    tmp_path,
):
    _, engine, _, repository = setup_storage(
        tmp_path
    )

    first = submit(repository)

    with pytest.raises(
        ValueError,
        match="already has a response",
    ):
        submit(
            repository,
            response_id="synthetic-response-002",
        )

    assert load(repository) == first

    engine.dispose()


def test_wrong_scope_and_invalid_response_are_rejected(
    tmp_path,
):
    _, engine, _, repository = setup_storage(
        tmp_path
    )

    first = submit(repository)

    with pytest.raises(
        ValueError,
        match="scope mismatch",
    ):
        load(
            repository,
            student_id="another-student",
        )

    with pytest.raises(
        ValueError,
        match="response_text",
    ):
        submit(
            repository,
            response_id="synthetic-response-002",
            activity_id="synthetic-activity-002",
            response_text="   ",
        )

    with pytest.raises(
        ValueError,
        match="cannot precede",
    ):
        submit(
            repository,
            response_id="synthetic-response-003",
            activity_id="synthetic-activity-003",
            submitted_at=(
                PRESENTED_AT - timedelta(seconds=1)
            ),
        )

    assert load(repository) == first

    engine.dispose()


def test_repository_does_not_create_missing_response_table(
    tmp_path,
):
    _, engine, _, repository = setup_storage(
        tmp_path,
        create_response_table=False,
    )

    with pytest.raises(
        Exception,
        match="course_learning_responses_v01",
    ):
        submit(repository)

    assert (
        "course_learning_responses_v01"
        not in inspect(engine).get_table_names()
    )

    engine.dispose()

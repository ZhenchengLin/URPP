"""
14B-3-2C-1: durable Fake Professor feedback tests.

Uses the existing integrated Synthetic Demo to prepare
submitted responses in temporary SQLite databases.

Feedback is teaching text, not a grade or Mastery Evidence.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from sqlalchemy.orm import sessionmaker

from app.repositories.course_learning_response_v01 import (
    CourseLearningResponseRepositoryV01,
)

from app.services.course_knowledge.durable_learning_feedback_v01 import (
    DurableLearningFeedbackV01,
    FeedbackRecoveryRequiredV01,
    course_learning_feedback_v01,
)

from scripts.course_teaching_demo_v01 import (
    ACTIVITY_ID,
    ACTIVITY_PROMPT,
    COURSE_ID,
    OBJECTIVE_ID,
    RESPONSE_ID,
    STUDENT_ID,
    TRACE_ID,
    initialize_database,
    open_verified_demo,
    run_present,
    run_teach,
)


FEEDBACK_ID = "synthetic-feedback-001"
FEEDBACK_VERSION = "synthetic-feedback-policy-v01"

ANSWER = (
    "A matrix decomposition can expose structure "
    "for later computation."
)


class CountingFakeFeedbackAgent:
    def __init__(self):
        self.calls = 0

    def produce(self, *, response):
        self.calls += 1

        # Deliberately no correctness judgment, grade,
        # confidence score, or mastery inference.
        return (
            "SYNTHETIC FEEDBACK: You submitted a response "
            f"to {response.activity_id}. "
            "Consider adding a concrete computational example. "
            f"Generation call: {self.calls}."
        )


def setup_storage(tmp_path):
    database = (
        Path(tmp_path)
        / "urpp-course-teaching-demo.sqlite"
    )

    # Existing demo initialization explicitly creates only
    # synthetic-demo tables in a new temporary database.
    initialize_database(database)

    engine = open_verified_demo(database)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    # The existing integrated flow creates a Generated Trace
    # and reports presentation before accepting student input.
    run_teach(factory)
    run_present(factory)

    responses = CourseLearningResponseRepositoryV01(
        factory
    )

    stored_response = responses.record_response(
        response_id=RESPONSE_ID,
        trace_id=TRACE_ID,
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        activity_id=ACTIVITY_ID,
        activity_prompt=ACTIVITY_PROMPT,
        response_text=ANSWER,
        submitted_at=datetime.now(timezone.utc),
    )

    # The updated Synthetic Demo initializer has already
    # provisioned this table. Do not CREATE TABLE again.
    # The feedback Service itself still does not provision
    # or migrate database schemas.
    from sqlalchemy import inspect

    assert (
        "course_learning_feedback_v01"
        in inspect(engine).get_table_names()
    )

    return database, engine, factory, stored_response


def make_service(factory, agent=None):
    agent = agent or CountingFakeFeedbackAgent()

    return (
        DurableLearningFeedbackV01(
            session_factory=factory,
            feedback_agent=agent,
        ),
        agent,
    )


def request(service, **overrides):
    parameters = {
        "feedback_id": FEEDBACK_ID,
        "response_id": RESPONSE_ID,
        "trace_id": TRACE_ID,
        "student_id": STUDENT_ID,
        "course_id": COURSE_ID,
        "objective_id": OBJECTIVE_ID,
        "feedback_version": FEEDBACK_VERSION,
        "requested_at": datetime.now(timezone.utc),
    }

    parameters.update(overrides)

    return service.run_or_resume(**parameters)


def test_first_feedback_and_identical_retry_call_agent_once(
    tmp_path,
):
    _, engine, _, original_response = setup_storage(tmp_path)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    service, agent = make_service(factory)

    first = request(service)
    second = request(service)

    assert first == second
    assert first.status == "generated_feedback"
    assert first.response_id == original_response.response_id
    assert "SYNTHETIC FEEDBACK" in first.feedback_text
    assert agent.calls == 1

    # Feedback must not change the original submitted text.
    assert (
        CourseLearningResponseRepositoryV01(factory)
        .load(
            response_id=RESPONSE_ID,
            trace_id=TRACE_ID,
            student_id=STUDENT_ID,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
        )
        .response_text
        == ANSWER
    )

    engine.dispose()


def test_completed_feedback_survives_new_database_connection(
    tmp_path,
):
    database, engine, factory, _ = setup_storage(tmp_path)

    service, first_agent = make_service(factory)

    original = request(service)

    assert first_agent.calls == 1

    engine.dispose()

    reopened_engine = open_verified_demo(database)

    reopened_factory = sessionmaker(
        bind=reopened_engine,
        expire_on_commit=False,
    )

    recovered_service, second_agent = make_service(
        reopened_factory
    )

    recovered = request(recovered_service)

    assert recovered == original
    assert second_agent.calls == 0

    reopened_engine.dispose()


def test_changed_feedback_version_cannot_reuse_original(
    tmp_path,
):
    _, engine, factory, _ = setup_storage(tmp_path)

    service, agent = make_service(factory)

    original = request(service)

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        request(
            service,
            feedback_version="other-feedback-policy",
        )

    assert agent.calls == 1

    assert request(service) == original

    engine.dispose()


def test_different_feedback_id_cannot_replace_original(
    tmp_path,
):
    _, engine, factory, _ = setup_storage(tmp_path)

    service, agent = make_service(factory)

    original = request(service)

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        request(
            service,
            feedback_id="synthetic-feedback-002",
        )

    assert agent.calls == 1
    assert request(service) == original

    engine.dispose()


def test_failed_agent_leaves_ambiguous_reservation(
    tmp_path,
):
    _, engine, factory, _ = setup_storage(tmp_path)

    class FailingAgent:
        def __init__(self):
            self.calls = 0

        def produce(self, *, response):
            self.calls += 1
            raise RuntimeError(
                "Simulated feedback generation interruption."
            )

    agent = FailingAgent()

    service, _ = make_service(
        factory,
        agent=agent,
    )

    with pytest.raises(
        RuntimeError,
        match="generation interruption",
    ):
        request(service)

    with pytest.raises(
        FeedbackRecoveryRequiredV01,
        match="Do not regenerate",
    ):
        request(service)

    assert agent.calls == 1

    engine.dispose()


def test_committed_feedback_recovers_after_response_loss(
    tmp_path,
):
    _, engine, factory, _ = setup_storage(tmp_path)

    service, first_agent = make_service(factory)

    original_complete = service._complete

    def complete_then_interrupt(**kwargs):
        original_complete(**kwargs)

        raise RuntimeError(
            "Simulated interruption after feedback commit."
        )

    service._complete = complete_then_interrupt

    with pytest.raises(
        RuntimeError,
        match="after feedback commit",
    ):
        request(service)

    recovered_service, second_agent = make_service(
        factory
    )

    recovered = request(recovered_service)

    assert recovered.status == "generated_feedback"
    assert first_agent.calls == 1
    assert second_agent.calls == 0

    engine.dispose()


def test_feedback_requires_an_existing_student_response(
    tmp_path,
):
    _, engine, factory, _ = setup_storage(tmp_path)

    service, agent = make_service(factory)

    with pytest.raises(LookupError):
        request(
            service,
            response_id="missing-response",
        )

    assert agent.calls == 0

    engine.dispose()


def test_feedback_repository_does_not_create_missing_table(
    tmp_path,
):
    from sqlalchemy import inspect

    _, engine, factory, _ = setup_storage(tmp_path)

    # The Service must not provision production schemas.
    course_learning_feedback_v01.drop(engine)

    service, agent = make_service(factory)

    with pytest.raises(
        Exception,
        match="course_learning_feedback_v01",
    ):
        request(service)

    assert (
        "course_learning_feedback_v01"
        not in inspect(engine).get_table_names()
    )

    assert agent.calls == 0

    engine.dispose()

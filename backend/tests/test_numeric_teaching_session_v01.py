"""
URPP Design 01D — Bound Numeric Teaching Session tests.

All test data and Agent responses are synthetic.
No actual students, authentication, or LLM calls are involved.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
    StudentAttemptV02,
)

from app.services.decision.engine_v01 import (
    DecisionEngineV01,
    RuleBasedControllerV01,
)

from app.services.decision.numeric_teaching_session_v01 import (
    NumericTeachingSessionV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    TeachingTurnOrchestratorV01,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)

PROMPT = "Enter the numeric answer."


@pytest.fixture
def repository():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    repository = AssessmentRecordRepositoryV02(factory)

    yield repository

    engine.dispose()


class TextAgent:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def produce(self, *, context, decision):
        self.calls += 1
        return self.content


def make_item(*, item_id="item-001", expected=5.0):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id="objective-001",
        prompt=PROMPT,
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_attempt(
    *,
    attempt_id="attempt-001",
    item_id="item-001",
    student_id="student-001",
    session_id="session-001",
    response="5",
    submitted_at=None,
):
    return StudentAttemptV02(
        attempt_id=attempt_id,
        student_id=student_id,
        course_id="course-001",
        session_id=session_id,
        objective_id="objective-001",
        assessment_item_id=item_id,
        source_message_id=f"message-{attempt_id}",
        response_group_id=f"response-{attempt_id}",
        response_text=response,
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=submitted_at or NOW + timedelta(seconds=1),
    )


def make_session(
    repository,
    *,
    assessment_content=PROMPT,
):
    professor_agent = TextAgent("A conceptual explanation.")
    assessment_agent = TextAgent(assessment_content)

    orchestrator = TeachingTurnOrchestratorV01(
        decision_engine=DecisionEngineV01(
            RuleBasedControllerV01()
        ),
        professor_agent=professor_agent,
        assessment_agent=assessment_agent,
    )

    session = NumericTeachingSessionV01(
        repository=repository,
        turn_orchestrator=orchestrator,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
        as_of=NOW,
    )

    return session, professor_agent, assessment_agent


def start_turn(
    session,
    *,
    item_id="item-001",
    revision=1,
    decision_id="decision-001",
    requested_at=NOW,
):
    return session.start_numeric_turn(
        assessment_item_id=item_id,
        item_revision=revision,
        decision_id=decision_id,
        requested_at=requested_at,
    )


def test_assessment_turn_binds_stored_item(repository):
    repository.save_item(make_item(), revision=1)

    session, professor, assessment = make_session(repository)

    turn = start_turn(session)

    assert turn.content == PROMPT
    assert turn.agent_kind == "assessment"

    assert session.has_pending_assessment is True
    assert professor.calls == 0
    assert assessment.calls == 1


def test_stored_attempt_updates_state(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(session)

    updated = session.accept_stored_attempt(
        attempt_id="attempt-001",
        as_of=NOW + timedelta(seconds=2),
    )

    assert updated.performance_estimate == 1.0
    assert updated.distinct_assessment_count == 1
    assert session.has_pending_assessment is False


def test_two_turns_recompute_state_from_accepted_attempts(
    repository,
):
    repository.save_item(
        make_item(item_id="item-001", expected=5.0),
        revision=1,
    )

    repository.save_item(
        make_item(item_id="item-002", expected=7.0),
        revision=1,
    )

    repository.save_attempt(
        make_attempt(
            attempt_id="attempt-001",
            item_id="item-001",
            response="5",
        ),
        item_revision=1,
    )

    repository.save_attempt(
        make_attempt(
            attempt_id="attempt-002",
            item_id="item-002",
            response="7",
            submitted_at=NOW + timedelta(seconds=4),
        ),
        item_revision=1,
    )

    session, _, assessment = make_session(repository)

    start_turn(session)

    first_state = session.accept_stored_attempt(
        attempt_id="attempt-001",
        as_of=NOW + timedelta(seconds=2),
    )

    assert first_state.distinct_assessment_count == 1

    start_turn(
        session,
        item_id="item-002",
        decision_id="decision-002",
        requested_at=NOW + timedelta(seconds=3),
    )

    second_state = session.accept_stored_attempt(
        attempt_id="attempt-002",
        as_of=NOW + timedelta(seconds=5),
    )

    assert second_state.distinct_assessment_count == 2
    assert second_state.independent_success_count == 2
    assert second_state.state.value == "competent"

    assert assessment.calls == 2


def test_unmatched_agent_prompt_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    session, _, _ = make_session(
        repository,
        assessment_content="An unrelated question.",
    )

    with pytest.raises(ValueError, match="stored assessment prompt"):
        start_turn(session)

    assert session.has_pending_assessment is False


def test_second_turn_is_blocked_while_attempt_is_pending(
    repository,
):
    repository.save_item(make_item(), revision=1)

    session, _, _ = make_session(repository)

    start_turn(session)

    with pytest.raises(ValueError, match="pending assessment"):
        start_turn(
            session,
            decision_id="decision-002",
        )


def test_attempt_from_another_student_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(student_id="student-002"),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(session)

    with pytest.raises(ValueError, match="active teaching session"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )

    assert session.has_pending_assessment is True
    assert session.state.distinct_assessment_count == 0


def test_attempt_from_another_session_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(session_id="session-002"),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(session)

    with pytest.raises(ValueError, match="active teaching session"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )


def test_attempt_for_another_item_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_item(
        make_item(item_id="item-002"),
        revision=1,
    )

    repository.save_attempt(
        make_attempt(item_id="item-002"),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(session)

    with pytest.raises(ValueError, match="pending assessment"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )


def test_attempt_for_another_revision_is_rejected(repository):
    repository.save_item(make_item(), revision=1)
    repository.save_item(make_item(), revision=2)

    repository.save_attempt(
        make_attempt(),
        item_revision=2,
    )

    session, _, _ = make_session(repository)

    start_turn(session, revision=1)

    with pytest.raises(ValueError, match="pending assessment"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )


def test_attempt_before_turn_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(submitted_at=NOW),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(
        session,
        requested_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="predates"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )


def test_rejected_attempt_does_not_close_pending_turn(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(
            attempt_id="wrong-attempt",
            student_id="student-002",
        ),
        item_revision=1,
    )

    repository.save_attempt(
        make_attempt(
            attempt_id="correct-attempt",
        ),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    start_turn(session)

    with pytest.raises(ValueError, match="active teaching session"):
        session.accept_stored_attempt(
            attempt_id="wrong-attempt",
            as_of=NOW + timedelta(seconds=2),
        )

    assert session.has_pending_assessment is True

    updated = session.accept_stored_attempt(
        attempt_id="correct-attempt",
        as_of=NOW + timedelta(seconds=2),
    )

    assert updated.distinct_assessment_count == 1
    assert session.has_pending_assessment is False


def test_state_cannot_be_updated_without_pending_turn(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    session, _, _ = make_session(repository)

    with pytest.raises(ValueError, match="No assessment"):
        session.accept_stored_attempt(
            attempt_id="attempt-001",
            as_of=NOW + timedelta(seconds=2),
        )

"""
URPP Implementation 13C-2B.

Integration tests for a personalized Recoverable Numeric Session.

Each test uses an isolated, temporary, file-backed SQLite
database and recording Agent doubles.

No production database, external LLM, or real student data
is used.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.domain.learning.models import EvidenceType

from app.services.decision.models_v01 import (
    TeachingActionV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
)

from app.services.decision.personalized_numeric_session_adapter_v01 import (
    create_personalized_recoverable_numeric_session_v01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnOrchestratorV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)


class RecordingAgent:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def produce(self, *, context, decision):
        self.calls.append(
            (context, decision)
        )

        return self.content


class SQLiteTestStack:
    """
    A small test harness for independently reopening
    the same file-backed SQLite database.

    It uses the existing URPP repositories and services.
    """

    def __init__(
        self,
        database_path,
        *,
        initialize: bool,
        clock_time: datetime,
    ):
        self.database_path = database_path

        self.clock_time = [clock_time]

        self.engine = create_engine(
            f"sqlite+pysqlite:///{database_path}"
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()

            cursor.execute("PRAGMA foreign_keys=ON")

            cursor.close()

        if initialize:
            Base.metadata.create_all(self.engine)

        factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

        self.assessments = AssessmentRecordRepositoryV02(
            factory
        )

        self.assignments = NumericAssignmentRepositoryV01(
            self.assessments,
            clock=lambda: self.clock_time[0],
        )

        self.sessions = NumericSessionRecordRepositoryV01(
            self.assessments
        )

        self.last_professor_agent = None
        self.last_assessment_agent = None

    def make_service(
        self,
        *,
        request=None,
        student_id="student-001",
        session_id="session-001",
    ):
        professor = RecordingAgent(
            "Professor-generated teaching content."
        )

        assessment = RecordingAgent(
            "Agent-generated text is not the stored question."
        )

        self.last_professor_agent = professor
        self.last_assessment_agent = assessment

        personalized_orchestrator = (
            PersonalizedTeachingTurnOrchestratorV01(
                decision_engine=PersonalizedDecisionEngineV01(),
                professor_agent=professor,
                assessment_agent=assessment,
            )
        )

        return create_personalized_recoverable_numeric_session_v01(
            assessment_repository=self.assessments,
            assignment_repository=self.assignments,
            session_repository=self.sessions,
            personalized_turn_orchestrator=personalized_orchestrator,
            student_id=student_id,
            course_id="course-001",
            objective_id="objective-001",
            session_id=session_id,
            student_request=request,
        )

    def reopen(self, *, clock_time):
        """
        Dispose the current SQLAlchemy Engine and open
        a new Engine and new Repository instances.

        Existing tables are not recreated.
        """
        self.engine.dispose()

        return SQLiteTestStack(
            self.database_path,
            initialize=False,
            clock_time=clock_time,
        )


@pytest.fixture
def stack(tmp_path):
    database_path = tmp_path / "urpp_personalized_test.sqlite"

    environment = SQLiteTestStack(
        database_path,
        initialize=True,
        clock_time=NOW + timedelta(seconds=2),
    )

    yield environment

    environment.engine.dispose()


def make_item(
    *,
    item_id="item-001",
    objective_id="objective-001",
    alignment_verified=True,
    prompt="What is 2 + 3?",
    expected=5.0,
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id=objective_id,
        prompt=prompt,
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=alignment_verified,
    )


def make_request(
    kind,
    *,
    requested_at=NOW,
):
    return StudentLearningRequestV01(
        objective_id="objective-001",
        request_kind=kind,
        requested_at=requested_at,
    )


def deliver(
    service,
    *,
    item_id="item-001",
    decision_id="decision-001",
    requested_at=NOW,
):
    return service.deliver_numeric_assessment(
        assessment_item_id=item_id,
        item_revision=1,
        decision_id=decision_id,
        requested_at=requested_at,
    )


def test_independent_request_persists_assignment_and_stored_prompt(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    service = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    initial = service.start(started_at=NOW)

    assert initial.pending is None

    delivery = deliver(service)

    assert (
        delivery.selected_action
        == TeachingActionV01.INDEPENDENT_PRACTICE
    )

    assert delivery.prompt == "What is 2 + 3?"

    assert (
        delivery.prompt
        != "Agent-generated text is not the stored question."
    )

    assessment = stack.last_assessment_agent
    professor = stack.last_professor_agent

    assert len(assessment.calls) == 1
    assert not professor.calls

    received_context, received_decision = assessment.calls[0]

    assert (
        received_context.student_request.request_kind
        == StudentLearningRequestKindV01.TRY_INDEPENDENTLY
    )

    assert received_decision.selected_for_request is True

    stored = stack.assignments.load_assignment(
        delivery.assignment_id
    )

    assert stored.status == "pending"

    assert stored.decision_id == delivery.decision_id


def test_pending_assignment_survives_database_reopen(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    first = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC
        ),
    )

    first.start(started_at=NOW)

    delivery = deliver(first)

    reopened = stack.reopen(
        clock_time=NOW + timedelta(seconds=5)
    )

    try:
        restored = reopened.make_service().resume(
            as_of=NOW + timedelta(seconds=4)
        )

        assert restored.pending is not None

        assert (
            restored.pending.assignment_id
            == delivery.assignment_id
        )

        assert restored.pending.prompt == "What is 2 + 3?"

        assert restored.pending.item_revision == 1

    finally:
        reopened.engine.dispose()


def test_completed_answer_and_state_survive_database_reopen(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    first = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    first.start(started_at=NOW)

    delivery = deliver(first)

    after_submission = first.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=3),
    )

    assert after_submission.pending is None

    reopened = stack.reopen(
        clock_time=NOW + timedelta(seconds=5)
    )

    try:
        restored = reopened.make_service().resume(
            as_of=NOW + timedelta(seconds=4)
        )

        stored = reopened.assignments.load_assignment(
            delivery.assignment_id
        )

        assert stored.status == "completed"

        assert stored.completed_attempt_id is not None

        assert restored.pending is None

        assert restored.completed_assignment_ids == (
            delivery.assignment_id,
        )

        # A request to work independently does not establish
        # verified independent-assessment provenance.
        assert restored.state.independent_success_count == 0

        assert restored.state.state.value == "unknown"

    finally:
        reopened.engine.dispose()


def test_transfer_request_cannot_relabel_ordinary_problem(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    service = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.REQUEST_TRANSFER
        ),
    )

    service.start(started_at=NOW)

    with pytest.raises(
        ValueError,
        match="requires a transfer-tagged Assessment Item",
    ):
        deliver(service)

    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is None
    assert restored.completed_assignment_ids == ()
    assert restored.state.transfer_success_count == 0


def test_transfer_tagged_item_still_requires_trusted_approval(
    stack,
):
    # A TRANSFER_ATTEMPT tag is not a trusted design approval.
    transfer_tagged_item = make_item().model_copy(
        update={
            "evidence_type": EvidenceType.TRANSFER_ATTEMPT,
        }
    )

    stack.assessments.save_item(
        transfer_tagged_item,
        revision=1,
    )

    service = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.REQUEST_TRANSFER
        ),
    )

    service.start(started_at=NOW)

    with pytest.raises(
        ValueError,
        match="requires a trusted Transfer Design Approval",
    ):
        deliver(service)

    # The existing Session calls its Agent before this gate.
    # The guarantee here is no persisted Assignment, not
    # absence of an Agent call.
    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is None

    assert restored.completed_assignment_ids == ()

    assert restored.state.transfer_success_count == 0

    assert stack.sessions.list_assignment_ids(
        session_id="session-001",
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
    ) == ()


def test_pending_assignment_rejects_another_personalized_delivery(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    first = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    first.start(started_at=NOW)

    first_delivery = deliver(first)

    second = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC,
            requested_at=NOW + timedelta(seconds=1),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Complete the pending assignment",
    ):
        deliver(
            second,
            decision_id="decision-002",
            requested_at=NOW + timedelta(seconds=1),
        )

    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is not None

    assert (
        restored.pending.assignment_id
        == first_delivery.assignment_id
    )


def test_mismatched_objective_is_rejected_before_agent_call(
    stack,
):
    stack.assessments.save_item(
        make_item(
            objective_id="different-objective",
        ),
        revision=1,
    )

    service = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    service.start(started_at=NOW)

    with pytest.raises(
        ValueError,
        match="does not match the session scope",
    ):
        deliver(service)

    assert not stack.last_assessment_agent.calls
    assert not stack.last_professor_agent.calls

    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is None


def test_unverified_alignment_is_rejected_before_agent_call(
    stack,
):
    stack.assessments.save_item(
        make_item(
            alignment_verified=False,
        ),
        revision=1,
    )

    service = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    service.start(started_at=NOW)

    with pytest.raises(
        ValueError,
        match="alignment is not verified",
    ):
        deliver(service)

    assert not stack.last_assessment_agent.calls
    assert not stack.last_professor_agent.calls

    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=1)
    )

    assert restored.pending is None


def test_explanation_request_cannot_issue_numeric_assignment(
    stack,
):
    with pytest.raises(
        ValueError,
        match="assessment-related student request",
    ):
        stack.make_service(
            request=make_request(
                StudentLearningRequestKindV01.REQUEST_EXPLANATION
            ),
        )

    # Test Agents are constructed before the adapter rejects
    # this request. Verify that neither Agent was invoked.
    assert stack.last_assessment_agent is not None
    assert stack.last_professor_agent is not None
    assert not stack.last_assessment_agent.calls
    assert not stack.last_professor_agent.calls


def test_reused_decision_id_is_rejected_after_completion(
    stack,
):
    stack.assessments.save_item(
        make_item(),
        revision=1,
    )

    first = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.TRY_INDEPENDENTLY
        ),
    )

    first.start(started_at=NOW)

    delivery = deliver(first)

    first.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=3),
    )

    stack.clock_time[0] = NOW + timedelta(seconds=5)

    second = stack.make_service(
        request=make_request(
            StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC,
            requested_at=NOW + timedelta(seconds=4),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Decision ID has already been used",
    ):
        deliver(
            second,
            decision_id="decision-001",
            requested_at=NOW + timedelta(seconds=4),
        )

    restored = stack.make_service().resume(
        as_of=NOW + timedelta(seconds=4)
    )

    assert restored.pending is None

    assert restored.completed_assignment_ids == (
        delivery.assignment_id,
    )

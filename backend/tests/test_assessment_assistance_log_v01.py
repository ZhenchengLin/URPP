"""
URPP Implementation 13E-3A.

Tests exercise file-backed SQLite and the existing
Recoverable Numeric Session.

Recording an application-reported hint is not proof
of actual display or independently verified assistance.

No recorded event is promoted into mastery evidence.
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

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

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceKindV01,
    AssessmentAssistanceLogRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.evidence_driven_turn_wiring_v01 import (
    create_evidence_driven_personalized_turn_v01,
)

from app.services.decision.personalized_numeric_session_adapter_v01 import (
    create_personalized_recoverable_numeric_session_v01,
)


NOW = datetime(
    2026,
    9,
    20,
    tzinfo=timezone.utc,
)


class RecordingAgent:
    def __init__(self):
        self.calls = []

    def produce(
        self,
        *,
        context,
        decision,
    ):
        self.calls.append(
            (context, decision)
        )

        return "Agent output is not assessment evidence."


def open_stack(path, *, initialize):
    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    if initialize:
        Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(
        factory
    )

    assignments = NumericAssignmentRepositoryV01(
        assessments,
        clock=lambda: NOW + timedelta(seconds=4),
    )

    sessions = NumericSessionRecordRepositoryV01(
        assessments
    )

    assistance = AssessmentAssistanceLogRepositoryV01(
        factory,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    orchestrator = (
        create_evidence_driven_personalized_turn_v01(
            professor_agent=RecordingAgent(),
            assessment_agent=RecordingAgent(),
        )
    )

    service = create_personalized_recoverable_numeric_session_v01(
        assessment_repository=assessments,
        assignment_repository=assignments,
        session_repository=sessions,
        personalized_turn_orchestrator=orchestrator,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
    )

    return engine, assessments, assistance, service


@pytest.fixture
def environment(tmp_path):
    path = tmp_path / "assistance_events.sqlite"

    engine, assessments, assistance, service = open_stack(
        path,
        initialize=True,
    )

    item = AssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="What is 2 + 3?",
        rubric=NumericRubricV02(
            expected_value=5.0,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )

    assessments.save_item(
        item,
        revision=1,
    )

    service.start(
        started_at=NOW,
    )

    delivery = service.deliver_numeric_assessment(
        assessment_item_id=item.assessment_item_id,
        item_revision=1,
        decision_id="decision-001",
        requested_at=NOW,
    )

    yield (
        path,
        engine,
        assistance,
        service,
        delivery,
    )

    engine.dispose()


def record_hint(
    assistance,
    delivery,
):
    return assistance.record_application_assistance(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
        kind=AssessmentAssistanceKindV01.HINT,
        content="Consider adding 2 and 3.",
    )


def list_records(
    assistance,
    delivery,
):
    return assistance.list_assistance_for_assignment(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
    )


def test_assistance_is_not_inferred_from_assessment_delivery(
    environment,
):
    _, _, assistance, _, delivery = environment

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_reported_hint_is_persisted_and_restored_after_reopen(
    environment,
):
    path, engine, assistance, _, delivery = environment

    reported = record_hint(
        assistance,
        delivery,
    )

    assert reported.kind == (
        AssessmentAssistanceKindV01.HINT
    )

    assert reported.content_sha256 == sha256(
        b"Consider adding 2 and 3."
    ).hexdigest()

    assert reported.source == "application_reported"

    engine.dispose()

    reopened_engine, _, reopened_log, _ = open_stack(
        path,
        initialize=False,
    )

    try:
        assert list_records(
            reopened_log,
            delivery,
        ) == (reported,)

    finally:
        reopened_engine.dispose()


def test_solution_and_hint_have_separate_events(
    environment,
):
    _, _, assistance, _, delivery = environment

    first = record_hint(
        assistance,
        delivery,
    )

    second = assistance.record_application_assistance(
        assignment_id=delivery.assignment_id,
        student_id="student-001",
        session_id="session-001",
        kind=AssessmentAssistanceKindV01.SOLUTION,
        content="The answer is 5.",
    )

    records = list_records(
        assistance,
        delivery,
    )

    assert len(records) == 2

    assert {
        record.event_id
        for record in records
    } == {
        first.event_id,
        second.event_id,
    }

    assert {
        record.kind
        for record in records
    } == {
        AssessmentAssistanceKindV01.HINT,
        AssessmentAssistanceKindV01.SOLUTION,
    }


def test_wrong_student_or_session_cannot_record_or_read(
    environment,
):
    _, _, assistance, _, delivery = environment

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        assistance.record_application_assistance(
            assignment_id=delivery.assignment_id,
            student_id="other-student",
            session_id="session-001",
            kind=AssessmentAssistanceKindV01.HINT,
            content="Hint.",
        )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        assistance.list_assistance_for_assignment(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="other-session",
        )

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_invalid_event_does_not_create_a_record(
    environment,
):
    _, _, assistance, _, delivery = environment

    with pytest.raises(
        TypeError,
        match="AssessmentAssistanceKindV01",
    ):
        assistance.record_application_assistance(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
            kind="hint",
            content="Hint.",
        )

    with pytest.raises(
        ValueError,
        match="nonempty string",
    ):
        assistance.record_application_assistance(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
            kind=AssessmentAssistanceKindV01.HINT,
            content="  ",
        )

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_help_cannot_be_recorded_after_submission(
    environment,
):
    _, _, assistance, service, delivery = environment

    after_submission = service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert after_submission.pending is None

    with pytest.raises(
        ValueError,
        match="after Assignment completion",
    ):
        record_hint(
            assistance,
            delivery,
        )

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_help_record_does_not_fabricate_mastery_evidence(
    environment,
):
    _, _, assistance, service, delivery = environment

    record_hint(
        assistance,
        delivery,
    )

    completed = service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert completed.pending is None

    assert completed.state.state.value == "unknown"

    assert completed.state.included_evidence_ids == []

    assert completed.state.independent_success_count == 0

    assert len(
        completed.state.excluded_evidence_ids
    ) == 1

    excluded_id = (
        completed.state.excluded_evidence_ids[0]
    )

    assert (
        completed.state.exclusion_reasons[excluded_id]
        == "assistance_level_unknown"
    )

    assert len(
        list_records(
            assistance,
            delivery,
        )
    ) == 1


# ---------------------------------------------------------
# Implementation 13E-3B:
# Application-reported presentation integration.
# ---------------------------------------------------------

from app.services.decision.assessment_assistance_presentation_v01 import (
    AssessmentAssistancePresentationServiceV01,
    AssistancePresentationFailedV01,
    AssistancePresentationUnloggedV01,
)


class RecordingAssistancePresenter:
    """
    Test double for an application content presenter.

    Recording a callback in this test does not simulate
    a real browser, student attention, or authentication.
    """

    def __init__(
        self,
        *,
        result=True,
        error=None,
    ):
        self.result = result
        self.error = error
        self.calls = []

    def present(
        self,
        *,
        assignment_id,
        student_id,
        session_id,
        kind,
        content,
    ):
        self.calls.append(
            {
                "assignment_id": assignment_id,
                "student_id": student_id,
                "session_id": session_id,
                "kind": kind,
                "content": content,
            }
        )

        if self.error is not None:
            raise self.error

        return self.result


def make_presentation_service(
    environment,
    presenter,
):
    _, engine, assistance, _, _ = environment

    return AssessmentAssistancePresentationServiceV01(
        session_factory=sessionmaker(
            bind=engine,
            expire_on_commit=False,
        ),
        assistance_log=assistance,
        presenter=presenter,
    )


def present_hint(
    presentation_service,
    delivery,
    *,
    student_id="student-001",
    session_id="session-001",
    content="Consider adding 2 and 3.",
):
    return presentation_service.present_assistance(
        assignment_id=delivery.assignment_id,
        student_id=student_id,
        session_id=session_id,
        kind=AssessmentAssistanceKindV01.HINT,
        content=content,
    )


def test_presentation_success_persists_application_report(
    environment,
):
    _, _, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    result = present_hint(
        presentation_service,
        delivery,
    )

    assert len(presenter.calls) == 1

    assert presenter.calls[0]["assignment_id"] == (
        delivery.assignment_id
    )

    assert presenter.calls[0]["kind"] == (
        AssessmentAssistanceKindV01.HINT
    )

    assert result.source == "application_reported"

    assert result.content_sha256 == sha256(
        b"Consider adding 2 and 3."
    ).hexdigest()

    assert list_records(
        assistance,
        delivery,
    ) == (result,)


def test_failed_presentation_does_not_create_assistance_event(
    environment,
):
    _, _, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter(
        result=False,
    )

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        AssistancePresentationFailedV01,
        match="did not report",
    ):
        present_hint(
            presentation_service,
            delivery,
        )

    assert len(presenter.calls) == 1

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_presenter_exception_does_not_create_assistance_event(
    environment,
):
    _, _, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter(
        error=RuntimeError("Presentation unavailable."),
    )

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        AssistancePresentationFailedV01,
        match="raised an exception",
    ):
        present_hint(
            presentation_service,
            delivery,
        )

    assert len(presenter.calls) == 1

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_invalid_scope_rejected_before_presenter_is_called(
    environment,
):
    _, _, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        present_hint(
            presentation_service,
            delivery,
            student_id="other-student",
        )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        present_hint(
            presentation_service,
            delivery,
            session_id="other-session",
        )

    assert presenter.calls == []

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_completed_assignment_rejected_before_presentation(
    environment,
):
    _, _, assistance, numeric_service, delivery = environment

    completed = numeric_service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert completed.pending is None

    presenter = RecordingAssistancePresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        ValueError,
        match="after Assignment completion",
    ):
        present_hint(
            presentation_service,
            delivery,
        )

    assert presenter.calls == []

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_invalid_input_rejected_before_presentation(
    environment,
):
    _, _, assistance, _, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        ValueError,
        match="nonempty string",
    ):
        present_hint(
            presentation_service,
            delivery,
            content="   ",
        )

    with pytest.raises(
        TypeError,
        match="AssessmentAssistanceKindV01",
    ):
        presentation_service.present_assistance(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
            kind="hint",
            content="Consider adding 2 and 3.",
        )

    assert presenter.calls == []

    assert list_records(
        assistance,
        delivery,
    ) == ()


def test_presentation_success_then_assignment_completion_reports_partial_operation(
    environment,
):
    """
    Presentation and SQLite logging are not atomic.

    Simulate completion of the Assignment during the
    presentation callback, before the service attempts
    to persist the assistance event.

    The error must explicitly indicate that assistance
    may have been provided without a durable log.
    """

    _, _, assistance, numeric_service, delivery = environment

    class CompletingPresenter:
        def __init__(self):
            self.calls = 0

        def present(
            self,
            *,
            assignment_id,
            student_id,
            session_id,
            kind,
            content,
        ):
            self.calls += 1

            numeric_service.submit_numeric_answer(
                assignment_id=assignment_id,
                response_text="5",
                as_of=NOW + timedelta(seconds=5),
            )

            return True

    presenter = CompletingPresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    with pytest.raises(
        AssistancePresentationUnloggedV01,
        match="without a durable log",
    ):
        present_hint(
            presentation_service,
            delivery,
        )

    assert presenter.calls == 1

    assert list_records(
        assistance,
        delivery,
    ) == ()

    restored = numeric_service.resume(
        as_of=NOW + timedelta(seconds=5),
    )

    assert restored.pending is None

    assert restored.state.included_evidence_ids == []


def test_presented_assistance_survives_database_reopen_without_creating_mastery(
    environment,
):
    path, engine, assistance, numeric_service, delivery = environment

    presenter = RecordingAssistancePresenter()

    presentation_service = make_presentation_service(
        environment,
        presenter,
    )

    record = present_hint(
        presentation_service,
        delivery,
    )

    completed = numeric_service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert completed.state.included_evidence_ids == []

    assert completed.state.independent_success_count == 0

    engine.dispose()

    reopened_engine, _, reopened_log, reopened_service = (
        open_stack(
            path,
            initialize=False,
        )
    )

    try:
        restored = reopened_service.resume(
            as_of=NOW + timedelta(seconds=5),
        )

        assert restored.pending is None

        assert restored.state.state.value == "unknown"

        assert restored.state.included_evidence_ids == []

        assert restored.state.independent_success_count == 0

        assert list_records(
            reopened_log,
            delivery,
        ) == (record,)

        assert len(presenter.calls) == 1

    finally:
        reopened_engine.dispose()

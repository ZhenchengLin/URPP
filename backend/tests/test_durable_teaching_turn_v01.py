"""14B-2B-1: synthetic fixtures and temporary SQLite only."""

from datetime import datetime, timezone
from hashlib import sha256

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.learning.models import ObjectiveStateLabel

from app.repositories.course_teaching_trace_v01 import (
    course_teaching_traces_v01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.durable_teaching_turn_v01 import (
    DurableCourseTeachingTurnV01,
    TeachingTurnRecoveryRequiredV01,
    course_teaching_turn_intents_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)

COURSE = "synthetic-course-001"
OBJECTIVE = "synthetic-objective-001"
REVISION = "synthetic-pack-revision-001"


def make_pack():
    content = "Synthetic matrix lesson for test use only."

    source = CourseSourceV01(
        course_id=COURSE,
        source_id="synthetic-source-001",
        source_revision="source-revision-001",
        source_locator="synthetic-fixture:section-1",
        content=content,
        content_sha256=sha256(
            content.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE,
        objective_id=OBJECTIVE,
        description="Explain a synthetic matrix lesson.",
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE,
        pack_id="synthetic-pack-001",
        pack_revision=REVISION,
        objectives=(objective,),
        sources=(source,),
    )


def make_state():
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id=COURSE,
        objective_id=OBJECTIVE,
        as_of=NOW,
    )

    # Test-only routing fixture, not assessment-backed mastery.
    return state.model_copy(
        update={"state": ObjectiveStateLabel.STRONG}
    )


def make_request():
    return StudentLearningRequestV01(
        objective_id=OBJECTIVE,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=NOW,
    )


class CountingProfessor:
    def __init__(self):
        self.calls = 0

    def produce(self, *, context, decision, course_knowledge):
        self.calls += 1
        return (
            "Synthetic Professor explanation from "
            + course_knowledge.sources[0].source_locator
        )


class CountingEngine:
    def __init__(self):
        self.calls = 0
        self.delegate = PersonalizedDecisionEngineV01()

    def decide(self, context):
        self.calls += 1
        return self.delegate.decide(context)


def make_storage(tmp_path):
    path = tmp_path / "durable-course-turn.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    # Explicit temporary-test schema setup only.
    course_teaching_traces_v01.create(
        engine,
        checkfirst=False,
    )

    course_teaching_turn_intents_v01.create(
        engine,
        checkfirst=False,
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    return path, engine, factory


def make_service(factory, engine=None, professor=None):
    if engine is None:
        engine = CountingEngine()

    if professor is None:
        professor = CountingProfessor()

    service = DurableCourseTeachingTurnV01(
        session_factory=factory,
        decision_engine=engine,
        professor_agent=professor,
    )

    return service, engine, professor


def execute(service, **overrides):
    values = {
        "pack": make_pack(),
        "trace_id": "trace-001",
        "student_id": "student-001",
        "course_id": COURSE,
        "objective_id": OBJECTIVE,
        "expected_pack_revision": REVISION,
        "decision_id": "decision-001",
        "requested_at": NOW,
        "generated_at": NOW,
        "student_request": make_request(),
    }

    values.update(overrides)

    return service.run_or_resume(
        make_state(),
        **values,
    )


def test_first_turn_and_identical_retry_call_professor_once(tmp_path):
    _, engine, factory = make_storage(tmp_path)
    service, decisions, professor = make_service(factory)

    first = execute(service)
    second = execute(service)

    assert first == second
    assert first.execution_status == "generated"
    assert decisions.calls == 1
    assert professor.calls == 1

    engine.dispose()


def test_retry_recovers_after_database_reopen(tmp_path):
    path, engine, factory = make_storage(tmp_path)

    first_service, decisions, professor = make_service(factory)
    first = execute(first_service)

    assert decisions.calls == 1
    assert professor.calls == 1

    engine.dispose()

    reopened_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    reopened_factory = sessionmaker(
        bind=reopened_engine,
        expire_on_commit=False,
    )

    recovered_service, second_decisions, second_professor = (
        make_service(reopened_factory)
    )

    recovered = execute(recovered_service)

    assert recovered == first
    assert second_decisions.calls == 0
    assert second_professor.calls == 0

    reopened_engine.dispose()


def test_changed_request_cannot_reuse_trace(tmp_path):
    _, engine, factory = make_storage(tmp_path)
    service, decisions, professor = make_service(factory)

    execute(service)

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        execute(
            service,
            student_request=StudentLearningRequestV01(
                objective_id=OBJECTIVE,
                request_kind=(
                    StudentLearningRequestKindV01.REQUEST_HINT
                ),
                requested_at=NOW,
            ),
        )

    assert decisions.calls == 1
    assert professor.calls == 1

    engine.dispose()


def test_same_decision_with_other_trace_id_is_rejected_before_agent(
    tmp_path,
):
    _, engine, factory = make_storage(tmp_path)
    service, decisions, professor = make_service(factory)

    execute(service)

    with pytest.raises(
        ValueError,
        match="already reserved",
    ):
        execute(service, trace_id="trace-002")

    assert decisions.calls == 1
    assert professor.calls == 1

    engine.dispose()


def test_reserved_turn_without_trace_fails_closed(tmp_path):
    _, engine, factory = make_storage(tmp_path)

    class FailingProfessor:
        def __init__(self):
            self.calls = 0

        def produce(self, *, context, decision, course_knowledge):
            self.calls += 1
            raise RuntimeError("Simulated generation interruption.")

    professor = FailingProfessor()

    service, decisions, _ = make_service(
        factory,
        professor=professor,
    )

    with pytest.raises(
        RuntimeError,
        match="generation interruption",
    ):
        execute(service)

    with pytest.raises(
        TeachingTurnRecoveryRequiredV01,
        match="Do not regenerate",
    ):
        execute(service)

    assert decisions.calls == 1
    assert professor.calls == 1

    engine.dispose()


def test_commit_before_response_can_be_recovered(tmp_path):
    _, engine, factory = make_storage(tmp_path)
    service, decisions, professor = make_service(factory)

    original_save = service._traces.save_generated

    def save_then_interrupt(*args, **kwargs):
        original_save(*args, **kwargs)
        raise RuntimeError("Simulated interruption after Trace commit.")

    service._traces.save_generated = save_then_interrupt

    with pytest.raises(
        RuntimeError,
        match="after Trace commit",
    ):
        execute(service)

    # A new wrapper represents a restarted application.
    recovered_service, second_decisions, second_professor = (
        make_service(factory)
    )

    recovered = execute(recovered_service)

    assert recovered.trace_id == "trace-001"
    assert recovered.execution_status == "generated"

    assert decisions.calls == 1
    assert professor.calls == 1

    assert second_decisions.calls == 0
    assert second_professor.calls == 0

    engine.dispose()


def test_student_scope_mismatch_fails_before_reservation(tmp_path):
    _, engine, factory = make_storage(tmp_path)
    service, decisions, professor = make_service(factory)

    with pytest.raises(
        ValueError,
        match="identity or scope mismatch",
    ):
        execute(service, student_id="another-student")

    assert decisions.calls == 0
    assert professor.calls == 0

    engine.dispose()

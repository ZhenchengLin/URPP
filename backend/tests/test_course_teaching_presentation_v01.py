"""
URPP 14B-2B-2 tests.

All course content is synthetic. Presentation reports here
are simulated application events, not verified student views.
Only temporary SQLite databases are used.
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.domain.learning.models import ObjectiveStateLabel

from app.repositories.course_teaching_trace_v01 import (
    CourseTeachingTraceRepositoryV01,
    course_teaching_traces_v01,
)

from app.repositories.course_teaching_presentation_v01 import (
    CourseTeachingPresentationRepositoryV01,
    course_teaching_presentations_v01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)

from app.services.course_knowledge.teaching_harness_v01 import (
    CourseGroundedTeachingHarnessV01,
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
PRESENTED_AT = NOW + timedelta(seconds=1)

COURSE = "synthetic-course-001"
OBJECTIVE = "synthetic-objective-001"
PACK_REVISION = "synthetic-pack-revision-001"


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
        pack_revision=PACK_REVISION,
        objectives=(objective,),
        sources=(source,),
    )


class FakeProfessor:
    def produce(self, *, context, decision, course_knowledge):
        return (
            "Synthetic Professor explanation from "
            + course_knowledge.sources[0].source_locator
        )


def make_result(decision_id):
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id=COURSE,
        objective_id=OBJECTIVE,
        as_of=NOW,
    )

    # Test-only routing condition, not assessment-backed mastery.
    state = state.model_copy(
        update={"state": ObjectiveStateLabel.STRONG}
    )

    harness = CourseGroundedTeachingHarnessV01(
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=FakeProfessor(),
    )

    request = StudentLearningRequestV01(
        objective_id=OBJECTIVE,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=NOW,
    )

    return harness.run_professor_turn(
        state,
        pack=make_pack(),
        course_id=COURSE,
        objective_id=OBJECTIVE,
        expected_pack_revision=PACK_REVISION,
        decision_id=decision_id,
        requested_at=NOW,
        student_request=request,
    )


def make_storage(tmp_path):
    path = tmp_path / "course-presentation.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    # Test-only explicit schema provisioning.
    # Production startup/migration is not implemented here.
    course_teaching_traces_v01.create(
        engine,
        checkfirst=False,
    )

    course_teaching_presentations_v01.create(
        engine,
        checkfirst=False,
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    traces = CourseTeachingTraceRepositoryV01(factory)
    presentations = CourseTeachingPresentationRepositoryV01(factory)

    traces.save_generated(
        make_result("decision-001"),
        trace_id="trace-001",
        student_id="student-001",
        generated_at=NOW,
    )

    return path, engine, factory, traces, presentations


def load(presentations, trace_id="trace-001"):
    return presentations.load_state(
        trace_id=trace_id,
        student_id="student-001",
        course_id=COURSE,
        objective_id=OBJECTIVE,
    )


def report(
    presentations,
    *,
    trace_id="trace-001",
    event_id="presentation-event-001",
    reported_at=PRESENTED_AT,
    surface="local_cli",
):
    return presentations.record_presentation(
        trace_id=trace_id,
        student_id="student-001",
        course_id=COURSE,
        objective_id=OBJECTIVE,
        event_id=event_id,
        reported_at=reported_at,
        surface=surface,
    )


def test_initial_state_is_generated_without_presentation(tmp_path):
    _, engine, _, _, presentations = make_storage(tmp_path)

    state = load(presentations)

    assert state.status == "generated"
    assert state.presentation is None

    assert state.trace.result.execution_status == "generated"

    engine.dispose()


def test_presentation_event_survives_database_reopen(tmp_path):
    path, engine, _, _, presentations = make_storage(tmp_path)

    original = load(presentations)

    reported = report(presentations)

    assert reported.status == "presentation_reported"
    assert reported.presentation is not None

    assert reported.presentation.event_id == "presentation-event-001"
    assert reported.presentation.surface == "local_cli"

    # Presentation must not rewrite the original generated Trace.
    assert reported.trace == original.trace

    engine.dispose()

    reopened_engine = create_engine(
        f"sqlite+pysqlite:///{path}"
    )

    reopened_factory = sessionmaker(
        bind=reopened_engine,
        expire_on_commit=False,
    )

    recovered = CourseTeachingPresentationRepositoryV01(
        reopened_factory
    ).load_state(
        trace_id="trace-001",
        student_id="student-001",
        course_id=COURSE,
        objective_id=OBJECTIVE,
    )

    assert recovered == reported
    assert recovered.trace == original.trace

    reopened_engine.dispose()


def test_identical_presentation_report_is_idempotent(tmp_path):
    _, engine, _, _, presentations = make_storage(tmp_path)

    first = report(presentations)
    second = report(presentations)

    assert second == first
    assert second.presentation.event_id == "presentation-event-001"

    engine.dispose()


def test_conflicting_event_for_same_trace_is_rejected(tmp_path):
    _, engine, _, _, presentations = make_storage(tmp_path)

    first = report(presentations)

    with pytest.raises(
        ValueError,
        match="conflicts with the original",
    ):
        report(
            presentations,
            event_id="presentation-event-002",
        )

    assert load(presentations) == first

    engine.dispose()


def test_reused_event_id_for_other_trace_is_rejected(tmp_path):
    _, engine, _, traces, presentations = make_storage(tmp_path)

    traces.save_generated(
        make_result("decision-002"),
        trace_id="trace-002",
        student_id="student-001",
        generated_at=NOW,
    )

    original = report(presentations)

    with pytest.raises(
        ValueError,
        match="already used for another Trace",
    ):
        report(
            presentations,
            trace_id="trace-002",
            event_id="presentation-event-001",
        )

    assert load(presentations) == original
    assert load(presentations, "trace-002").status == "generated"

    engine.dispose()


def test_missing_or_wrong_scope_trace_cannot_be_reported(tmp_path):
    _, engine, _, _, presentations = make_storage(tmp_path)

    with pytest.raises(LookupError):
        report(
            presentations,
            trace_id="nonexistent-trace",
        )

    with pytest.raises(
        ValueError,
        match="scope mismatch",
    ):
        presentations.record_presentation(
            trace_id="trace-001",
            student_id="another-student",
            course_id=COURSE,
            objective_id=OBJECTIVE,
            event_id="presentation-event-wrong-scope",
            reported_at=PRESENTED_AT,
            surface="local_cli",
        )

    assert load(presentations).status == "generated"

    engine.dispose()


def test_presentation_cannot_precede_generation(tmp_path):
    _, engine, _, _, presentations = make_storage(tmp_path)

    with pytest.raises(
        ValueError,
        match="cannot precede generation",
    ):
        report(
            presentations,
            reported_at=NOW - timedelta(seconds=1),
        )

    assert load(presentations).status == "generated"

    engine.dispose()


def test_corrupted_presentation_digest_is_detected(tmp_path):
    _, engine, factory, _, presentations = make_storage(tmp_path)

    report(presentations)

    with factory() as session:
        with session.begin():
            session.execute(
                update(course_teaching_presentations_v01)
                .where(
                    course_teaching_presentations_v01.c.trace_id
                    == "trace-001"
                )
                .values(content_sha256="0" * 64)
            )

    with pytest.raises(
        ValueError,
        match="content digest mismatch",
    ):
        load(presentations)

    engine.dispose()


def test_repository_does_not_create_presentation_table(tmp_path):
    database = tmp_path / "missing-presentation-table.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{database}"
    )

    # The generated Trace table exists, but the
    # Presentation table is intentionally not created.
    course_teaching_traces_v01.create(
        engine,
        checkfirst=False,
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    # A valid generated Trace must exist so load_state()
    # reaches the missing Presentation table query.
    trace_repository = CourseTeachingTraceRepositoryV01(
        factory
    )

    trace_repository.save_generated(
        make_result("decision-001"),
        trace_id="trace-001",
        student_id="student-001",
        generated_at=NOW,
    )

    repository = CourseTeachingPresentationRepositoryV01(
        factory
    )

    with pytest.raises(
        Exception,
        match="course_teaching_presentations_v01",
    ):
        repository.load_state(
            trace_id="trace-001",
            student_id="student-001",
            course_id=COURSE,
            objective_id=OBJECTIVE,
        )

    # A read failure must not silently provision the table.
    from sqlalchemy import inspect

    assert (
        "course_teaching_presentations_v01"
        not in inspect(engine).get_table_names()
    )

    engine.dispose()

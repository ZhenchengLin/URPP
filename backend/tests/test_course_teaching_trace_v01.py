"""
URPP Implementation 14B-2A tests.

Synthetic course material only. File-backed test databases
are created under pytest's temporary directory.

These tests verify generated-result storage and recovery.
They do not establish delivery or exactly-once generation.
"""

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker

from app.domain.learning.models import (
    ObjectiveStateLabel,
)

from app.repositories.course_teaching_trace_v01 import (
    CourseTeachingTraceRepositoryV01,
    course_teaching_traces_v01,
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


NOW = datetime(
    2026, 9, 22,
    tzinfo=timezone.utc,
)

COURSE_ID = "synthetic-course-001"
OBJECTIVE_ID = "synthetic-objective-001"

PACK_REVISION = "synthetic-pack-revision-001"

CONTENT = (
    "Synthetic explanation of a matrix decomposition."
)


def make_pack():
    source = CourseSourceV01(
        course_id=COURSE_ID,
        source_id="synthetic-source-001",
        source_revision="source-revision-001",
        source_locator="synthetic-fixture:section-1",
        content=CONTENT,
        content_sha256=sha256(
            CONTENT.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        description=(
            "Explain a synthetic matrix decomposition."
        ),
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE_ID,
        pack_id="synthetic-pack-001",
        pack_revision=PACK_REVISION,
        objectives=(objective,),
        sources=(source,),
    )


class FakeCourseProfessor:
    def __init__(self):
        self.calls = 0

    def produce(
        self,
        *,
        context,
        decision,
        course_knowledge,
    ):
        self.calls += 1

        return (
            "Synthetic explanation using "
            f"{course_knowledge.sources[0].source_locator}."
        )


def make_generated_result():
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        as_of=NOW,
    )

    # Synthetic routing condition, not a mastery claim.
    state = state.model_copy(
        update={
            "state": ObjectiveStateLabel.STRONG,
        }
    )

    professor = FakeCourseProfessor()

    harness = CourseGroundedTeachingHarnessV01(
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=professor,
    )

    request = StudentLearningRequestV01(
        objective_id=OBJECTIVE_ID,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=NOW,
    )

    result = harness.run_professor_turn(
        state,
        pack=make_pack(),
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        expected_pack_revision=PACK_REVISION,
        decision_id="decision-trace-001",
        requested_at=NOW,
        student_request=request,
    )

    assert professor.calls == 1

    return result


def make_repository(tmp_path):
    database = tmp_path / "teaching-traces.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{database}"
    )

    # Test-only explicit schema setup. The production
    # repository never creates or migrates its table.
    course_teaching_traces_v01.create(
        engine,
        checkfirst=False,
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    return database, engine, CourseTeachingTraceRepositoryV01(
        factory
    )


def save(
    repository,
    result,
    *,
    trace_id="trace-001",
    student_id="student-001",
):
    return repository.save_generated(
        result,
        trace_id=trace_id,
        student_id=student_id,
        generated_at=NOW,
    )


def test_generated_trace_survives_database_reopen(
    tmp_path,
):
    database, engine, repository = make_repository(
        tmp_path
    )

    result = make_generated_result()

    stored = save(repository, result)

    assert stored.execution_status == "generated"
    assert stored.trace_id == "trace-001"
    assert stored.student_id == "student-001"

    assert stored.result == result

    assert (
        stored.result.completed_turn.content
        == result.completed_turn.content
    )

    assert (
        stored.result.source_refs
        == result.course_knowledge.objective.source_refs
    )

    assert (
        stored.result.completed_turn.decision.decision.decision_id
        == "decision-trace-001"
    )

    engine.dispose()

    # A new Engine and Session factory simulate the
    # repository being reconstructed after process restart.
    reopened_engine = create_engine(
        f"sqlite+pysqlite:///{database}"
    )

    reopened_factory = sessionmaker(
        bind=reopened_engine,
        expire_on_commit=False,
    )

    recovered_repository = (
        CourseTeachingTraceRepositoryV01(
            reopened_factory
        )
    )

    recovered = recovered_repository.load(
        trace_id="trace-001",
        student_id="student-001",
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
    )

    assert recovered == stored
    assert recovered.result == result

    reopened_engine.dispose()


def test_duplicate_trace_id_cannot_overwrite_result(
    tmp_path,
):
    _, engine, repository = make_repository(
        tmp_path
    )

    result = make_generated_result()

    first = save(repository, result)

    with pytest.raises(
        ValueError,
        match="Trace ID already exists",
    ):
        save(repository, result)

    recovered = repository.load(
        trace_id="trace-001",
        student_id="student-001",
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
    )

    assert recovered == first

    engine.dispose()


def test_duplicate_decision_cannot_create_second_trace(
    tmp_path,
):
    _, engine, repository = make_repository(
        tmp_path
    )

    result = make_generated_result()

    save(repository, result)

    with pytest.raises(
        ValueError,
        match="decision already exists",
    ):
        save(
            repository,
            result,
            trace_id="trace-002",
        )

    with pytest.raises(
        LookupError,
        match="was not found",
    ):
        repository.load(
            trace_id="trace-002",
            student_id="student-001",
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
        )

    engine.dispose()


def test_load_rejects_wrong_student_or_course_scope(
    tmp_path,
):
    _, engine, repository = make_repository(
        tmp_path
    )

    save(
        repository,
        make_generated_result(),
    )

    with pytest.raises(
        ValueError,
        match="scope mismatch",
    ):
        repository.load(
            trace_id="trace-001",
            student_id="another-student",
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
        )

    with pytest.raises(
        ValueError,
        match="scope mismatch",
    ):
        repository.load(
            trace_id="trace-001",
            student_id="student-001",
            course_id="another-course",
            objective_id=OBJECTIVE_ID,
        )

    engine.dispose()


def test_invalid_source_refs_are_not_persisted(
    tmp_path,
):
    _, engine, repository = make_repository(
        tmp_path
    )

    result = make_generated_result()

    invalid = replace(
        result,
        source_refs=(),
    )

    with pytest.raises(
        ValueError,
        match="source references do not match",
    ):
        save(repository, invalid)

    with pytest.raises(LookupError):
        repository.load(
            trace_id="trace-001",
            student_id="student-001",
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
        )

    engine.dispose()


def test_non_generated_result_is_not_persisted(
    tmp_path,
):
    _, engine, repository = make_repository(
        tmp_path
    )

    result = make_generated_result()

    invalid = replace(
        result,
        execution_status="presented",
    )

    with pytest.raises(
        ValueError,
        match="Only generated",
    ):
        save(repository, invalid)

    engine.dispose()


def test_repository_never_creates_missing_schema(
    tmp_path,
):
    database = tmp_path / "empty.sqlite"

    engine = create_engine(
        f"sqlite+pysqlite:///{database}"
    )

    factory = sessionmaker(
        bind=engine,
    )

    repository = CourseTeachingTraceRepositoryV01(
        factory
    )

    with pytest.raises(
        Exception,
        match="course_teaching_traces_v01",
    ):
        save(
            repository,
            make_generated_result(),
        )

    engine.dispose()

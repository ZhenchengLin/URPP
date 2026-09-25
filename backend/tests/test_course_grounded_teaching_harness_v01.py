"""
URPP Implementation 14B-1 tests.

All course content and learning states in this module are
synthetic test fixtures.

The tests establish routing and contract behavior, not actual
teaching quality, student learning, or course authorization.
"""

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.domain.learning.models import (
    ObjectiveStateLabel,
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

from app.services.decision.models_v01 import (
    TeachingActionV01,
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

COURSE_ID = "course-001"
OBJECTIVE_ID = "objective-001"
PACK_REVISION = "synthetic-pack-revision-001"

CONTENT = (
    "Synthetic teaching fixture about matrix decomposition."
)


def make_pack(
    *,
    visibility="student_visible",
    review_status="approved",
):
    source = CourseSourceV01(
        course_id=COURSE_ID,
        source_id="synthetic-source-001",
        source_revision="source-revision-001",
        source_locator="synthetic-fixture:section-1",
        content=CONTENT,
        content_sha256=sha256(
            CONTENT.encode("utf-8")
        ).hexdigest(),
        visibility=visibility,
        use_permission="approved_for_local_teaching",
        review_status=review_status,
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


def make_state(
    *,
    course_id=COURSE_ID,
    objective_id=OBJECTIVE_ID,
    strong=False,
):
    state = estimate_objective_state(
        [],
        student_id="student-001",
        course_id=course_id,
        objective_id=objective_id,
        as_of=NOW,
    )

    if strong:
        # Synthetic routing fixture only.
        # Not a claim backed by assessment evidence.
        return state.model_copy(
            update={
                "state": ObjectiveStateLabel.STRONG,
            }
        )

    return state


def make_request(
    *,
    objective_id=OBJECTIVE_ID,
):
    return StudentLearningRequestV01(
        objective_id=objective_id,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=NOW,
    )


class RecordingDecisionEngine:
    def __init__(self):
        self.delegate = PersonalizedDecisionEngineV01()
        self.calls = []

    def decide(self, context):
        self.calls.append(context)
        return self.delegate.decide(context)


class RecordingCourseProfessor:
    def __init__(self):
        self.calls = []

    def produce(
        self,
        *,
        context,
        decision,
        course_knowledge,
    ):
        self.calls.append(
            (context, decision, course_knowledge)
        )

        return (
            "Synthetic Professor content using "
            f"{course_knowledge.sources[0].source_locator}."
        )


def make_harness():
    engine = RecordingDecisionEngine()
    professor = RecordingCourseProfessor()

    harness = CourseGroundedTeachingHarnessV01(
        decision_engine=engine,
        professor_agent=professor,
    )

    return harness, engine, professor


def run(
    harness,
    *,
    state=None,
    pack=None,
    course_id=COURSE_ID,
    objective_id=OBJECTIVE_ID,
    expected_pack_revision=PACK_REVISION,
    student_request=None,
):
    if state is None:
        state = make_state(strong=True)

    if pack is None:
        pack = make_pack()

    if student_request is None:
        student_request = make_request()

    return harness.run_professor_turn(
        state,
        pack=pack,
        course_id=course_id,
        objective_id=objective_id,
        expected_pack_revision=expected_pack_revision,
        decision_id="decision-14b1-001",
        requested_at=NOW,
        student_request=student_request,
    )


def test_valid_course_context_reaches_professor_once():
    harness, engine, professor = make_harness()

    state = make_state(strong=True)
    before = state.model_dump(mode="json")

    result = run(
        harness,
        state=state,
    )

    assert len(engine.calls) == 1
    assert len(professor.calls) == 1

    assert result.completed_turn.agent_kind == "professor"

    assert (
        result.completed_turn.decision.decision.selected_action
        == TeachingActionV01.CONCEPTUAL_REVIEW
    )

    received_context, received_decision, knowledge = (
        professor.calls[0]
    )

    assert received_context.student_request is not None

    assert received_decision == result.completed_turn.decision

    assert knowledge == result.course_knowledge

    assert knowledge.course_id == COURSE_ID
    assert knowledge.objective_id == OBJECTIVE_ID

    assert result.pack_id == "synthetic-pack-001"
    assert result.pack_revision == PACK_REVISION

    assert result.source_refs == knowledge.objective.source_refs

    assert result.execution_status == "generated"

    assert state.model_dump(mode="json") == before


def test_restricted_source_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="not student-visible",
    ):
        run(
            harness,
            pack=make_pack(visibility="restricted"),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_unapproved_source_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="Source is not approved",
    ):
        run(
            harness,
            pack=make_pack(review_status="proposed"),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_student_state_course_scope_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="Student State course/objective scope mismatch",
    ):
        run(
            harness,
            state=make_state(
                course_id="different-course",
                strong=True,
            ),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_student_state_objective_scope_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="Student State course/objective scope mismatch",
    ):
        run(
            harness,
            state=make_state(
                objective_id="different-objective",
                strong=True,
            ),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_student_request_scope_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="Student request objective scope mismatch",
    ):
        run(
            harness,
            student_request=make_request(
                objective_id="different-objective",
            ),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_wrong_pack_revision_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="Course Pack revision mismatch",
    ):
        run(
            harness,
            expected_pack_revision="older-pack-revision",
        )

    assert engine.calls == []
    assert professor.calls == []


def test_unknown_objective_blocks_before_decision():
    harness, engine, professor = make_harness()

    with pytest.raises(
        ValueError,
        match="was not found",
    ):
        run(
            harness,
            state=make_state(
                objective_id="unknown-objective",
                strong=True,
            ),
            objective_id="unknown-objective",
            student_request=make_request(
                objective_id="unknown-objective",
            ),
        )

    assert engine.calls == []
    assert professor.calls == []


def test_assessment_action_is_not_executed_by_harness():
    harness, engine, professor = make_harness()

    state = make_state()

    with pytest.raises(
        RuntimeError,
        match="does not execute Assessment Actions",
    ):
        harness.run_professor_turn(
            state,
            pack=make_pack(),
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
            expected_pack_revision=PACK_REVISION,
            decision_id="decision-14b1-assessment",
            requested_at=NOW,
        )

    # The existing policy selects a diagnostic assessment
    # for this synthetic UNKNOWN state without a request.
    # 14B-1 must not turn that action into Professor content.
    assert len(engine.calls) == 1
    assert professor.calls == []


def test_professor_failure_is_not_reported_as_success():
    engine = RecordingDecisionEngine()

    class FailingProfessor:
        def produce(
            self,
            *,
            context,
            decision,
            course_knowledge,
        ):
            raise RuntimeError(
                "Synthetic Professor generation failed."
            )

    harness = CourseGroundedTeachingHarnessV01(
        decision_engine=engine,
        professor_agent=FailingProfessor(),
    )

    with pytest.raises(
        RuntimeError,
        match="generation failed",
    ):
        run(harness)

    assert len(engine.calls) == 1

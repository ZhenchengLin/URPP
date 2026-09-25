"""
URPP 14C-6B offline Professor Adapter tests.

All course material and Student State are synthetic.
No model provider, network, database, or student delivery.
"""

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from app.domain.learning.models import ObjectiveStateLabel

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)

from app.services.course_knowledge.structured_professor_adapter_v01 import (
    StructuredProfessorAdapterV01,
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

COURSE = "synthetic-course"
OBJECTIVE = "synthetic-objective"
SOURCE = "synthetic-source"

EXCERPT = (
    "For this synthetic course, a matrix decomposition "
    "represents a matrix using structured factors."
)


_DEFAULT_RESPONSE = object()


class RecordingGateway:

    def __init__(self, response=_DEFAULT_RESPONSE):
        self.calls = []

        self.response = (
            {
                "content": "A short synthetic explanation.",
                "source_ids": [SOURCE],
            }
            if response is _DEFAULT_RESPONSE
            else response
        )

    def generate_structured(
        self,
        *,
        prompt_name,
        payload,
    ):
        self.calls.append((prompt_name, payload))
        return self.response


def make_pack():
    source = CourseSourceV01(
        course_id=COURSE,
        source_id=SOURCE,
        source_revision="revision-1",
        source_locator="synthetic:section-1",
        content=EXCERPT,
        content_sha256=sha256(
            EXCERPT.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE,
        objective_id=OBJECTIVE,
        description="Explain a synthetic matrix decomposition.",
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE,
        pack_id="synthetic-pack",
        pack_revision="revision-1",
        objectives=(objective,),
        sources=(source,),
    )


def run(gateway, *, pack=None):
    if pack is None:
        pack = make_pack()

    state = estimate_objective_state(
        [],
        student_id="synthetic-student",
        course_id=COURSE,
        objective_id=OBJECTIVE,
        as_of=NOW,
    )

    # Synthetic routing fixture only.
    state = state.model_copy(
        update={"state": ObjectiveStateLabel.STRONG}
    )

    harness = CourseGroundedTeachingHarnessV01(
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=StructuredProfessorAdapterV01(
            gateway=gateway
        ),
    )

    return harness.run_professor_turn(
        state,
        pack=pack,
        course_id=COURSE,
        objective_id=OBJECTIVE,
        expected_pack_revision="revision-1",
        decision_id="synthetic-decision",
        requested_at=NOW,
        student_request=StudentLearningRequestV01(
            objective_id=OBJECTIVE,
            request_kind=(
                StudentLearningRequestKindV01.REQUEST_EXPLANATION
            ),
            requested_at=NOW,
        ),
    )


def test_gateway_receives_scoped_course_knowledge_once():
    gateway = RecordingGateway()

    result = run(gateway)

    assert len(gateway.calls) == 1

    prompt_name, payload = gateway.calls[0]

    assert prompt_name == (
        "urpp-course-grounded-professor-v0.1"
    )

    assert payload["objective"]["objective_id"] == OBJECTIVE

    assert payload["teaching_action"] == "conceptual_review"

    assert payload["sources"][0]["source_id"] == SOURCE

    assert payload["sources"][0]["content"] == EXCERPT

    assert "student_id" not in payload

    assert result.completed_turn.agent_kind == "professor"

    assert result.completed_turn.content == (
        "A short synthetic explanation."
    )

    assert result.execution_status == "generated"


@pytest.mark.parametrize(
    "response",
    [
        None,
        "",
        {},
        {"content": "", "source_ids": [SOURCE]},
        {"content": "Valid text", "source_ids": []},
        {"content": "Valid text", "source_ids": [SOURCE, SOURCE]},
        {"content": "Valid text", "source_ids": ["unknown-source"]},
        {"content": "Valid text", "source_ids": "synthetic-source"},
        {"content": "Valid text", "source_ids": [SOURCE], "authorized": True},
        {"content": "X" * 6001, "source_ids": [SOURCE]},
    ],
)
def test_malformed_generation_fails_closed(response):
    gateway = RecordingGateway(response=response)

    with pytest.raises((TypeError, ValueError)):
        run(gateway)

    assert len(gateway.calls) == 1


def test_unapproved_source_blocks_before_generation():
    gateway = RecordingGateway()

    pack = make_pack()

    invalid_source = pack.sources[0].model_copy(
        update={"review_status": "revoked"}
    )

    invalid_pack = pack.model_copy(
        update={"sources": (invalid_source,)}
    )

    with pytest.raises(ValueError):
        run(gateway, pack=invalid_pack)

    assert gateway.calls == []


def test_async_gateway_is_rejected():
    class AsyncGateway:

        async def generate_structured(
            self,
            *,
            prompt_name,
            payload,
        ):
            return {
                "content": "Not executed.",
                "source_ids": [SOURCE],
            }

    with pytest.raises(
        TypeError,
        match="must be synchronous",
    ):
        StructuredProfessorAdapterV01(
            gateway=AsyncGateway()
        )


def test_no_model_provider_is_required_for_offline_tests():
    gateway = RecordingGateway()

    result = run(gateway)

    assert len(gateway.calls) == 1
    assert result.completed_turn.content

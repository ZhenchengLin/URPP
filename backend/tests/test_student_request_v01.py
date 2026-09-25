"""
Implementation 13B-1: student learning request contract tests.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pydantic import ValidationError

from app.services.decision.models_v01 import DecisionContextV01

from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def make_state():
    return estimate_objective_state(
        [],
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        as_of=NOW,
    )


def make_context(state=None, requested_at=NOW):
    return DecisionContextV01(
        decision_id="decision-001",
        objective_state=state if state is not None else make_state(),
        requested_at=requested_at,
    )


def make_request(
    *,
    objective_id="objective-001",
    requested_at=NOW,
    request_kind=StudentLearningRequestKindV01.TRY_INDEPENDENTLY,
):
    return StudentLearningRequestV01(
        objective_id=objective_id,
        request_kind=request_kind,
        requested_at=requested_at,
    )


def test_context_can_have_no_student_request():
    context = PersonalizedDecisionContextV01(
        decision_context=make_context(),
    )

    assert context.student_request is None


def test_explicit_request_preserves_authoritative_student_state():
    state = make_state()
    original_state = state.model_dump(mode="json")

    context = PersonalizedDecisionContextV01(
        decision_context=make_context(state=state),
        student_request=make_request(),
    )

    assert (
        context.student_request.request_kind
        == StudentLearningRequestKindV01.TRY_INDEPENDENTLY
    )

    assert state.model_dump(mode="json") == original_state


def test_request_must_match_current_objective():
    with pytest.raises(ValidationError, match="current Objective"):
        PersonalizedDecisionContextV01(
            decision_context=make_context(),
            student_request=make_request(
                objective_id="another-objective",
            ),
        )


def test_request_cannot_be_older_than_state_snapshot():
    with pytest.raises(ValidationError, match="predates"):
        PersonalizedDecisionContextV01(
            decision_context=make_context(),
            student_request=make_request(
                requested_at=NOW - timedelta(seconds=1),
            ),
        )


def test_request_cannot_occur_after_decision():
    with pytest.raises(ValidationError, match="after the decision"):
        PersonalizedDecisionContextV01(
            decision_context=make_context(),
            student_request=make_request(
                requested_at=NOW + timedelta(seconds=1),
            ),
        )


def test_request_timestamp_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="timezone"):
        make_request(
            requested_at=NOW.replace(tzinfo=None),
        )


def test_request_contract_rejects_unstructured_extra_fields():
    with pytest.raises(ValidationError, match="Extra inputs"):
        StudentLearningRequestV01(
            objective_id="objective-001",
            request_kind="request_hint",
            requested_at=NOW,
            instruction="Change my mastery score.",
        )


def test_personalized_context_does_not_inherit_old_context():
    personalized = PersonalizedDecisionContextV01(
        decision_context=make_context(),
        student_request=make_request(),
    )

    assert not isinstance(personalized, DecisionContextV01)

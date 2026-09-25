"""
Tests for Implementation 13E-4C-2.

The Teaching Observation Context cannot approve
Mastery Evidence or infer independent performance.
"""

from dataclasses import replace

import pytest

from app.services.assessment.learning_observation_shadow_v01 import (
    LearningObservationShadowV01,
)

from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)


def observation(
    *,
    assignment_id="assignment-001",
    attempt_id="attempt-001",
    hint_count=0,
    solution_count=0,
):
    """Construct a synthetic Learning Observation."""

    event_count = hint_count + solution_count

    if solution_count:
        context = "app_solution_reported"
    elif hint_count:
        context = "app_hint_reported"
    else:
        context = "no_app_report"

    return LearningObservationShadowV01(
        assignment_id=assignment_id,
        attempt_id=attempt_id,
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        session_id="session-001",
        assessment_item_id="item-001",
        item_revision=1,
        source_assistance_event_ids=tuple(
            f"event-{attempt_id}-{index}"
            for index in range(event_count)
        ),
        reported_hint_count=hint_count,
        reported_solution_count=solution_count,
        app_assistance_context=context,
    )


def context_from(*observations):

    return TeachingObservationContextV01(
        student_id="student-001",
        course_id="course-001",
        objective_id="objective-001",
        observations=tuple(observations),
    )


def test_empty_context_does_not_claim_independence():

    context = context_from()

    assert context.observed_attempt_count == 0
    assert context.source_attempt_ids == ()
    assert context.no_app_report_attempt_count == 0


def test_one_hint_observation():

    context = context_from(
        observation(hint_count=1),
    )

    assert context.observed_attempt_count == 1
    assert context.app_hint_attempt_count == 1
    assert context.app_solution_attempt_count == 0


def test_no_app_report_is_not_mastery_evidence():

    context = context_from(
        observation(),
    )

    assert context.no_app_report_attempt_count == 1

    item = context.observations[0]

    assert item.external_help_status == "unknown"
    assert item.verified_independence is False
    assert item.mastery_eligible is False


def test_multiple_observations_preserve_separate_counts():

    first = observation(hint_count=1)

    second = observation(
        assignment_id="assignment-002",
        attempt_id="attempt-002",
    )

    third = observation(
        assignment_id="assignment-003",
        attempt_id="attempt-003",
        solution_count=1,
    )

    context = context_from(first, second, third)

    assert context.observed_attempt_count == 3
    assert context.app_hint_attempt_count == 1
    assert context.app_solution_attempt_count == 1
    assert context.no_app_report_attempt_count == 1

    assert context.source_attempt_ids == (
        "attempt-001",
        "attempt-002",
        "attempt-003",
    )


def test_mixed_help_counts_attempt_once_per_category():

    context = context_from(
        observation(
            hint_count=2,
            solution_count=1,
        ),
    )

    assert context.observed_attempt_count == 1
    assert context.app_hint_attempt_count == 1
    assert context.app_solution_attempt_count == 1
    assert context.no_app_report_attempt_count == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("student_id", "other-student"),
        ("course_id", "other-course"),
        ("objective_id", "other-objective"),
    ],
)
def test_cross_scope_observation_is_rejected(field, value):

    other = replace(
        observation(),
        **{field: value},
    )

    with pytest.raises(ValueError, match="scope mismatch"):
        context_from(other)


def test_different_session_same_objective_is_allowed():

    second = replace(
        observation(
            assignment_id="assignment-002",
            attempt_id="attempt-002",
        ),
        session_id="session-002",
    )

    context = context_from(observation(), second)

    assert context.observed_attempt_count == 2


def test_duplicate_attempt_is_rejected():

    first = observation()

    duplicate = observation(
        assignment_id="assignment-002",
        attempt_id="attempt-001",
    )

    with pytest.raises(ValueError, match="Duplicate Attempt"):
        context_from(first, duplicate)


def test_duplicate_assignment_is_rejected():

    first = observation()

    duplicate = observation(
        assignment_id="assignment-001",
        attempt_id="attempt-002",
    )

    with pytest.raises(ValueError, match="Duplicate Assignment"):
        context_from(first, duplicate)


def test_modified_mastery_claim_is_rejected():

    forged = replace(
        observation(),
        mastery_eligible=True,
    )

    with pytest.raises(ValueError, match="Mastery"):
        context_from(forged)


def test_inconsistent_assistance_counts_are_rejected():

    inconsistent = replace(
        observation(hint_count=1),
        reported_hint_count=2,
    )

    with pytest.raises(ValueError, match="event count mismatch"):
        context_from(inconsistent)


def test_non_observation_input_is_rejected():

    with pytest.raises(TypeError, match="Learning Observation"):
        context_from({"attempt_id": "attempt-001"})


def test_observations_must_be_immutable_tuple():

    with pytest.raises(TypeError, match="tuple"):
        TeachingObservationContextV01(
            student_id="student-001",
            course_id="course-001",
            objective_id="objective-001",
            observations=[observation()],
        )

"""
URPP V0.2 State Update Engine Tests.

These tests use synthetic learning evidence only.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.learning.models import (
    EvidenceType,
    ObjectiveStateLabel,
)

from app.domain.learning.state_v02 import (
    EvidenceEventV02,
    EvidenceFreshness,
    PerformanceStability,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


NOW = datetime(
    2026,
    9,
    19,
    tzinfo=timezone.utc,
)

SCOPE = {
    "student_id": "student-001",
    "course_id": "course-001",
    "objective_id": "objective-001",
    "as_of": NOW,
}


# ============================================================
# TEST FIXTURE
# ============================================================


def make_event(
    index,
    *,
    session="session-001",
    item=None,
    days=0,
    **overrides,
):
    values = {
        "evidence_id": f"evidence-{index}",
        "student_id": "student-001",
        "course_id": "course-001",
        "objective_id": "objective-001",
        "session_id": session,
        "assessment_item_id": item or f"item-{index}",
        "evidence_type": EvidenceType.PROBLEM_ATTEMPT,
        "observation": "Synthetic student response.",
        "objective_alignment": "direct",
        "assessment_validity": "valid",
        "outcome": "success",
        "correctness": 1.0,
        "assistance_level": 0,
        "prior_solution_exposure": False,
        "novelty": "novel",
        "model_confidence": 0.95,
        "scoring_policy_version": "evidence-scoring-v0.2",
        "created_at": NOW - timedelta(days=days),
    }

    values.update(overrides)

    return EvidenceEventV02(**values)


def calculate(events, **overrides):

    arguments = SCOPE | overrides

    return estimate_objective_state(
        events,
        **arguments,
    )


# ============================================================
# TEST 01 — NO EVIDENCE
# ============================================================


def test_no_evidence_is_unknown():

    result = calculate([])

    assert result.state == ObjectiveStateLabel.UNKNOWN

    assert result.performance_estimate is None


# ============================================================
# TEST 02 — SELF REPORT
# ============================================================


def test_self_report_cannot_establish_mastery():

    event = make_event(
        1,
        evidence_type=EvidenceType.STUDENT_SELF_REPORT,
    )

    result = calculate([event])

    assert result.state == ObjectiveStateLabel.UNKNOWN

    assert result.effective_evidence_mass == 0


# ============================================================
# TEST 03 — ONE SUCCESS
# ============================================================


def test_one_success_is_insufficient():

    result = calculate([
        make_event(1),
    ])

    assert result.state == ObjectiveStateLabel.UNKNOWN


# ============================================================
# TEST 04 — COMPETENT
# ============================================================


def test_two_independent_successes_can_establish_competent():

    result = calculate([
        make_event(1),
        make_event(2),
    ])

    assert result.state == ObjectiveStateLabel.COMPETENT

    assert result.independent_success_count == 2


# ============================================================
# TEST 05 — STRONG
# ============================================================


def test_independent_transfer_across_sessions_can_be_strong():

    events = [
        make_event(1, session="session-a"),
        make_event(2, session="session-a"),
        make_event(
            3,
            session="session-b",
            evidence_type=EvidenceType.TRANSFER_ATTEMPT,
        ),
    ]

    result = calculate(events)

    assert result.state == ObjectiveStateLabel.STRONG

    assert result.transfer_success_count == 1


# ============================================================
# TEST 06 — NO TRANSFER
# ============================================================


def test_three_ordinary_successes_are_not_automatically_strong():

    events = [
        make_event(1, session="session-a"),
        make_event(2, session="session-a"),
        make_event(3, session="session-b"),
    ]

    result = calculate(events)

    assert result.state == ObjectiveStateLabel.COMPETENT


# ============================================================
# TEST 07 — DELAYED RETRIEVAL
# ============================================================


def test_delayed_retrieval_is_distinct_from_immediate_recall():

    earlier = [
        make_event(1, session="session-a"),
        make_event(2, session="session-a"),
    ]

    immediate = calculate(
        earlier
        + [
            make_event(
                3,
                session="session-b",
                evidence_type=EvidenceType.RETRIEVAL_ATTEMPT,
            )
        ]
    )

    delayed = calculate(
        earlier
        + [
            make_event(
                3,
                session="session-b",
                evidence_type=EvidenceType.RETRIEVAL_ATTEMPT,
                retrieval_delay_hours=48.0,
            )
        ]
    )

    assert immediate.state == ObjectiveStateLabel.COMPETENT

    assert delayed.state == ObjectiveStateLabel.STRONG


# ============================================================
# TEST 08 — ASSISTED SUCCESS
# ============================================================


def test_assisted_successes_cannot_establish_competent():

    events = [
        make_event(
            i,
            session=f"session-{i}",
            assistance_level=2,
        )
        for i in range(1, 6)
    ]

    result = calculate(events)

    assert result.state == ObjectiveStateLabel.DEVELOPING

    assert result.independent_success_count == 0


# ============================================================
# TEST 09 — CORRELATED ATTEMPTS
# ============================================================


def test_repeated_attempts_on_same_task_count_once():

    first = make_event(
        1,
        item="same-item",
        days=1,
    )

    repeated = make_event(
        2,
        item="same-item",
        days=0,
        correctness=0.0,
        outcome="failure",
    )

    result = calculate([
        first,
        repeated,
        make_event(3, session="session-b"),
    ])

    assert result.distinct_assessment_count == 2

    assert (
        result.exclusion_reasons["evidence-2"]
        == "correlated_repeat_in_session"
    )


# ============================================================
# TEST 10 — DUPLICATE SAFETY
# ============================================================


def test_identical_duplicate_does_not_increase_evidence():

    first = make_event(1)
    second = make_event(2)

    baseline = calculate([
        first,
        second,
    ])

    duplicated = calculate([
        first,
        first,
        second,
    ])

    assert baseline.model_dump() == duplicated.model_dump()


def test_conflicting_duplicate_is_rejected():

    first = make_event(1)

    conflicting = first.model_copy(
        update={"correctness": 0.0}
    )

    with pytest.raises(
        ValueError,
        match="Conflicting duplicate",
    ):

        calculate([
            first,
            conflicting,
        ])


# ============================================================
# TEST 11 — ORDER INDEPENDENCE
# ============================================================


def test_evidence_order_does_not_change_state():

    events = [
        make_event(1, session="session-a"),
        make_event(2, session="session-a"),
        make_event(
            3,
            session="session-b",
            correctness=0.0,
            outcome="failure",
        ),
    ]

    forward = calculate(events)

    backward = calculate(
        list(reversed(events))
    )

    assert forward.model_dump() == backward.model_dump()


# ============================================================
# TEST 12 — TIME PASSING
# ============================================================


def test_time_passing_only_changes_freshness():

    events = [
        make_event(1, days=6),
        make_event(2, days=5),
    ]

    current = calculate(
        events,
        as_of=NOW,
    )

    later = calculate(
        events,
        as_of=NOW + timedelta(days=35),
    )

    assert (
        current.performance_estimate
        == later.performance_estimate
    )

    assert current.state == later.state

    assert (
        current.evidence_freshness
        == EvidenceFreshness.RECENT
    )

    assert (
        later.evidence_freshness
        == EvidenceFreshness.STALE
    )


# ============================================================
# TEST 13 — REGRESSION
# ============================================================


def test_new_failures_can_lower_student_state():

    previous = [
        make_event(1, session="session-a"),
        make_event(2, session="session-a"),
        make_event(
            3,
            session="session-b",
            evidence_type=EvidenceType.TRANSFER_ATTEMPT,
        ),
    ]

    assert (
        calculate(previous).state
        == ObjectiveStateLabel.STRONG
    )

    new_failures = [
        make_event(
            i,
            session=f"failure-session-{i}",
            correctness=0.0,
            outcome="failure",
        )
        for i in range(4, 10)
    ]

    updated = calculate(
        previous + new_failures
    )

    assert updated.state in (
        ObjectiveStateLabel.DEVELOPING,
        ObjectiveStateLabel.EMERGING,
    )

    assert (
        updated.performance_stability
        == PerformanceStability.MIXED
    )


# ============================================================
# TEST 14 — SCOPE VALIDATION
# ============================================================


def test_evidence_from_another_student_is_rejected():

    event = make_event(
        1,
        student_id="another-student",
    )

    with pytest.raises(
        ValueError,
        match="scope",
    ):

        calculate([event])


# ============================================================
# TEST 15 — FUTURE EVIDENCE
# ============================================================


def test_future_evidence_is_rejected():

    event = make_event(
        1,
        created_at=NOW + timedelta(days=1),
    )

    with pytest.raises(
        ValueError,
        match="Future",
    ):

        calculate([event])


# ============================================================
# TEST 16 — PRIOR SOLUTION EXPOSURE
# ============================================================


def test_solution_exposure_does_not_count_as_independent():

    events = [
        make_event(
            1,
            prior_solution_exposure=True,
        ),
        make_event(
            2,
            session="session-b",
            assistance_level=2,
        ),
    ]

    result = calculate(events)

    assert result.independent_success_count == 0

    assert result.state != ObjectiveStateLabel.COMPETENT

    assert result.state != ObjectiveStateLabel.STRONG


# ============================================================
# REGRESSION — CORRELATED RESPONSE GROUP
# ============================================================


def test_correlated_response_group_counts_once():

    events = [
        make_event(
            101,
            session="session-a",
            item="item-a",
            response_group_id="response-shared",
        ),
        make_event(
            102,
            session="session-a",
            item="item-b",
            response_group_id="response-shared",
        ),
        make_event(
            103,
            session="session-b",
            item="item-c",
            response_group_id="response-independent",
        ),
    ]

    result = calculate(events)

    assert result.distinct_assessment_count == 2

    assert result.independent_success_count == 2

    assert "evidence-101" in result.included_evidence_ids

    assert "evidence-102" in result.excluded_evidence_ids

    assert (
        result.exclusion_reasons["evidence-102"]
        == "correlated_response_group_in_session"
    )


def test_same_response_group_in_different_sessions_is_not_deduplicated():

    events = [
        make_event(
            104,
            session="session-a",
            item="item-a",
            response_group_id="shared-group",
        ),
        make_event(
            105,
            session="session-b",
            item="item-b",
            response_group_id="shared-group",
        ),
    ]

    result = calculate(events)

    assert result.distinct_assessment_count == 2

    assert result.independent_success_count == 2


# ============================================================
# REGRESSION — INCONSISTENT PERFORMANCE EVIDENCE
# ============================================================


def test_inconsistent_evidence_cannot_increase_student_state():
    valid_failure = make_event(
        201,
        item="item-201",
        outcome="failure",
        correctness=0.0,
    )

    contradictory = make_event(
        202,
        item="item-202",
        outcome="failure",
        correctness=1.0,
    )

    result = calculate([
        valid_failure,
        contradictory,
    ])

    assert result.state == ObjectiveStateLabel.UNKNOWN

    assert result.distinct_assessment_count == 1

    assert (
        result.exclusion_reasons["evidence-202"]
        == "inconsistent_outcome_correctness"
    )

    assert "evidence-202" not in result.included_evidence_ids

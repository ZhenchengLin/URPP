"""
URPP V0.2 — Student State Update Engine.

Input:
    EvidenceEventV02[]

Output:
    ObjectiveStateV02

The estimator is deterministic and independent of any LLM provider.

All state estimates are derived from evidence history.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import fsum
from typing import Sequence

from app.domain.learning.models import (
    EvidenceType,
    ObjectiveStateLabel,
)

from app.domain.learning.state_v02 import (
    EvidenceEventV02,
    EvidenceFreshness,
    EvidenceSupport,
    ObjectiveStateV02,
    PerformanceStability,
)

from app.services.student_model.eligibility_v02 import (
    evaluate_evidence,
)

from app.services.student_model.policy_v02 import (
    StatePolicyV02,
)


# ============================================================
# 1. DETERMINISTIC ORDERING
# ============================================================


def _time_key(
    event: EvidenceEventV02,
) -> tuple[datetime, str]:
    """
    Sort evidence chronologically.

    evidence_id breaks ties when timestamps are equal.
    """

    return (
        event.created_at.astimezone(timezone.utc),
        event.evidence_id,
    )


# ============================================================
# 2. INDEPENDENT SUCCESS
# ============================================================


def _independent_success(
    event: EvidenceEventV02,
) -> bool:
    """
    Independent success requires a correct response without
    assistance or prior exposure to the solution.

    The calling estimator must first establish evidence eligibility.
    """

    return (
        event.outcome == "success"
        and event.correctness is not None
        and event.correctness >= 1.0 - 1e-9
        and event.assistance_level == 0
        and event.prior_solution_exposure is False
    )


# ============================================================
# 3. STATE ESTIMATOR
# ============================================================


def estimate_objective_state(
    evidence_events: Sequence[EvidenceEventV02],
    *,
    student_id: str,
    course_id: str,
    objective_id: str,
    as_of: datetime,
    policy: StatePolicyV02 | None = None,
) -> ObjectiveStateV02:
    """
    Estimate one student's state on one Learning Objective.

    The function:

    1. Validates evidence identity and time.
    2. Deduplicates events.
    3. Checks evidence eligibility.
    4. Controls repeated assessments.
    5. Applies session weight caps.
    6. Estimates observed performance.
    7. Applies evidence requirements.
    8. Returns a traceable ObjectiveStateV02.

    No input evidence is modified.
    """

    policy = policy or StatePolicyV02()

    # --------------------------------------------------------
    # Validate the evaluation time
    # --------------------------------------------------------

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError(
            "as_of must be timezone-aware."
        )

    if policy.max_session_evidence_mass <= 0:
        raise ValueError(
            "max_session_evidence_mass must be positive."
        )

    # ========================================================
    # STEP 1 — VALIDATE AND DEDUPLICATE
    # ========================================================

    unique: dict[str, EvidenceEventV02] = {}

    for event in evidence_events:

        if (
            event.student_id,
            event.course_id,
            event.objective_id,
        ) != (
            student_id,
            course_id,
            objective_id,
        ):
            raise ValueError(
                f"Evidence scope mismatch: {event.evidence_id}"
            )

        if (
            event.created_at.tzinfo is None
            or event.created_at.utcoffset() is None
        ):
            raise ValueError(
                f"Naive evidence timestamp: {event.evidence_id}"
            )

        if event.created_at > as_of:
            raise ValueError(
                f"Future evidence event: {event.evidence_id}"
            )

        previous = unique.get(event.evidence_id)

        if previous is not None and previous != event:
            raise ValueError(
                "Conflicting duplicate evidence_id: "
                f"{event.evidence_id}"
            )

        unique[event.evidence_id] = event

    # ========================================================
    # STEP 2 — EVIDENCE ELIGIBILITY
    # ========================================================

    excluded: dict[str, str] = {}

    by_task: dict[
        tuple[str, str],
        list[tuple[EvidenceEventV02, float]],
    ] = defaultdict(list)

    for event in sorted(
        unique.values(),
        key=_time_key,
    ):

        decision = evaluate_evidence(
            event,
            policy,
        )

        if not decision.eligible:

            excluded[event.evidence_id] = decision.reason

            continue

        assert event.assessment_item_id is not None

        group_key = (
            event.session_id,
            event.assessment_item_id,
        )

        by_task[group_key].append(
            (
                event,
                decision.diagnostic_weight,
            )
        )

    # ========================================================
    # STEP 3 — CORRELATED EVIDENCE CONTROL
    # ========================================================

    selected: list[
        tuple[EvidenceEventV02, float]
    ] = []

    for group in by_task.values():

        group.sort(
            key=lambda item: _time_key(item[0])
        )

        # Preserve the first eligible attempt.
        selected.append(group[0])

        # Later attempts on the same task in the same
        # session cannot increase independent evidence.
        for event, _ in group[1:]:

            excluded[event.evidence_id] = (
                "correlated_repeat_in_session"
            )

    selected.sort(
        key=lambda item: _time_key(item[0])
    )

    # --------------------------------------------------------
    # Control correlated responses across assessment items.
    #
    # Different assessment_item_ids do not establish
    # independent observations when the events belong
    # to the same response group in the same session.
    # --------------------------------------------------------

    seen_response_groups: set[tuple[str, str]] = set()

    uncorrelated: list[
        tuple[EvidenceEventV02, float]
    ] = []

    for event, weight in selected:

        if event.response_group_id is not None:

            response_key = (
                event.session_id,
                event.response_group_id,
            )

            if response_key in seen_response_groups:

                excluded[event.evidence_id] = (
                    "correlated_response_group_in_session"
                )

                continue

            seen_response_groups.add(response_key)

        uncorrelated.append(
            (
                event,
                weight,
            )
        )

    selected = uncorrelated

    # ========================================================
    # STEP 4 — SESSION WEIGHT CAP
    # ========================================================

    session_total: dict[str, float] = defaultdict(float)

    for event, weight in selected:

        session_total[event.session_id] += weight

    weighted: list[
        tuple[EvidenceEventV02, float]
    ] = []

    for event, weight in selected:

        total = session_total[event.session_id]

        factor = min(
            1.0,
            policy.max_session_evidence_mass / total,
        )

        weighted.append(
            (
                event,
                weight * factor,
            )
        )

    # ========================================================
    # STEP 5 — PERFORMANCE ESTIMATE
    # ========================================================

    mass = fsum(
        weight
        for _, weight in weighted
    )

    if mass > 0:

        estimate = (
            fsum(
                weight * event.correctness
                for event, weight in weighted
            )
            / mass
        )

    else:

        estimate = None

    # ========================================================
    # STEP 6 — EVIDENCE DIVERSITY
    # ========================================================

    items = {
        event.assessment_item_id
        for event, _ in weighted
    }

    sessions = {
        event.session_id
        for event, _ in weighted
    }

    independents = [
        event
        for event, _ in weighted
        if _independent_success(event)
    ]

    independent_items = {
        event.assessment_item_id
        for event in independents
    }

    independent_sessions = {
        event.session_id
        for event in independents
    }

    # ========================================================
    # STEP 7 — TRANSFER AND RETRIEVAL
    # ========================================================

    transfer_success = [
        event
        for event, _ in weighted
        if (
            event.evidence_type
            == EvidenceType.TRANSFER_ATTEMPT
            and _independent_success(event)
            and event.novelty == "novel"
        )
    ]

    delayed_retrieval = [
        event
        for event, _ in weighted
        if (
            event.evidence_type
            == EvidenceType.RETRIEVAL_ATTEMPT
            and _independent_success(event)
            and event.retrieval_delay_hours is not None
            and (
                event.retrieval_delay_hours
                >= policy.min_retrieval_delay_hours
            )
        )
    ]

    # ========================================================
    # STEP 8 — STATE GATES
    # ========================================================

    insufficient_evidence = (
        mass == 0
        or len(items) < policy.minimum_distinct_items
        or mass < policy.minimum_evidence_mass
    )

    if insufficient_evidence:

        state = ObjectiveStateLabel.UNKNOWN

    elif estimate is not None and estimate < 0.40:

        state = ObjectiveStateLabel.EMERGING

    elif (
        estimate is not None
        and estimate < policy.competent_threshold
    ):

        state = ObjectiveStateLabel.DEVELOPING

    else:

        # ----------------------------------------------------
        # COMPETENT GATE
        # ----------------------------------------------------

        competent = (
            len(independent_items)
            >= policy.competent_independent_successes
            and any(
                event.novelty in (
                    "similar",
                    "novel",
                )
                for event in independents
            )
        )

        if not competent:

            state = ObjectiveStateLabel.DEVELOPING

        else:

            # ------------------------------------------------
            # STRONG GATE
            # ------------------------------------------------

            strong = (
                estimate is not None
                and estimate >= policy.strong_threshold
                and (
                    len(independent_items)
                    >= policy.strong_independent_successes
                )
                and (
                    len(independent_sessions)
                    >= policy.strong_minimum_sessions
                )
                and bool(
                    transfer_success
                    or delayed_retrieval
                )
            )

            if strong:

                state = ObjectiveStateLabel.STRONG

            else:

                state = ObjectiveStateLabel.COMPETENT

    # ========================================================
    # STEP 9 — EVIDENCE SUPPORT
    # ========================================================

    support_score = (
        min(mass / 3.0, 1.0)
        * min(len(items) / 3.0, 1.0)
    )

    if state == ObjectiveStateLabel.UNKNOWN:

        support = EvidenceSupport.INSUFFICIENT

    elif support_score < 0.25:

        support = EvidenceSupport.LIMITED

    elif support_score < 0.60:

        support = EvidenceSupport.MODERATE

    else:

        support = EvidenceSupport.SUBSTANTIAL

    # ========================================================
    # STEP 10 — PERFORMANCE STABILITY
    # ========================================================

    scores = [
        event.correctness
        for event, _ in weighted
    ]

    if len(scores) < 2:

        stability = (
            PerformanceStability.INSUFFICIENT_DATA
        )

    elif max(scores) - min(scores) >= 0.50:

        stability = PerformanceStability.MIXED

    else:

        stability = PerformanceStability.CONSISTENT

    # ========================================================
    # STEP 11 — EVIDENCE FRESHNESS
    # ========================================================

    last_direct = max(
        (
            event.created_at
            for event, _ in weighted
        ),
        default=None,
    )

    independent_observations = [
        event.created_at
        for event, _ in weighted
        if (
            event.assistance_level == 0
            and event.prior_solution_exposure is False
        )
    ]

    last_independent = max(
        independent_observations,
        default=None,
    )

    if last_independent is None:

        freshness = EvidenceFreshness.UNKNOWN

    elif (
        as_of - last_independent
        > timedelta(days=policy.stale_after_days)
    ):

        freshness = EvidenceFreshness.STALE

    else:

        freshness = EvidenceFreshness.RECENT

    # ========================================================
    # STEP 12 — POLICY VERSION VALIDATION
    # ========================================================

    versions = {
        event.scoring_policy_version
        for event, _ in weighted
    }

    if len(versions) > 1:

        raise ValueError(
            "Mixed scoring policy versions "
            "require explicit migration."
        )

    # ========================================================
    # STEP 13 — BUILD OBJECTIVE STATE
    # ========================================================

    return ObjectiveStateV02(

        student_id=student_id,

        course_id=course_id,

        objective_id=objective_id,

        state=state,

        performance_estimate=estimate,

        evidence_support_score=support_score,

        evidence_support=support,

        performance_stability=stability,

        evidence_freshness=freshness,

        effective_evidence_mass=mass,

        distinct_assessment_count=len(items),

        distinct_session_count=len(sessions),

        independent_success_count=len(
            independent_items
        ),

        transfer_success_count=len(
            {
                event.assessment_item_id
                for event in transfer_success
            }
        ),

        included_evidence_ids=[
            event.evidence_id
            for event, _ in weighted
        ],

        excluded_evidence_ids=sorted(excluded),

        exclusion_reasons={
            key: excluded[key]
            for key in sorted(excluded)
        },

        policy_version=policy.version,

        scoring_policy_version=next(
            iter(versions),
            "none",
        ),

        as_of=as_of,

        last_direct_assessment_at=last_direct,

        last_independent_assessment_at=last_independent,
    )

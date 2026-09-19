"""
URPP V0.2 Evidence Eligibility and Diagnostic Weight.

This module evaluates one evidence event.

Cross-event operations such as deduplication, response grouping,
session caps, and state aggregation belong to state_update.py.
"""

from dataclasses import dataclass

from app.domain.learning.state_v02 import (
    AssessmentValidity,
    EvidenceEventV02,
    ObjectiveAlignment,
)

from app.services.student_model.policy_v02 import (
    ASSISTANCE_WEIGHTS,
    EVIDENCE_TYPE_WEIGHTS,
    NOVELTY_WEIGHTS,
    StatePolicyV02,
)


@dataclass(frozen=True)
class EvidenceDecision:
    eligible: bool
    reason: str
    diagnostic_weight: float


def evaluate_evidence(
    event: EvidenceEventV02,
    policy: StatePolicyV02,
) -> EvidenceDecision:
    """
    Determine whether one event can contribute performance evidence.

    A valid event receives a diagnostic weight in [0, 1].
    """

    if event.evidence_type.value not in EVIDENCE_TYPE_WEIGHTS:
        return EvidenceDecision(
            eligible=False,
            reason="not_performance_evidence",
            diagnostic_weight=0.0,
        )

    if event.objective_alignment != ObjectiveAlignment.DIRECT:
        return EvidenceDecision(
            eligible=False,
            reason="objective_not_directly_aligned",
            diagnostic_weight=0.0,
        )

    if event.assessment_validity != AssessmentValidity.VALID:
        return EvidenceDecision(
            eligible=False,
            reason="assessment_not_valid",
            diagnostic_weight=0.0,
        )

    # Outcome and numeric correctness must agree.
    #
    # Reject contradictory performance records rather than
    # silently treating a labeled failure as a successful answer.
    #
    # This rule applies to performance evidence after validity
    # and objective-alignment checks.
    correctness = event.correctness

    inconsistent = (
        (event.outcome == "success" and correctness != 1.0)
        or (event.outcome == "failure" and correctness != 0.0)
        or (
            event.outcome == "partial"
            and correctness is not None
            and not (0.0 < correctness < 1.0)
        )
        or (event.outcome == "neutral" and correctness is not None)
    )

    if inconsistent:
        return EvidenceDecision(
            eligible=False,
            reason="inconsistent_outcome_correctness",
            diagnostic_weight=0.0,
        )

    if event.outcome == "neutral" or correctness is None:
        return EvidenceDecision(
            eligible=False,
            reason="performance_not_observable",
            diagnostic_weight=0.0,
        )

    if event.assistance_level is None:
        return EvidenceDecision(
            eligible=False,
            reason="assistance_level_unknown",
            diagnostic_weight=0.0,
        )

    if not event.assessment_item_id:
        return EvidenceDecision(
            eligible=False,
            reason="assessment_identity_missing",
            diagnostic_weight=0.0,
        )

    if event.model_confidence < policy.min_model_confidence:
        return EvidenceDecision(
            eligible=False,
            reason="interpretation_confidence_too_low",
            diagnostic_weight=0.0,
        )

    assistance_weight = ASSISTANCE_WEIGHTS[
        event.assistance_level
    ]

    novelty_weight = NOVELTY_WEIGHTS[event.novelty]

    # Seeing a solution prevents treating a repeated task as novel.
    if event.prior_solution_exposure is True:
        novelty_weight = min(
            novelty_weight,
            NOVELTY_WEIGHTS["repeated"],
        )

    type_weight = EVIDENCE_TYPE_WEIGHTS[
        event.evidence_type.value
    ]

    weight = (
        assistance_weight
        * novelty_weight
        * type_weight
        * event.model_confidence
    )

    weight = max(0.0, min(weight, 1.0))

    if weight == 0.0:
        return EvidenceDecision(
            eligible=False,
            reason="zero_diagnostic_weight",
            diagnostic_weight=0.0,
        )

    return EvidenceDecision(
        eligible=True,
        reason="eligible_performance_evidence",
        diagnostic_weight=weight,
    )

"""
URPP V0.2 State Policy.

All parameters are provisional engineering heuristics.
They are not calibrated probabilities of student mastery.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StatePolicyV02:
    version: str = "state-policy-v0.2"

    min_model_confidence: float = 0.65

    minimum_evidence_mass: float = 0.75

    minimum_distinct_items: int = 2

    competent_threshold: float = 0.75

    strong_threshold: float = 0.90

    competent_independent_successes: int = 2

    strong_independent_successes: int = 3

    strong_minimum_sessions: int = 2

    max_session_evidence_mass: float = 1.5

    stale_after_days: int = 21


ASSISTANCE_WEIGHTS = (
    1.00,
    0.80,
    0.60,
    0.45,
    0.30,
    0.15,
    0.00,
)


NOVELTY_WEIGHTS = {
    "novel": 1.00,
    "similar": 0.75,
    "repeated": 0.35,
    "unknown": 0.50,
}


EVIDENCE_TYPE_WEIGHTS = {
    "problem_attempt": 1.00,
    "self_explanation": 0.90,
    "definition_recall": 0.80,
    "transfer_attempt": 1.00,
    "retrieval_attempt": 1.00,
    "error_correction": 0.65,
}

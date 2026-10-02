# URPP — Evidence-driven Decision Policy V0.1

Status: Implementation 13E-1.
Roadmap: Week 4 — Adaptive Teaching.

## Purpose

Choose a next teaching action using an existing authoritative
Objective State when the student has not made an explicit
learning-activity request.

This is a deterministic, opt-in decision component.

It does not replace the existing Personalized Decision
Engine or Orchestrator in this implementation stage.

## Inputs and evidence boundary

The new engine accepts PersonalizedDecisionContextV01.

It reads the existing ObjectiveStateV02 snapshot through
DecisionContextV01.

It does not construct a Student State from Agent output
or infer correctness from conversation text.

It uses the state label, included evidence count,
distinct assessment count, and independent success count.

Excluded evidence is not promoted into included evidence.

A state label is not a permanent student trait or a
scientifically calibrated mastery probability.

## Automatic selection rules

When no explicit student request exists:

- UNKNOWN with no included distinct assessment evidence:
  DIAGNOSTIC_ASSESSMENT.
- UNKNOWN with included distinct assessment evidence:
  INDEPENDENT_PRACTICE.
- EMERGING / DEVELOPING without included distinct
  assessment evidence: CONCEPTUAL_REVIEW.
- EMERGING / DEVELOPING with included evidence but no
  independent success: CONCEPTUAL_HINT.
- EMERGING / DEVELOPING with an independent success:
  INDEPENDENT_PRACTICE.
- COMPETENT with no recorded independent success:
  SELF_EXPLANATION.
- COMPETENT with an independent success:
  INDEPENDENT_PRACTICE.
- STRONG with no recorded independent success:
  INDEPENDENT_PRACTICE.
- STRONG with an independent success:
  SELF_EXPLANATION.

These are provisional engineering heuristics.
They are not empirically validated optimal teaching rules.

The selected action must belong to the current
PedagogicalPolicyV01 allowed-action set.

## Transfer Delivery boundary

TRANSFER_ASSESSMENT is excluded from automatic selection
and the returned automatic allowed-action set.

This reflects the current fail-closed Transfer Delivery
Gate, not an inference that the student cannot transfer
knowledge.

An explicit student request still uses the existing
PersonalizedDecisionEngineV01 selection behavior.

An explicit Transfer request may be selected, but actual
delivery remains subject to the existing independent
eligibility and trusted-review checks.

This module does not open the Transfer Delivery Gate.

## Provenance

Automatic selections use the new
DecisionSelectionSourceV01.EVIDENCE_DRIVEN value.

The result records the state label and the specific
evidence-summary counts consulted.

The version identifiers distinguish this policy
from the original rule-based baseline.

A selection reason describes the applied heuristic;
it does not claim an action was executed or that
new student evidence was generated.

## Non-goals

No change to the Student State estimator.
No modification of existing assessment evidence.
No database schema or persistence changes.
No Transfer Review changes.
No real LLM integration.
No production authentication.
No Orchestrator replacement in this stage.
No end-to-end Adaptive Learning Loop yet.

## Next implementation

13E-2 should connect this engine to the existing
Personalized Orchestrator through a narrowly scoped,
opt-in integration.

Verify recovery, student-request priority, database
persistence, blocked Transfer Delivery, and action
provenance using existing integration tests.

The full Adaptive Learning Loop requires a subsequent
end-to-end test that demonstrates real assessment
evidence updating Student State before the next decision.

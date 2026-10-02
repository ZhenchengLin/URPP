# URPP — Evidence-driven Turn Wiring V0.1

Status: Implementation 13E-2A.
Roadmap: Week 4, Adaptive Teaching.

## Purpose

Enable explicit opt-in use of the existing
EvidenceDrivenDecisionEngineV01 through the existing
PersonalizedTeachingTurnOrchestratorV01.

Do not replace the legacy default decision engine.

## Shared decision interface

The Personalized Orchestrator now accepts a decision
engine through PersonalizedDecisionPortV01.

The original PersonalizedDecisionEngineV01 and the
new EvidenceDrivenDecisionEngineV01 implement the
same decision interface.

The orchestrator still makes one decision and routes
to exactly one Agent when the action is executable.

## Opt-in composition

create_evidence_driven_personalized_turn_v01()
constructs an orchestrator using the evidence-driven
engine and the supplied teaching Agent implementations.

When no explicit student request exists, the new
engine chooses an action from the current state
summary and allowed action set.

When an explicit request exists, the existing
student-request priority is preserved.

This composition does not acquire an Objective State,
authenticate a student, or persist records.

## Transfer protection

The opt-in composition adds a guard before the
Assessment Agent is called.

TRANSFER_ASSESSMENT continues to fail closed because
trusted approval-backed delivery is not enabled.

The existing Recoverable Numeric Session retains
its independent Transfer Delivery Gate.

This extra guard applies to orchestrators constructed
through the new opt-in factory. It does not claim to
change every existing orchestrator in the codebase.

## Numeric Session Adapter

The existing PersonalizedNumericSessionTurnAdapterV01
can consume the opt-in orchestrator without modifying
the existing Assignment persistence implementation.

The adapter requires an assessment action when used
for numeric delivery.

A professor-oriented action such as CONCEPTUAL_HINT
must use the teaching orchestrator directly instead
of being misrepresented as a Numeric Assignment.

The adapter does not persist personalized decision
selection provenance in the legacy Assignment schema.

## Evidence boundary

These tests verify actual orchestrator and adapter
routing, including the real empty-evidence state.

Tests for other state labels use explicitly synthetic
snapshots solely to verify routing.

They do not demonstrate that submitted student answers
produced those states.

## Next implementation

13E-2B must use the existing SQLite test stack to:

1. Deliver an eligible numeric diagnostic.
2. Submit a response through the existing assignment
   and evidence pipeline.
3. Recover the same student's updated Objective State.
4. Run another automatic decision from that recovered state.
5. Verify the selected action and selection reason.

Do not treat Agent-generated text as assessment evidence.

Do not bypass Assessment Item eligibility checks.

Keep Transfer Delivery disabled.

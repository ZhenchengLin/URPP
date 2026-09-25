# URPP — Personalized Numeric Session Adapter V0.1

Status: Implementation 13C-2A.

## Purpose

Connect the Personalized Teaching Turn to the existing
Recoverable Numeric Session without duplicating its
Assessment Item, Assignment, or Student State logic.

## Integration

The existing RecoverableNumericSessionServiceV01 calls
a turn orchestrator with:

run_turn(objective_state, decision_id, requested_at)

PersonalizedNumericSessionTurnAdapterV01 provides this
interface and delegates to the personalized orchestrator
with a bound StudentLearningRequestV01.

The personalized result is converted into the legacy
TeachingTurnResultV01 contract.

Only one teaching decision is performed.

The existing Recoverable Numeric Session remains responsible
for validating the stored Assessment Item and creating the
persisted Assignment.

## Supported requests

Numeric Assessment delivery only accepts requests whose
selected actions belong to ASSESSMENT_ACTIONS.

Professor-oriented requests, such as explanation and hints,
must use a non-Assignment teaching path.

An explicit request is bound to one adapter instance and
cannot be used for multiple teaching decisions.

For a new request, construct a new adapter and Recoverable
Session service using the same persistent repositories and
the same Session identity.

A request timestamp must equal the Numeric Assessment
decision timestamp in this V0.1 integration.

## Important boundaries

A selected assessment action does not guarantee that a
suitable Assessment Item exists.

The existing Recoverable Numeric Session must still verify
the item's revision, scope, and alignment before issuing
an Assignment.

The Agent's generated free text must not replace the stored
numeric assessment prompt.

Student requests are not evidence of mastery.

The adapter does not persist the original request or the
personalized decision provenance in the Assignment schema.

The returned legacy TeachingTurnResultV01 intentionally
contains only the existing decision and teaching-content
fields.

The adapter does not authenticate the student or establish
that the request came from an authorized student.

## Verification status

13C-2A verifies the compatibility adapter and decision
routing using recording Agent test doubles.

It does not by itself verify a persisted personalized
Assignment, answer submission, or process restart.

13C-2B must exercise the complete workflow using isolated
SQLite databases and the existing Recoverable Session
repositories. The tests must also confirm that mismatched
Assessment Items and pending Assignments remain rejected.

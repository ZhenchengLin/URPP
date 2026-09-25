# URPP — Evidence Provenance Adaptive Loop V0.1

Status: Implementation 13E-2B.
Roadmap: Week 4 — Adaptive Teaching.

## Verified existing behavior

The current Numeric Assignment Repository stores
assistance_level=None and prior_solution_exposure=None
because the response-submission interface has no
verified source for either field.

The numeric scoring service preserves those unknowns.

The Student State eligibility rules exclude an attempt
whose assistance level is unknown.

A correct answer alone therefore does not establish
independent success or justify increasing mastery.

This implementation does not weaken those rules.

## New automatic workflow rule

When an Objective remains UNKNOWN, has no included
assessment evidence, and every currently excluded
evidence record is excluded for the specific reason
assistance_level_unknown, the automatic decision
engine may select CONCEPTUAL_REVIEW.

This is a provisional workflow heuristic for avoiding
an immediate repetition of an assessment whose evidence
provenance could not be established.

It is NOT a conclusion that the student is weak,
requires remediation, or has demonstrated mastery.

Other exclusion reasons do not activate this rule.

Explicit student requests continue to take priority.

## Actual SQLite integration

The integration test:

1. Creates an isolated file-backed SQLite database.
2. Starts a real Recoverable Numeric Session.
3. Automatically selects and issues an eligible
   DIAGNOSTIC_ASSESSMENT.
4. Submits a numeric student response through the
   existing persistent Assignment and Attempt pipeline.
5. Reopens SQLite using new Engine and Repository
   instances.
6. Recovers the same student's Objective State.
7. Verifies that the submitted attempt is excluded
   specifically because assistance_level_unknown.
8. Runs the next automatic personalized teaching turn
   from the recovered state.
9. Verifies that the next action is CONCEPTUAL_REVIEW
   through the Professor Agent.
10. Verifies that no new Assignment or mastery evidence
    was fabricated.

## What this test does and does not prove

The test demonstrates that an actual persisted student
response can change the next automatic teaching action,
even when the response is ineligible for mastery
estimation.

It does NOT demonstrate that an eligible assessment
raised mastery or that the student's independent
performance has been verified.

The included-evidence count remains zero.
The Student State remains UNKNOWN.

An Agent's generated teaching content is not evidence
of student mastery.

## Future accepted-evidence integration

To complete the accepted-evidence learning loop,
the application needs a trustworthy way to record
assistance and prior-solution-exposure provenance
for an Assessment Attempt.

Such information must have an explicit source and
appropriate verification policy.

Do not infer assistance_level=0 from a correct answer,
from a student's request to work independently, or
from Agent-generated text.

A future implementation should add a documented
provenance-capture contract and demonstrate that
a genuinely eligible Assessment Event can update
Student State before the next automatic decision.

## Existing safeguards

No change to Assessment Item eligibility.
No change to the State Estimator.
No change to scoring.
No change to existing Assignment persistence.
No automatic Transfer Assessment delivery.
No production authentication claims.

# URPP — Numeric Provenance Review Candidate V0.1

Status: Implementation 13E-4B.
Roadmap: Week 4 — Adaptive Teaching.

## Purpose

Create a source-bound review input from the existing
persisted Numeric Attempt Provenance Snapshot.

This is not an authorized review or approval.

## Binding

The candidate records Assignment and Attempt identity,
the student/session scope, and reported Hint/Solution counts.

A deterministic SHA-256 fingerprint includes the V0.1
snapshot's Assignment, Attempt, response, assistance
metadata, and reported Assistance Event records.

The candidate does not expose the raw answer as a field.

The underlying fingerprint includes the raw answer.
For short or guessable answers, a plain SHA-256 digest
is not a privacy or anonymity guarantee.

## Recheck

Before a future review uses a candidate, the service
can rebuild the current snapshot and compare it with
the candidate's original fingerprint and summary.

A mismatch is rejected.

This detects changes to the stored source record
between candidate creation and rechecking.

It is not a transactional lock. A concurrent write
after rechecking is outside this mechanism's guarantee.

## Security boundary

SHA-256 is not an authenticated signature.

An attacker able to replace both database records
and candidate fingerprints could defeat this check.

The service does not authenticate a reviewer, protect
a signing key, or authorize a review decision.

The existing Snapshot Service also does not provide
a single cross-service transactional source read.

These guarantees require separate design and tests
before accepting Numeric Provenance Review decisions.

## Evidence boundary

The candidate always remains:

- pending_authorized_review;
- external_assistance_status=unknown;
- verified_independence=False;
- accepted_as_mastery_evidence=False.

Reported assistance is not proof of student attention.

An empty assistance log is not proof that the student
received no external help.

No Attempt fields or Evidence Eligibility rules change.

No Student State or Decision Engine changes occur.

## SQLite verification

Tests use completed Numeric Assignments and stored Attempts.

They verify assistance counts, empty-log behavior,
rejection of altered candidates, rejection after a
privileged change to a source record, and recovery
after reopening the SQLite database.

## Next stage

13E-4C must define an authorization boundary and a
review policy for genuinely known assistance conditions.

A candidate alone must never be converted into a
verified-independent Attempt or accepted mastery evidence.

Implementation 14 and the subsequent Architecture Review
should also revisit whether the provenance workflow has
become more complex than the intended local-first product
requires.

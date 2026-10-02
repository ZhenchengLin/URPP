# URPP — Assessment Assistance Event Log V0.1

Status: Implementation 13E-3A.
Roadmap: Week 4 — Adaptive Teaching.

## Purpose

Persist assistance events reported by an application
while a Numeric Assessment Assignment is pending.

This establishes a storage contract for future
application-controlled assistance provenance.

It does not yet prove that a student received help.

## Recorded information

Each event records:

- A generated event ID.
- The exact Numeric Assignment ID.
- The stored Assignment's student/session scope.
- The reported kind: HINT or SOLUTION.
- A SHA-256 fingerprint of the reported content.
- A timestamp from the configured application clock.
- source=application_reported.

The assistance content is not stored in plaintext.

The current source field explicitly distinguishes
these records from independently verified provenance.

## Write restrictions

The Repository checks that:

- The Numeric Assignment exists.
- Its student/session scope matches the supplied scope.
- The Assignment is pending.
- Its completion attempt has not been recorded.
- The event time does not precede the Assignment time.
- The reported assistance kind is supported.
- The content is nonempty.

New records are inserted without exposing an update
or delete method through this Repository interface.

These checks do not authenticate the caller.

## Important trust limitation

An arbitrary internal caller can currently invoke
record_application_assistance() with invented content.

The Repository cannot verify that a user interface
displayed the content or that the student saw it.

A future application layer must control the actual
presentation operation and the corresponding log write.

The current log must not be treated as proof of student
independence or as an authoritative assistance_level.

## Relationship to Attempt and Student State

StudentAttemptV02 remains unchanged.

The existing Numeric Assignment submission continues
to record assistance_level=None and
prior_solution_exposure=None.

This event log does not automatically change those
fields or produce eligible performance evidence.

A correct answer, an empty assistance log, or an
application-reported event does not prove the absence
of external help.

The existing Evidence Eligibility policy remains
unchanged and continues to fail closed when assistance
provenance is unknown.

## SQLite tests

Tests use isolated file-backed SQLite databases and
the existing Recoverable Numeric Session flow.

They verify explicit logging, cross-connection recovery,
Assignment scope, rejection after submission, and
continued exclusion of unverified mastery evidence.

Existing databases require schema management before
this new table can be used; tests create it through
SQLAlchemy metadata in fresh temporary databases.

The current write checks are not a production-grade
concurrency or authorization guarantee.

## Next stage

13E-3B should integrate assistance logging with the
application's controlled content-presentation pathway.

Before deriving an Attempt's assistance_level, define
a reviewed mapping from observed assistance events
to assistance categories and a policy for unobservable
external assistance.

Do not infer independent success merely because
the assistance log is empty.

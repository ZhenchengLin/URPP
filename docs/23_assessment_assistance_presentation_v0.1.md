# URPP — Assessment Assistance Presentation V0.1

Status: Implementation 13E-3B.
Roadmap: Week 4 — Adaptive Teaching.

## Purpose

Connect the existing Assignment-scoped Assistance
Event Log to an application-controlled synchronous
content-presentation operation.

This stage introduces an integration contract.
It does not implement a production browser presenter.

## Presentation sequence

1. Validate the requested Assignment, student,
   session, assistance kind, and content.
2. Confirm that the Assignment is pending.
3. Invoke the application-supplied Presenter exactly
   once for this service call.
4. Continue only when the Presenter returns
   the boolean value True.
5. Persist an application-reported assistance event
   using the existing Assistance Log Repository.
6. Return the stored event to the caller.

A failed Presenter does not authorize a new log entry.

The Assistance Log Repository independently rechecks
Assignment scope and pending status before persistence.

## Trust boundary

The Presenter is supplied by an internal application
integration and is currently exercised with test doubles.

A successful callback is an application report, not
independent proof that the student saw the content.

The service does not authenticate student identity,
verify a browser render, or detect external assistance.

The existing log source remains application_reported.

No trusted assistance_level is derived at this stage.

## Partial-operation failure

Content presentation and SQLite persistence cannot
be enclosed in one database transaction.

If a Presenter reports success but the subsequent
log write fails, the service raises
AssistancePresentationUnloggedV01.

The application must treat this outcome as potentially
provided assistance without a durable event.

It must not silently claim the operation succeeded,
and it must not automatically replay the presentation.

An Assignment can also complete between the initial
pending check and the final log write. The repository
recheck rejects the late event, and the service
reports the partial operation explicitly.

This stage does not provide exactly-once delivery,
a durable outbox, or a production concurrency guarantee.

## Student State safeguards

No change to StudentAttemptV02.
No change to Numeric Assignment submission.
No change to scoring or Evidence Eligibility.
No change to the State Estimator.
No change to the Evidence-driven Decision Engine.
No change to Transfer Delivery.

The absence of recorded Hint or Solution events
does not prove that the student worked independently.

Application-reported assistance events do not
automatically create eligible mastery evidence.

## SQLite integration tests

The tests exercise:

- Successful Presenter callback followed by logging.
- Presenter rejection and exception.
- Assignment student/session scope validation.
- Rejection of completed Assignments before presentation.
- Rejection of invalid input before presentation.
- A successful presentation followed by a database
  rejection because the Assignment completed meanwhile.
- Cross-connection persistence recovery without
  fabricated mastery evidence.

Test Presenter callbacks are doubles and do not
represent a production user interface.

## Next stage

13E-3C should connect the presentation interface
to an actual application-owned interaction pathway,
with a reviewed policy for presentation acknowledgment,
retries, and incomplete records.

Only after a reliable provenance contract exists
should Attempt assistance metadata be derived from
recorded activity.

Never infer independence merely from an empty log.

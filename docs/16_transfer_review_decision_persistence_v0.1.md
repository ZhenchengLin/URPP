# URPP — Transfer Review Decision Persistence V0.1

Status: Implementation 13D-1C3.

## Purpose

Persist review-decision records for specific Transfer
Design Review drafts and Assessment Item revisions.

This stage does not enable Transfer Assessment delivery.

## Decision contract

TransferReviewDecisionV01 records:

- A unique Review Decision ID.
- Assessment Item ID and Revision.
- Course and Objective identity.
- Assessment Item content fingerprint.
- Transfer Design Review Draft fingerprint.
- Reviewer ID and identity issuer as recorded claims.
- An approve or reject outcome.
- Nonempty review rationale.
- A timezone-aware decision timestamp.

A decision records what the supplied data claims.
It does not independently authenticate its reviewer.

## Persistence

TransferReviewDecisionRepositoryV01 uses the existing
SQLAlchemy Base and session-factory conventions.

Each decision row references an existing Assessment
Item ID and Revision using a composite foreign key.

The Repository verifies that the referenced numeric
item exists and that its saved Course, Objective,
and full content fingerprint match the decision.

Decision IDs are unique.

The Repository exposes save, load, and history-list
operations. It does not expose update or delete methods.

This append-only property applies to this Repository
interface. It does not prevent a privileged database
administrator or code with direct database write access
from modifying database rows.

The Repository does not establish reviewer authorization.

## Trusted approval boundary

An outcome of approve is not an authoritative Approval.

This prototype accepts reviewer identifiers supplied
by application code, which could be forged.

The Repository deliberately has no is_approved method
and does not return an authorization token.

The existing Transfer Delivery Gate remains unchanged
and continues to reject TRANSFER_ASSESSMENT.

A future trusted application service must authenticate
the reviewer, enforce the relevant review permission,
control the write entry point, and establish authoritative
decision provenance before any recorded approval can
authorize delivery.

## Historical decisions

Multiple decisions may be recorded for the same item
revision using different Decision IDs.

The Repository returns historical records without
selecting a winner or inferring a current approval.

A future approval policy must define revocation,
supersession, current validity, and concurrent-review
semantics before delivery can rely on this history.

## Database limitations

This stage introduces a new table registered with
the existing SQLAlchemy metadata.

The tests create isolated temporary SQLite databases.

No production migration is included.

An existing database requires an explicit schema
management plan before using the new table.

A successful SQLite test does not establish
PostgreSQL compatibility or production concurrency
guarantees.

## Evidence limitations

Design-review decisions and student-performance
evidence are separate.

A recorded approve outcome does not demonstrate
student knowledge transfer or Independent Mastery.

The Student State estimator remains unchanged.

## Next stage

13D-1C4 must introduce a trusted approval-writing
application service and authoritative reviewer
authentication/authorization integration.

Only after the approval source, current-validity policy,
and delivery-path integration are tested may the
Transfer Delivery Gate be opened for verified items.

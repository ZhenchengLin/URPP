# URPP — Transfer Delivery Fail-Closed Gate V0.1

Status: Implementation 13D-1C1.

## Purpose

Prevent the existing Recoverable Numeric Session from
issuing a Transfer Assessment before URPP has a trusted
Transfer Design Approval source.

## Existing constraints

13D-1A requires a TRANSFER_ASSESSMENT action to use an
Assessment Item tagged TRANSFER_ATTEMPT.

13D-1B introduced a content-bound Transfer Design
Review Draft.

Neither the transfer tag nor the draft constitutes
trusted approval.

## Current delivery behavior

The Recoverable Numeric Session now applies:

1. Existing Assessment Item scope and alignment checks.
2. Existing Assessment Action–Item compatibility check.
3. Fail-closed Transfer Delivery Gate.
4. Existing Assignment persistence.

The gate permits ordinary assessment actions to continue.

The gate rejects TRANSFER_ASSESSMENT unconditionally
because this application currently has no trusted
Transfer Design Approval source.

There is no caller-supplied approved=True override.

## Why approval is not yet implemented

AssessmentRecordRepositoryV02 explicitly delegates
authentication and reviewer authorization to a future
trusted application-service layer.

Creating a database row containing approved=True
would not independently establish reviewer authority.

Before enabling reviewed Transfer Assessment delivery,
URPP must define an authorized review workflow,
persist immutable review decisions, and verify their
binding to the current Assessment Item revision/content.

The draft's SHA-256 fingerprint is for change detection.
It is not reviewer authentication or a digital signature.

## Scope and limitations

The fail-closed check is connected to
RecoverableNumericSessionServiceV01.

This stage does not claim that every possible legacy
assessment delivery path in URPP uses this gate.

The existing Recoverable Session calls its teaching
Agent before evaluating this gate. The new check prevents
the incompatible Assignment from being persisted,
but does not guarantee that no Agent was called.

No database schema changes are made.

No approval records are written.

No transfer-success or independence evidence is
inferred from action selection, student requests,
or numeric correctness.

## Next steps

Introduce a trusted reviewer identity and authorization
boundary, then an immutable approval record tied to
Assessment Item ID, Revision, and content fingerprint.

After that, replace the unconditional rejection with
an authoritative approval lookup and validity check.

Audit any remaining legacy Assignment delivery paths
before claiming system-wide enforcement.

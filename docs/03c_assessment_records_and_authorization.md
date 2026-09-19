# Design 01C — Assessment Records and Authorization

Status: V0.2 implementation design
Branch: design/evidence-extraction-scoring

## 1. Purpose

Define the trust boundary between untrusted client input,
authoritative assessment records, reviewer approval, and
student-state estimation.

The existing assessment pipeline is an internal prototype.
It is not yet an authenticated or persistent service.

## 2. Technical direction

Production database: PostgreSQL.
Database access: SQLAlchemy.
Schema migrations: Alembic.
PostgreSQL driver: psycopg.
Local repository tests may use SQLite.

The database technology does not itself authenticate users.

SQLAlchemy, Alembic, and psycopg must be declared in the backend
dependency configuration before database implementation.

## 3. Authoritative assessment items

The server stores each assessment item and rubric version.

A student submission references an existing assessment_item_id.
The server retrieves the corresponding item and rubric.

The client cannot establish objective alignment by submitting
alignment_verified=True.

An assessment item used for a completed attempt must retain
its original rubric version. Later edits create a new version
rather than silently changing the historical scoring basis.

## 4. Student attempts

An attempt is bound to an authenticated student's identity.

The backend derives student_id from verified authentication
context, not from an unrestricted client-supplied field.

The server assigns or validates attempt_id, session_id,
assessment_item_id, response_group_id, and submission time.

The submitted answer is preserved as an original record.
Scoring and review results are stored separately.

## 5. Reviewer authentication and authorization

Authentication establishes the reviewer's identity through
a trusted identity provider or authentication service.

Authorization checks whether that authenticated reviewer has
permission to review the relevant course and assessment.

A client-provided reviewer_id or role is not proof of authority.

The signing key remains in server-controlled configuration.
It is never sent to the browser or accepted from a student request.

The approval-signing function is callable only after the
backend has performed the relevant authorization checks.

## 6. Review and approval records

A review references a stored assessment item, rubric version,
and student attempt.

An approval references the exact review and its source records.

The backend validates signed approvals before finalization.

Approval creation, verification, rejection, and revocation
must be auditable.

A signature validates record integrity; it does not establish
that the reviewer's mathematical judgment is correct.

## 7. State-estimation entry point

An authenticated application service retrieves eligible
assessment records and approved evidence from trusted storage.

Public API requests must not directly submit arbitrary
EvidenceEventV02 objects to update student state.

ObjectiveStateV02 is derived from evidence history.
The evidence history remains the source of truth.

Numeric and open-response evidence currently use different
scoring_policy_version values. Mixed-version aggregation
requires an explicit compatibility policy before deployment.

## 8. Implementation order

1. Declare database dependencies and create schema migrations.
2. Implement versioned assessment-item and attempt repositories.
3. Add authenticated student identity and reviewer permissions.
4. Restrict approval issuance to authorized backend workflows.
5. Connect authoritative records to the assessment pipeline.
6. Add audit, revocation, and integration tests.
7. Only then expose assessment and review HTTP endpoints.

## 9. Current non-goals

This document does not implement authentication.
It does not deploy a database.
It does not make the current internal pipeline production-ready.
It does not treat an LLM-generated review as independently verified.

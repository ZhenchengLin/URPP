# URPP — Personalized Numeric SQLite Integration V0.1

Status: Implementation 13C-2B.

## Purpose

Verify that a structured Student Learning Request can influence
a Numeric Assessment action while all existing Recoverable
Session and Assignment persistence constraints remain active.

## Test environment

- Isolated, temporary, file-backed SQLite databases.
- SQLite foreign-key enforcement enabled on connections.
- Existing Assessment, Assignment, and Session repositories.
- Existing RecoverableNumericSessionServiceV01.
- PersonalizedNumericSessionTurnAdapterV01.
- Recording Agent doubles, not real LLM Agents.

Tests must not use a real URPP database or student records.

## Verified workflow

Student request
→ personalized teaching decision
→ existing Assessment Item validation
→ persisted Assignment
→ stored numeric prompt delivery
→ persisted student response
→ reconstructed Objective State
→ reopened SQLite connection and fresh service instance
→ recovered Session progress.

## Required negative cases

- A pending Assignment must not be replaced.
- An Assessment Item from a different Objective is rejected.
- An item without verified alignment is rejected.
- An already-used Decision ID cannot be issued again
  within the same Session.
- A request for explanation cannot be represented as a
  Numeric Assignment.

## Evidence boundaries

A student requesting independent practice does not,
by itself, establish verified independent performance.

A student requesting a transfer assessment does not
establish successful knowledge transfer.

The existing internal submission flow currently leaves
independent-performance provenance unknown. Integration
tests must preserve that limitation rather than fabricating
Independent Mastery from a correct numeric answer.

## Limitations

These tests reopen a SQLite database using new SQLAlchemy
Engine, Repository, and Session service instances. They do
not execute a separate operating-system process or test
production concurrency.

The personalized Adapter does not persist the original
student request or complete personalized decision provenance.

An Assessment Agent's free text cannot replace the stored
numeric Assessment Item prompt.

A TRANSFER_ASSESSMENT action label alone does not verify
that an item measures genuine transfer. A future assessment
policy must check the item's documented transfer properties.

No real LLM, student authentication, HTTP endpoint,
production database migration, or deployment is included.

## Verification commands

Targeted:

PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/test_personalized_numeric_session_sqlite_v01.py \
  backend/tests/test_personalized_numeric_session_adapter_v01.py \
  backend/tests/test_recoverable_numeric_session_v01.py

Full backend regression:

PYTHONPATH=backend python3 -m pytest -q backend/tests

The actual test results and commit hash must be recorded
from the execution log, not predicted in this document.

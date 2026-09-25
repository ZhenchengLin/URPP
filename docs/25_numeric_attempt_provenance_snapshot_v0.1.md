# URPP — Numeric Attempt Provenance Snapshot V0.1

Status: Implementation 13E-4A.

## Purpose

Create a read-only review input from an actual completed
Numeric Assignment, its persisted Student Attempt, and its
assignment-scoped application-reported Assistance Events.

The snapshot is not an approved assessment record.

## Why not reuse Open-response Review Approval?

The existing signed Review Approval mechanism binds an
Open-response Assessment Item, Attempt, structured scoring
review, reviewer identity, and approval timestamp.

Its approval concerns that open-response scoring review.
It does not independently verify the assistance conditions
of a Numeric Attempt.

Its signing function also requires an upstream service to
have authenticated and authorized the reviewer.

A signing key or a reviewer ID supplied by a test does not
constitute real identity verification.

Numeric Attempt provenance therefore needs a separate,
explicitly designed review and authorization contract.

## Snapshot contents

The service loads an actual completed Assignment and its
recorded Attempt, validates their scope and identity,
then retrieves the associated Assistance Events.

The snapshot includes the persisted answer and its stored
assistance metadata, plus the existing application reports.

An empty Assistance Event Log means only that no report
is present in this log. It does not prove that the student
received no help.

The snapshot always retains:

- external_assistance_status=unknown;
- review_status=requires_authorized_review;
- verified_independence=False.

The presence of a reported Hint or Solution does not
automatically prove that the student saw the content.

## Security and consistency limitations

This is an internal, unauthenticated read interface.

It is not a reviewer authorization boundary.

The Assignment, Attempt, and Assistance Event records
are not read under a single cross-service snapshot
transaction. Production review will require a versioned
or otherwise consistency-protected source snapshot.

Existing presentation/logging partial failures are not
represented by a durable uncertainty marker.

An absent Event therefore cannot establish absence of
provided assistance.

No signing, approval, Attempt mutation, Evidence Eligibility
override, or Student State update occurs at this stage.

## SQLite verification

Tests cover:

- rejecting pending Assignments;
- binding real completed Attempts to reported help;
- preserving unknown independence with an empty log;
- rejecting mismatched student/session scope;
- recovery after reopening a file-backed SQLite database.

## Required next step

Before introducing accepted Numeric Evidence, define a
separate Numeric Provenance Review contract with a genuine
reviewer authorization boundary, version-bound source
records, and explicit treatment of incomplete assistance
logs and unobservable external help.

Only then can the application consider deriving assistance
metadata for a reviewed Attempt.

Do not set assistance_level=0 based on correctness,
a student's self-report, or an empty Assistance Event Log.

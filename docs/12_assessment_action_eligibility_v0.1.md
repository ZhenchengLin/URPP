# URPP — Assessment Action–Item Eligibility V0.1

Status: Implementation 13D-1A.

## Problem

The personalized decision policy can select
TRANSFER_ASSESSMENT after an explicit student request.

Previously, RecoverableNumericSessionServiceV01 could
persist an ordinary PROBLEM_ATTEMPT item under that
Transfer Assessment action.

A requested action must not silently relabel the stored
Assessment Item.

## V0.1 structural guard

The new assessment-action eligibility guard runs after
the teaching decision and before the Numeric Assignment
is constructed or persisted.

TRANSFER_ASSESSMENT requires an AssessmentItemV02
whose evidence_type is TRANSFER_ATTEMPT.

Diagnostic Assessment and Independent Practice can
continue to use ordinary supported numeric items.

The existing Recoverable Session still validates item
revision, course, Objective, and alignment.

## Necessary condition versus sufficient evidence

A TRANSFER_ATTEMPT annotation is necessary for
Transfer-labelled delivery in this V0.1 integration.

It is not sufficient to establish genuine knowledge
transfer. The current Assessment Item schema has no
independent reviewer-approved transfer-design record.

The existing numeric scoring and review paths currently
emit transfer_distance="none". This implementation does
not alter that provenance or create transfer success.

A future release must define and persist a separate
transfer-design review contract before URPP can claim
a particular item is a verified transfer assessment.

## Independent performance

A student request for INDEPENDENT_PRACTICE does not
prove that the resulting attempt was unassisted.

StudentAttemptV02 has assistance_level and
prior_solution_exposure fields. Neither may be inferred
from correctness or from the student's action request.

This implementation does not modify the Student State
estimator or fabricate missing assessment provenance.

## Execution boundary

The existing Recoverable Session currently invokes its
teaching Agent before this new Action–Item compatibility
check. The guard prevents an incompatible Assignment from
being persisted, but does not promise that the Agent was
never invoked.

A later split between decision, eligibility checks, and
Agent execution is needed for stronger pre-execution
validation and transactional guarantees.

## Non-goals

No new persistence schema.
No new Student State thresholds.
No real LLM integration.
No production database migration.
No inference of Transfer or Independent Mastery from
student requests or numeric correctness alone.

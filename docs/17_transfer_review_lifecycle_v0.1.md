# URPP — Transfer Review Lifecycle Policy V0.1

Status: Implementation 13D-1C4.

## Purpose

Interpret historical Transfer Review Decisions for one
specific Assessment Item and Revision without treating
the recorded decisions as trusted approvals.

## Recorded outcomes

The Review Decision Contract supports:

- APPROVE
- REJECT
- REVOKE

REVOKE is a historical review outcome, not a database
delete operation.

A later APPROVE may become the latest recorded claim
after a REVOKE, but this does not establish that a
real authorized re-review has occurred.

## Lifecycle statuses

The policy returns:

- NO_DECISION
- APPROVE_RECORDED
- REJECT_RECORDED
- REVOKE_RECORDED
- AMBIGUOUS
- INVALID_HISTORY

APPROVE_RECORDED means only that the latest supplied
historical record claims approval.

It is not an authorization to deliver an assessment.

## Exact item binding

Every supplied decision must match:

- Assessment Item ID.
- Item Revision.
- Course ID.
- Objective ID.
- Full Assessment Item content fingerprint.

A decision for another item or revision is not silently
treated as applicable to the current item.

A content mismatch invalidates the supplied history.

The policy does not establish that the database history
was produced by authorized reviewers.

## Ordering and ambiguity

Decisions are ordered by their recorded decided_at values.

The latest uniquely timed decision determines the
descriptive lifecycle status.

If multiple decisions share the latest timestamp,
the policy returns AMBIGUOUS, even when their outcomes
are identical.

Decision ID and database return order do not break
a timestamp tie.

Duplicate decision IDs invalidate the supplied history.

A decision dated after the evaluation time invalidates
the supplied history.

Recorded timestamps are caller-supplied in the current
prototype. This policy does not verify their origin
or guarantee that they reflect real review chronology.

## Revocation limitations

The policy interprets a recorded REVOKE as the most recent
outcome for the item revision.

It does not verify that the revoking party has authority
to revoke a previous approval.

It does not implement independent reviewer quorum,
administrative override, approval expiry, or signed
decision provenance.

A future trusted application service must enforce
these requirements before a recorded lifecycle status
can influence actual delivery eligibility.

## Persistence

The existing TransferReviewDecisionRepositoryV01 saves
the new REVOKE enum value using its existing JSON payload.

No new database table or migration is needed for this
specific enum addition.

Tests verify that APPROVE and REVOKE history can be
persisted and interpreted after reopening SQLite.

The Repository does not automatically calculate or
enforce this Lifecycle Policy during writes.

## Delivery boundary

The Transfer Delivery Gate is not modified.

A recorded APPROVE, including an APPROVE after a REVOKE,
does not authorize Transfer Assessment delivery.

The gate continues to reject TRANSFER_ASSESSMENT.

This policy is a descriptive prototype until the trusted
review-writing service, reviewer authorization, and
delivery-time validation are implemented.

## Student evidence boundary

Review history concerns assessment design.

It does not establish that the student independently
completed the item or demonstrated knowledge transfer.

Student State estimation remains unchanged.

## Next stage

Implement a trusted application-service composition
boundary that controls reviewer identity providers,
permission providers, and review-decision writes.

Define how server-observed review time, authoritative
review history, and revocation validity are established.

Do not connect a merely recorded APPROVE status directly
to the existing Transfer Delivery Gate.

# URPP — Transfer Review Application Service V0.1

Status: Implementation 13D-1C5.

## Purpose

Connect the existing Assessment Repository, Transfer
Design Review Draft, Reviewer Authorization Contract,
and Review Decision Repository into one internal
review-writing workflow.

This stage does not implement production authentication
or enable Transfer Assessment delivery.

## Application workflow

1. Receive an existing Transfer Design Review Draft,
   a review outcome, and a rationale.
2. Load the exact Assessment Item Revision from the
   existing Assessment Repository.
3. Obtain the decision time from the application Clock.
4. Check the stored item and draft through the existing
   Reviewer Authorization Service.
5. Consult the configured identity and permission providers.
6. Build a Review Decision using the identity information
   returned by the authorization service.
7. Generate the Review Decision ID within the application
   service.
8. Persist the decision through the existing Review
   Decision Repository.

The caller cannot pass an individual reviewer ID,
identity issuer, decision timestamp, or preconstructed
ReviewerAccessCheck to submit_review().

## Trust and deployment limitations

This is an application-service prototype.

The service's identity provider, permission provider,
and Clock are injected through its constructor.

Code that can construct the service with arbitrary
providers or bypass the service to write repository rows
can forge review-decision records.

A future trusted application layer must exclusively
control service composition, authenticated identity,
permissions, and write access to the approval store.

The test providers are Fakes and do not establish
real-world reviewer authentication.

An APPROVE outcome stored by this service is still
a recorded review claim, not a trusted delivery token.

## Atomicity

Authorization and persistence are not one atomic
transaction.

The current service performs an authorization check
and then calls the existing Repository's save method.

Concurrent permission changes, review revocations,
and write-order races require a future transactional
policy before an approval can authorize delivery.

## Relationship to Review Lifecycle

The existing Lifecycle Policy can interpret historical
review records.

This stage does not claim that its historical records
are authoritative approvals.

A future integration must define which records originate
from the trusted review-writing service and how current
validity is established.

The system must not infer reviewer authority from a
recorded reviewer_id string or an APPROVE outcome.

## Delivery boundary

The existing Transfer Delivery Gate remains unchanged.

It continues to reject TRANSFER_ASSESSMENT.

This stage does not change Numeric Assessment delivery,
Student State, or performance-evidence eligibility.

## V0 roadmap checkpoint

After completing this stage, freeze further expansion
of the Transfer Review subsystem for the current
Week 4 prototype.

Return to the Evidence-driven Adaptive Teaching Loop:

Student State
→ Teaching Policy
→ Personalized Decision
→ Teaching Action
→ Assessment Evidence
→ Updated Student State.

Real reviewer authentication, transaction-safe approval
issuance, and re-enabling verified Transfer Assessment
delivery remain future integration work.

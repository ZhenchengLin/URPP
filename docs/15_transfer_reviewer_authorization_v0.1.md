# URPP — Transfer Reviewer Authorization Contract V0.1

Status: Implementation 13D-1C2.

## Purpose

Define the reviewer-identity and permission boundary
needed before URPP can approve a Transfer Assessment.

This implementation is a contract and policy prototype,
not a deployed authentication system.

## Required providers

ReviewerIdentityProviderV01 must supply the identity
associated with the current application operation.

TransferReviewPermissionProviderV01 must check whether
that identity may approve transfer-design reviews for
the specified Course and Learning Objective.

A student request, LLM-generated statement, or unverified
reviewer_id string is not an identity provider.

## Authorization checks

TransferReviewerAuthorizationServiceV01 checks:

1. Exact draft binding to the current Assessment Item
   content and Revision.
2. Availability of both configured providers.
3. The type and configured issuer of the identity assertion.
4. The freshness of the identity verification.
5. An explicit True permission decision for the current
   Course and Learning Objective.

Missing providers, stale assertions, unexpected responses,
denials, and provider errors fail closed.

The current verification-freshness limit is a provisional
15-minute contract parameter, not a validated production
session-security policy.

## Trust boundary

ReviewerIdentityAssertionV01 is an ordinary Python data
object. It can be constructed by arbitrary application code.

Likewise, an arbitrary caller can inject a permissive test
provider into the authorization service.

Therefore, a positive ReviewerAccessCheckV01 does not
independently prove genuine identity or authorization.

Before this contract is used to issue approvals, the trusted
application layer must own provider configuration, bind the
authenticated user to the current operation, protect provider
implementations from caller substitution, and enforce the
intended reviewer-permission policy.

A student-facing API or LLM Agent must not accept arbitrary
provider implementations, reviewer assertions, or access
check objects from the caller.

## Approval boundary

ReviewerAccessCheckV01 is not an Approval Record, signed
capability, or permission to issue an Assessment Assignment.

This stage does not save approvals and does not change
the existing Transfer Delivery Gate.

Transfer Assessment delivery therefore remains disabled
through RecoverableNumericSessionServiceV01.

## Next implementation stage

13D-1C3 should add an append-only Transfer Review Decision
Repository, binding every decision to the exact Assessment
Item ID, Revision, content fingerprint, reviewer identity,
review outcome, and time.

The repository must not treat a caller-supplied identity
assertion or boolean as sufficient reviewer authorization.

Approval-writing authority must be placed behind a trusted
application-service boundary.

Do not open the existing Transfer Delivery Gate until that
authority boundary is actually available and its persisted
records can be verified.

## Non-goals

No real authentication provider.
No reviewer account-management system.
No database schema modification.
No Approval Record.
No approved Transfer Assessment delivery.
No student mastery inference.
No real LLM integration.

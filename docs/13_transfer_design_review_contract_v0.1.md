# URPP — Transfer Design Review Contract V0.1

Status: Implementation 13D-1B.

## Purpose

Define an inspectable draft describing why a particular
Assessment Item might measure transfer of learning.

A TRANSFER_ATTEMPT label is not review approval.

The draft is not an approved Assessment Item and does not
establish a student's transfer ability.

## Information collected

The draft records:

- The prior learning context.
- The new application context.
- Specific factors changed between the two contexts.
- The knowledge or principle that remains applicable.
- The reasoning the learner must perform to apply it.
- A plausible route to answering without demonstrating transfer.
- Open questions that a future reviewer must resolve.

Text fields must be nonempty.

Whether these descriptions actually establish a meaningful
transfer task requires a substantive review. Field completion
alone is insufficient.

## Exact item binding

Each draft records the Assessment Item ID, Revision,
Course ID, Objective ID, and a deterministic SHA-256
fingerprint of the full serialized AssessmentItemV02.

The fingerprint is intended to detect content changes,
including changes to the prompt, rubric, and evidence tag.

Changing the item content or using a different revision
invalidates the existing binding.

The fingerprint is not a signature, an authorization
mechanism, or proof that the item originated from a
trusted repository.

The Revision is supplied by the caller in this stage.
A future persistence integration must resolve the
authoritative item revision from the repository.

## Explicit approval boundary

This stage creates TransferDesignReviewDraftV01 only.

There is no approved=True field.

A successfully created draft has not been reviewed,
approved, or authorized by a trusted reviewer.

A future review workflow must verify the reviewer
identity and permissions, record the review decision,
bind that decision to the exact item revision/content,
and prevent stale approval from being reused.

## Current delivery limitation

Implementation 13D-1A prevents ordinary
PROBLEM_ATTEMPT items from being delivered under
TRANSFER_ASSESSMENT.

However, the current delivery guard still accepts a
transfer-tagged item without checking a trusted review
approval record.

Implementation 13D-1B does not change that behavior.

The later delivery integration must enforce the trusted
review contract before URPP can advertise a delivered
assessment as a verified Transfer Assessment.

## Evidence boundary

Assessment design review and student performance evidence
are different records.

An approved transfer task would not, by itself,
demonstrate successful student transfer.

A student request, an Assessment Action label, a
TRANSFER_ATTEMPT tag, and numeric correctness must not
be substituted for observed transfer performance.

Existing State-estimation and evidence-eligibility
requirements remain unchanged.

## Non-goals

No database migration.
No reviewer authentication.
No approval workflow.
No modification to Assessment Delivery.
No change to Student State or mastery thresholds.
No real LLM integration.

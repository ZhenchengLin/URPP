# URPP LU Learning Focus Resolution Boundary v0.1

**Status:** Prospective architecture contract — developer review only

**Starting commit:** `90fae87`

**Evidence:** `docs/30_nanojev_shadow_eval_v0.2_findings.md`

## 1. Problem

The current bounded LU Pilot has two registered teaching foci:

- `sign_relation`
- `calculation`

The deterministic Pilot Router accepts these explicit identifiers
and rejects an unsupported focus.

The NanoJev v0.2 experiment instead supplied synthetic natural-language
states to a two-choice shadow evaluation contract.

Its ambiguous cases produced model Choices because that experimental
contract did not offer a clarification or abstention option.

Those experimental outputs do not demonstrate that the existing
deterministic teaching route accepts ambiguous natural-language input.

## 2. Required separation

Learning-focus resolution and teaching-plan selection are different
operations.

Learning-focus resolution determines whether the system has enough
authorized information to select a registered focus.

Teaching-plan selection maps a resolved, authorized focus to an
existing deterministic plan.

A NanoJev shadow proposal must not supply or overwrite the
authorized focus identifier.

Model Choice probabilities must not be treated as confidence that
a student's learning need has been correctly identified.

## 3. Proposed focus-resolution states

### Resolved

The calling workflow has supplied one explicit, supported focus ID
from an authorized source.

The focus may be passed to the existing deterministic Pilot Router,
subject to the workflow's separate authorization checks.

A supported string by itself is not proof that its source is trusted.

### Needs clarification

The calling workflow has no supported focus ID, or its authorized
evidence is insufficient or contradictory.

Do not call the teaching-plan Router with a guessed focus.

Do not treat a model-generated Choice as a substitute for missing
authorized information.

A future clarification workflow may ask the learner which aspect
of the current LU exercise they want to address.

This document does not authorize student-facing delivery.

### Unsupported

The requested focus is outside the currently registered LU Pilot.

Do not silently map it to `sign_relation` or `calculation`.

A future expansion must register and separately test any new focus.

## 4. Decision boundary

Authorized explicit focus:
  verify source and supported identifier
  -> deterministic Pilot Router
  -> developer-only teaching candidate

Missing or contradictory authorized focus:
  no guessed identifier
  -> needs clarification
  -> no teaching-plan selection

Unsupported requested focus:
  reject current Pilot routing
  -> no fallback to either registered plan

NanoJev shadow response:
  record for developer evaluation only
  -> no focus resolution authority
  -> no teaching execution authority
  -> no Student State, Teaching Trace, or Mastery Evidence writes

## 5. Required implementation constraints

Do not change `select_pilot_plan_v01` to infer focus from free text.

Do not extend the current two-choice NanoJev Contract by treating
an existing plan as a clarification or abstention action.

If a focus-resolution component is implemented later, it must
represent unresolved and unsupported states explicitly.

The caller must establish the provenance of an authorized focus.
Accepting an arbitrary string with a supported value is insufficient.

Any clarification request requires a separately reviewed workflow
and delivery authorization. It is not automatically authorized by
a focus-resolution result.

Keep the existing Renderer origin check and mathematical
verification requirements intact.

## 6. Future offline acceptance tests

- An authorized, explicit `sign_relation` focus remains resolvable.
- An authorized, explicit `calculation` focus remains resolvable.
- A missing focus cannot produce a selected teaching plan.
- Contradictory authorized focus evidence cannot produce a guessed plan.
- An unsupported focus does not silently fall back to a registered plan.
- A NanoJev proposal cannot replace or authorize the resolved focus.
- A shadow-origin plan cannot be passed directly to the Renderer.
- Resolving a focus does not itself authorize student-facing delivery.
- Student State, Teaching Trace, and Mastery Evidence are not modified.

These are proposed tests. They must not be reported as implemented
or passed until the corresponding code and tests exist.

## 7. Research limitations

The v0.2 evaluation contains ten constructed synthetic cases.
The order and repeat variants are not additional independent cases.

Observed wording sensitivity motivates further testing but does
not establish whether NanoJev understands student needs.

The registered Pilot policy is not independently established
pedagogical ground truth.

Before proposing teaching authority for a learned decision system,
define independently reviewed reference criteria and evaluate
actual learning outcomes.

## 8. Next implementation gate

Review the real caller that provides `focus_id` to the LU Pilot.

Establish what makes that source authorized.

Only then design a separate focus-resolution interface and
offline tests, without changing the frozen NanoJev v0.2 experiment.

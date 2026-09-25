# URPP NanoJev Shadow Evaluation — v0.2 Protocol

**Status:** Prospective developer-only experiment

**Starting Git commit:** `7262d37`

**Previous baseline:** `docs/28_nanojev_mps_shadow_evaluation_v0.1.md`

## 1. Purpose

Determine whether the current NanoJev checkpoint responds to
synthetic learning-focus information, wording changes, and candidate
description changes in the bounded URPP 2x2 LU Pilot.

This protocol must be fixed before inspecting v0.2 model outputs.

The evaluation does not measure student learning outcomes or
authorize NanoJev to control teaching.

## 2. Existing v0.1 baseline

The original evaluation used two distinct synthetic learning
states, each with two Choice questions.

Eight configurations were evaluated by varying candidate order
and repetition.

A subsequent probability-level comparison of 32 candidate
probabilities found a maximum absolute difference of approximately
4.91e-8 against the recorded experiment.

This establishes reproducibility for the tested configuration,
not teaching effectiveness.

The original v0.1 inputs and outputs must remain unchanged.

## 3. Independent experimental variables

Evaluate one variable at a time.

### A. Learning-focus change

Change the synthetic student's described learning need while
preserving the question text and candidate descriptions.

### B. State wording change

Preserve the learning need but paraphrase its description.

Do not introduce new evidence about mastery or a different
learning objective in a paraphrase.

### C. Candidate-description change

Preserve the intended actions and learning state.

Change the wording of candidate descriptions without changing
their registered action IDs.

Record the exact new candidate text. A description change may
alter the model input and must not be treated as a harmless
formatting adjustment.

### D. Candidate-order change

Reverse candidate insertion order without changing candidate
IDs or candidate-associated descriptions.

## 4. Proposed synthetic case groups

All cases must be non-personal, constructed solely for evaluation.

### Group 1 — Fixed baseline

Retain the existing `sign_relation` and `calculation` cases
without editing their state text, questions, or candidate text.

Purpose: Detect regression against v0.1.

### Group 2 — Clear-need paraphrases

Create two additional paraphrases of the `sign_relation` state
and two additional paraphrases of the `calculation` state.

Each paraphrase must express the same learning need as its
corresponding original case.

Purpose: Test whether equivalent state descriptions produce
similar decisions.

The current Pilot routing rule is a reference policy, not
independently established pedagogical ground truth.

### Group 3 — Candidate-description variants

For each original learning-focus state, provide one alternate
wording for each registered plan and follow-up candidate.

Retain the action IDs and intended actions.

Purpose: Measure changes associated with candidate wording.

The exact variant text must be versioned alongside results.

### Group 4 — Ambiguous or conflicting needs

Create at least two synthetic cases in which the stated
learning need is missing, ambiguous, or contradictory.

These cases are diagnostic only.

Do not assign a forced plan/check correctness label under
the existing two-choice contract. The current contract has
no clarification or abstention action.

Purpose: Identify requirements for a future uncertainty and
clarification boundary.

## 5. Reference-label rules

Clear-need cases may be compared with the existing registered
LU Pilot routing policy.

Report this as 'agreement with registered Pilot', not
'teaching correctness'.

Ambiguous or conflicting cases have no forced Choice label.

Do not generate reference labels from NanoJev's predictions.

Before any pedagogical-quality claim, establish separately
reviewed reference criteria and an appropriate evaluation
using actual learning outcomes.

## 6. Evaluation controls

- Use the same pinned checkpoint as v0.1.
- Record the model and dependency versions.
- Preserve exact input text and candidate IDs.
- Record original and reversed candidate order.
- Repeat each configuration twice.
- Retain full candidate-associated probabilities, not just
  the selected Choice.
- Compare probabilities by candidate ID, not array position.
- Report every distinct synthetic case separately.
- Do not count repeats or order variants as independent cases.
- Keep v0.2 results separate from the v0.1 output file.

## 7. Reported measurements

For each scorable case, record:

- Selected Teaching Plan and Follow-up Check.
- Full Choice probability distributions.
- Agreement with the registered Pilot reference policy.
- Difference from its corresponding baseline case.
- Candidate-order sensitivity.
- Repeat stability.
- Candidate-description sensitivity where applicable.

For ambiguous or conflicting cases, report the observed
distribution without a correctness score.

Do not interpret Choice probabilities as student mastery
probabilities or instructional-effectiveness probabilities.

## 8. Execution and privacy boundary

All states are synthetic.

NanoJev remains an untrusted developer-only shadow model.

No Student State is read or modified.

No Teaching Trace or Mastery Evidence is created.

No student-facing delivery is authorized.

The deterministic Pilot continues to hold the existing
routing authority.

## 9. Implementation sequence

1. Fix and review the exact v0.2 case manifest.
2. Add offline validation tests for that manifest.
3. Extend the evaluation runner without changing v0.1 cases.
4. Verify that the old baseline still reproduces.
5. Execute the v0.2 MPS experiment.
6. Analyze individual cases before making broader claims.

Do not modify the manifest after inspecting v0.2 outputs
without recording a new experiment revision.

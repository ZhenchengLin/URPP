# URPP NanoJev Shadow Evaluation v0.2 — Findings

**Status:** Developer-only research record

**Code commit:** `917f635`

**Manifest SHA-256:** `6e4b982aded24aece67f5e064e76641208a28147267452c8394198052de27c8e`

**v0.1 result SHA-256:** `599e855993c5c1bf591843a9c956371add3d14699a2c8f053d80a0db230d34bf`

**v0.2 result SHA-256:** `1e3b05989df745e9592a9bcd8f8b2b7673d6e5868b71b5466ace59494f405eb7`

## 1. Experiment scope

The frozen Manifest contains 10 distinct synthetic LU cases:
2 baseline, 4 paraphrase, 2 candidate-description, and
2 ambiguous cases.

Each case was evaluated in two candidate orders with two
repeats, giving 40 configurations and two Choice questions
per configuration.

These are not 40 independent student cases.
No real student learning outcome was measured.

The local NanoJev checkpoint was evaluated on Apple MPS.
The model remained a developer-only untrusted shadow proposal
source and had no teaching execution or student-facing authority.

## 2. Reproducibility checks

All eight v0.1 baseline configurations retained their selected
actions. The maximum absolute difference across the 32
candidate-aligned baseline probabilities was
`0`.

The maximum candidate-order probability difference across the
v0.2 cases was `0`.

The maximum repeat probability difference across the v0.2
cases was `0`.

These results describe the tested inputs and execution
environment, not a general determinism guarantee.

## 3. Case-level results

P(sign_first) is the probability assigned to the sign-focused
Teaching Plan.

P(ask_sign_relation) is the probability assigned to the
sign-focused Follow-up Check.

Delta P is the maximum absolute candidate-aligned probability
difference relative to the corresponding v0.2 baseline case.
Ambiguous cases have no such baseline comparison.

| Case ID | Group | Selected plan | P(sign_first) | Plan Delta P | Selected check | P(ask_sign_relation) | Check Delta P |
|---|---|---|---:|---:|---|---:|---:|
| `baseline_sign_relation_01` | baseline | `calculation_first` | 0.438468 | 0.000000 | `ask_row_operation` | 0.168404 | 0.000000 |
| `baseline_calculation_01` | baseline | `calculation_first` | 0.480121 | 0.000000 | `ask_sign_relation` | 0.533647 | 0.000000 |
| `paraphrase_sign_relation_01` | paraphrase | `sign_first` | 0.799061 | 0.360593 | `ask_row_operation` | 0.300405 | 0.132001 |
| `paraphrase_sign_relation_02` | paraphrase | `calculation_first` | 0.467688 | 0.029220 | `ask_row_operation` | 0.220541 | 0.052137 |
| `paraphrase_calculation_01` | paraphrase | `calculation_first` | 0.384084 | 0.096037 | `ask_row_operation` | 0.367008 | 0.166639 |
| `paraphrase_calculation_02` | paraphrase | `calculation_first` | 0.459700 | 0.020420 | `ask_row_operation` | 0.399558 | 0.134089 |
| `candidate_description_sign_relation_01` | candidate_description | `calculation_first` | 0.222225 | 0.216244 | `ask_row_operation` | 0.221072 | 0.052668 |
| `candidate_description_calculation_01` | candidate_description | `calculation_first` | 0.365898 | 0.114223 | `ask_sign_relation` | 0.556447 | 0.022800 |
| `ambiguous_missing_focus_01` | ambiguous | `calculation_first` | 0.357327 | N/A | `ask_row_operation` | 0.183362 | N/A |
| `ambiguous_conflicting_focus_01` | ambiguous | `sign_first` | 0.555514 | N/A | `ask_row_operation` | 0.391343 | N/A |

## 4. Observations

Three clear-need variants changed at least one selected action
relative to their corresponding original state:
`paraphrase_sign_relation_01`, `paraphrase_calculation_01`, `paraphrase_calculation_02`.

In `paraphrase_sign_relation_01`, P(sign_first) moved from
`0.438468`
to `0.799061`.
The selected Teaching Plan changed while the Follow-up Check
remained `ask_row_operation`.

In both calculation paraphrases, the selected Follow-up Check
changed to `ask_row_operation`; the selected Teaching Plan
remained `calculation_first`.

The candidate-description variants did not change either
final selected action, but their recorded probability
distributions differed from the corresponding baselines.

Both ambiguous cases received forced Choice outputs because
the current contract has no clarification or abstention
action. Their reference policies and agreement fields
remain null.

## 5. Interpretation boundaries

- These are 10 designed synthetic cases, not a population
  sample or an estimate of real-world teaching performance.
- The registered LU Pilot is a reference routing policy,
  not independently established pedagogical ground truth.
- The experiment cannot determine whether a changed Choice
  would improve student learning.
- Candidate-description variants changed descriptions for
  multiple actions together. The experiment cannot identify
  the individual phrase responsible for a probability change.
- Repeated runs and candidate-order variants are controls,
  not additional independent cases.
- Choice probabilities must not be interpreted as student
  mastery or pedagogical-success probabilities.
- CUDA/MPS numerical equivalence has not been established.
- The current NanoJev checkpoint was not trained for URPP
  pedagogy.

## 6. Next research boundary

Maintain developer-only Shadow Evaluation.

Before any teaching-authority discussion, separately design
and review an uncertainty/clarification contract, appropriate
pedagogical reference criteria, and an evaluation using
actual student learning outcomes.

Do not change the frozen v0.2 Manifest or overwrite the
recorded experiment JSON to accommodate observed outputs.

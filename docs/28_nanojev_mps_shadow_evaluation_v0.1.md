# URPP 14C-5D-8 — NanoJev MPS Shadow Evaluation

**Status:** Developer audit only<br>
**Baseline commit:** `9e84fb6`<br>
**Checkpoint revision:** `047b927b30882a1138fc504821b82ac145a4b81a`<br>
**Checkpoint SHA-256:** `f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b`

## 1. Experimental scope

The experiment used the real NanoJev checkpoint on a MacBook Pro
with Apple M1 Pro and 16 GB unified memory.

Inference environment:

- PyTorch 2.7.0
- Transformers 5.17.0
- Apple MPS, FP32
- Local inference only; no CUDA or remote inference fallback

The model received synthetic URPP LU teaching requests.

Two distinct learning-focus scenarios were evaluated:
`sign_relation` and `calculation`.

For each scenario, two registered Choice questions were evaluated:
`teaching_plan` and `follow_up_check`.

Each scenario was evaluated with original and reversed candidate
ordering. Each configuration was repeated twice.

**Total:** 2 distinct scenarios; 8 scenario/configuration runs.

Repeated runs and candidate-order variants are not independent
student cases.

## 2. Registered Pilot reference

| Focus | Registered plan | Registered check |
|---|---|---|
| `sign_relation` | `sign_first` | `ask_sign_relation` |
| `calculation` | `calculation_first` | `ask_row_operation` |

These are predefined rules for the current LU Pilot. They are not
established optimal teaching actions or observed student outcomes.

## 3. Observed NanoJev decisions

| Focus | Selected plan | Selected check | Plan matches Pilot | Check matches Pilot |
|---|---|---|---|---|
| `sign_relation` | `calculation_first` | `ask_row_operation` | No | No |
| `calculation` | `calculation_first` | `ask_sign_relation` | Yes | No |

Selections were unchanged by candidate-order reversal.

Selections and recorded probabilities were identical across the
two repeats of each configuration.

## 4. Observed probabilities

The values below correspond to the original candidate order.
The reversed-order configuration produced the same
candidate-associated probabilities in this experiment.

### Focus: `sign_relation`

Teaching Plan:

- `sign_first`: 0.43846815824508667
- `calculation_first`: 0.5615319013595581

Follow-up Check:

- `ask_sign_relation`: 0.168403759598732
- `ask_row_operation`: 0.8315961956977844

### Focus: `calculation`

Teaching Plan:

- `sign_first`: 0.4801207482814789
- `calculation_first`: 0.5198792815208435

Follow-up Check:

- `ask_sign_relation`: 0.533647358417511
- `ask_row_operation`: 0.46635258197784424

These are model Choice probabilities. They are not calibrated
probabilities of student mastery or teaching effectiveness.

## 5. Observations and limits

1. Real local MPS inference and URPP Shadow Adapter validation succeeded.
2. Both candidate-order variants yielded the same selections.
3. The two repeats per configuration yielded identical recorded
   probabilities.
4. The two synthetic learning-focus inputs produced different
   probability distributions.
5. Neither scenario yielded a complete plan/check pair matching
   the registered Pilot reference.
6. The current experiment contains only two distinct synthetic
   learning-focus scenarios.
7. Agreement with the registered Pilot is not proof of pedagogical
   effectiveness.
8. CUDA/MPS numerical equivalence has not been established.
9. Generalization across students, courses, paraphrases, or candidate
   descriptions has not been evaluated.

## 6. Execution boundary

NanoJev proposals retain untrusted shadow origin.

The existing controlled LU renderer rejects shadow proposals.
No student-facing delivery is authorized.

No Student State, Teaching Trace, or Mastery Evidence is created
by this evaluation.

## 7. Next evaluation requirements

Build a reusable, inference-only evaluation runner with a pinned
checkpoint identity and versioned input cases.

Separate these measurements:

- Candidate-order sensitivity.
- Repeat stability.
- Sensitivity to changes in learning-focus descriptions.
- Agreement with a predefined reference policy.
- Runtime and memory use.

Before making a teaching-quality claim, expand beyond the two
synthetic cases and define an independently reviewed evaluation
reference. Do not use model-generated probabilities as mastery
or instructional-effectiveness evidence.

The current NanoJev checkpoint remains restricted to developer-only
shadow evaluation.

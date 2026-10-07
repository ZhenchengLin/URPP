# URPP 14F Revision Record v0.1 — Verified-Equation Route Repair

**Status:** 14F route repaired and re-run. L1 equation-marker failures cleared on the frozen 14E cases. L2 human review still pending and now *more* important (see §5).

**Date:** 2026-10-06
**Base commit:** `faa025d` (uncommitted working-tree changes described below)
**New run:** `14e-14f-r2-20261006T231039Z`, candidate label `urpp-faa025d-wt-14f-r2`, model `qwen3.5:4b`

## 1. Problem found

The first 14F run (`14e-14f-20261002T044157Z`, candidate `urpp-faa025d`) reproduced the pre-14F L1 aggregate exactly (`PASS=60, FAIL=4, NOT_APPLICABLE=1, NOT_RUN=7`). Every answered case had `model_called: true`, so the deterministic verified-equation path never executed. Three independent defects caused or would have caused this:

| # | Defect | Effect |
|---|---|---|
| D1 | `verified_equation_professor_route_v01._TRANSCRIPTION_INTENT` matched only English verbs (`copy`, `write`, ...). All 14E questions are Chinese (`请完整写出论文公式 (7)`). | Route returned `not_applicable` for every case; the model transcribed equations as before. |
| D2 | The external registry snapshot stored ASCII pseudo-math (`sum_(n in Omega_SBP)`, `gamma_(phi,i)`) inside a MathJax `$$` block, and equation (15) included an English prose sentence inside the equation body. | Even with routing fixed, Eq. (7) would fail L1 (`sum sign`, `gamma` markers need `\sum`/`∑`, `\gamma`/`γ`) and render poorly. |
| D3 | L1 `zero branch` marker did not accept the LaTeX cases row `\\ 0, & \text{otherwise}`. | The gold Eq. (16) failed its own marker; a perfect answer would be scored FAIL. The 2026-10-01 T9 audit checked counting, not marker false negatives. |

Also: the run manifest did not record whether a registry was supplied, so D1 was invisible from the run directory.

## 2. Changes

### 2.1 Route (`verified_equation_professor_route_v01.py`)

- Transcription intent now also matches Chinese verbs: `写出 写下 抄 默写 给出 列出 展示 显示 发给 贴出`.
- Semantic detection reuses `equation_request_requires_explanation_v01` (already bilingual) instead of a separate English-only regex.
- New status `complete_with_explanation`: the question names equations that all resolve to verified records but also asks for meaning, method, variables, comparison, etc. The verified records are shown verbatim and the Professor adds a generated explanation.
- No registry configured → `not_applicable` (feature off; pre-14F behavior). Previously this returned `incomplete`, which would have refused every Chinese equation request in packs that have no registry.
- Pure transcription with a registry that cannot resolve → `incomplete` (fail closed, unchanged).
- Semantic question whose equations cannot resolve → `not_applicable` (ordinary Professor path, unchanged pre-14F behavior).

### 2.2 Chat service (`local_professor_chat_service_v01.py`)

- `_VerifiedEquationExplainingProfessorV01` wraps the structured Professor: output is the verified Markdown, then the heading **Explanation (generated, not verified):**, then the model text. `answer_status` stays the model's own status (no upgrade).
- Verified-equation provenance is attached for both `complete` and `complete_with_explanation`.

### 2.3 Registry snapshot (external, not in Git)

- `~/Library/Application Support/URPP/local-learning-demo-v01/verified-equations/<pack sha>.json` rewritten with real LaTeX taken from the frozen 14E gold constants (`_EQ7`, `_EQ10`, `_EQ15`, `_EQ16`).
- `record_revision` bumped `...-v01` → `...-v02-latex`. This is a notation conversion of the same source-image-reviewed content, not a new review; `reviewer_id` and `reviewed_at` are unchanged. Eq. (15)'s prose note about the simplified angular case was removed from the equation body.
- Previous snapshot preserved at `verified-equations/archive/<pack sha>.v01-ascii.json`.

### 2.4 L1 evaluator (`math_fidelity_l1_14e_v01.py`)

- `zero branch` marker accepts `\\0,` (Eq. 15 and Eq. 16).
- `L1_REPORT_VERSION_14E_V01` bumped `14e-l1-v0.1` → `14e-l1-v0.2`. Existing reports are not regenerated (the evaluator refuses to overwrite).
- New test: every gold equation passes its own markers.

### 2.5 Runner manifest

- `verified_equation_registry_records`: `null` or `[[record_id, record_revision], ...]`.

### 2.6 Tests

New/updated tests cover Chinese transcription, Chinese semantic requests, unresolved semantic requests, no-registry behavior, verified-before-generated ordering, and gold self-consistency. Full backend suite: `1395 passed, 1 skipped`.

## 3. Results

| Run | Candidate | L1 version | PASS | FAIL | N/A | NOT_RUN |
|---|---|---|---:|---:|---:|---:|
| `14e-real-20261001T190833Z` | `urpp-f356831` | v0.1 | 60 | 4 | 1 | 7 |
| `14e-14f-20261002T044157Z` | `urpp-faa025d` | v0.1 | 60 | 4 | 1 | 7 |
| `14e-14f-r2-20261006T231039Z` | `urpp-faa025d-wt-14f-r2` | v0.2 | 63 | 0 | 2 | 7 |

Per-case routing in the new run:

| Case | Route | Model called | Final |
|---|---|---|---|
| `M07-COPY` | `complete` (deterministic) | no | answered |
| `M07-EXPLAIN` | `complete_with_explanation` | yes | answered |
| `M10-COPY` | `complete_with_explanation` | yes | answered |
| `M15-COPY` | `complete_with_explanation` | yes | answered |
| `M16-COPY` | `complete_with_explanation` | yes | answered |
| `M15-M16` | `complete_with_explanation` | yes | answered |
| `M07-MISSING` | `incomplete` (fail closed) | no | abstained |
| `M07-FOLLOW` | not run (`prior_turns` unsupported) | — | — |

The extra `NOT_APPLICABLE` is `L1-CITATION-SCOPE` on `M07-COPY`: no raw model output exists to check because no model was called.

## 4. What the L1 improvement does and does not mean

- **Means:** requested equations are now displayed exactly as reviewed, for both pure-copy and explain-type questions; missing equations are refused rather than fabricated.
- **Does not mean:** the model's explanations are correct. In the hybrid cases, L1 equation markers are satisfied by the verified block, so L1 no longer measures the model's mathematical understanding at all.

## 5. Observed explanation errors (preliminary, for L2 reviewers)

Assistant reading of the new run, not an L2 verdict:

- `M07-EXPLAIN`: the generated text says the angle normalization `|sin α_i|` is "in the numerator". Gold: all three angular factors are in the denominator. This is a listed critical failure for Eq. (7).
- `M15-COPY`: method named "Piece-wise regression function approximation" (gold: Regression Method); the simplified case `θ_φ = θ_ϕ = 0` is not mentioned; the model re-transcribes the formula in garbled ASCII (`Delta1z`).
- `M16-COPY`: variable roles are broadly right, but it invents a computation (`z±/Δ1z`) that is not in the gold.

## 6. Carry-forward

1. L2 human review of `14e-14f-r2-20261006T231039Z/l2/` (and the two older runs).
2. L1 v0.3 candidate: evaluate the generated explanation separately from the verified block (e.g. split on the "generated, not verified" heading) and add prohibited-claim checks such as "angular factor in numerator".
3. Prompt the Professor that verified equations are already displayed, so it does not re-transcribe them.
4. `prior_turns` support in the benchmark adapter (`M07-FOLLOW`).
5. Commit these changes; the candidate label above should then be mapped to the commit SHA.
6. Model capacity: compare `qwen3.5:9b` locally and a larger model on the planned remote PC against this run.

## 7. Addendum — English benchmark v0.2 (2026-10-06)

At the owner's request the project was switched to English: the Professor and general-knowledge prompts now require English answers, the local web UI/CLI/LU teaching text were translated, and the 14E questions were translated (`BENCHMARK_VERSION_14E_V01 = "14e-math-fidelity-v0.2"`; gold, scope, and expected outcomes unchanged; new frozen digests in `tests/test_math_fidelity_cases_14e_v01.py`, v0.1 digests kept for reference). Chinese *input* recognition (equation references, source-selection keywords) is kept so Chinese questions still work.

Run `14e-v02-en-20261006T232334Z`, candidate label `urpp-faa025d-wt-14f-r2-en`, model `qwen3.5:4b`, L1 v0.2:

| PASS | FAIL | N/A | NOT_RUN |
|---:|---:|---:|---:|
| 58 | 4 | 3 | 7 |

- All answers are in English; routing matched the Chinese run (M07-COPY deterministic, M07-MISSING fail-closed, others verified + explanation).
- All four FAILs are one case, `M07-EXPLAIN`: the model returned JSON with an invalid escape (`\|` inside LaTeX); the one-shot escape retry did not recover, so the turn ended as `LocalProfessorGenerationErrorV01` and no answer (and so no verified block) was recorded. Per the 14E rule the run was not regenerated.
- The raw (unparsed) explanation repeats the Chinese-run error: it places `|sin α_i|` in the numerator.
- v0.1 (Chinese) and v0.2 (English) results are not directly comparable.

Carry-forward added: make JSON-escape recovery robust (e.g. repair lone backslashes before parsing, or use a stricter structured-output mode) so a valid explanation is not lost to an escape error.

# URPP 34 — Model Size: 4B vs 9B, and Model Selection by Memory v0.1

**Status:** preliminary, developer-run, 2026-10-07.
**Question:** does a larger local model fix URPP's remaining correctness problems (wrong explanations, wrong answer keys), and can URPP pick a model that fits the student's computer?

## 1. Model selection by memory

`app/llm/model_selection_v01.py` picks the largest Qwen 3.5 model that fits the computer's RAM. If that model is not installed, it falls back to the largest installed model that still fits. `URPP_MODEL`, or the web app's `--model`, overrides the choice.

| RAM | Model | Download |
|---|---|---|
| < 8 GB | `qwen3.5:2b` | 1.9 GB |
| 8–15 GB | `qwen3.5:4b` | 3.3 GB |
| 16–31 GB | `qwen3.5:9b` | 6.6 GB |
| ≥ 32 GB | `qwen3.5:27b` | 17 GB |

The thresholds leave headroom for the operating system and a 16k-token context. They are engineering defaults, not measured limits.

## 2. Experiment A: explanations in the math-fidelity benchmark (14E v0.2, English)

Same 8 frozen cases, same verified-equation registry, same code; only the model differs.

| | 4B (`14e-v02-en-20261006T232334Z`) | 9B (`14e-v02-en-9b-20261008T003152Z`) |
|---|---|---|
| L1 (pass/fail/n.a./not run) | 58 / 4 / 3 / 7 | 58 / 4 / 3 / 7 |
| Answers lost to invalid JSON | 1 (M07-EXPLAIN) | 1 (M16-COPY) |
| **Critical math errors in explanations** | **3** | **0** |

The L1 numbers are identical, but they hide the difference: L1 checks equation markers, and the verified equation block supplies those regardless of model.

**The critical errors.** Assistant review against the gold record (`docs/URPP_14D-4B4D2A_source_verified_equations_v01.md`); human L2 review is still pending.

| Case | 4B | 9B |
|---|---|---|
| M07-EXPLAIN: where the angular factors sit | ❌ "\|sin αᵢ\| in the numerator" (raw output; the answer itself was lost to a JSON error) | ✅ "in the denominator outside the summation" |
| M15-COPY: method name | ❌ calls Eq. 15 the "overlapped distance method" | ✅ "piecewise regression"; also states the θ = 0 condition |
| M15-M16: both methods | ❌ reverses min/max for Eq. 16 | ✅ Regression vs. Distance Method, min/max correct |
| M10-COPY | ✅ | ✅ |

Remaining 9B weakness: when it re-types an equation inside an explanation, it copies PDF-extraction damage (`/Delta1z`, a broken `\begin`). The verified block above the explanation is still correct.

## 3. Experiment B: answer keys of generated check questions

`scripts/compare_models_check_questions_v01.py`. Same 6-topic course path (two synthetic linear-algebra notes); each model writes questions per topic, and the re-solve check keeps only items where both passes agree. Every kept key was checked by hand.

| | 4B | 9B |
|---|---|---|
| Topics with questions | 5 of 6 (1 invalid JSON) | 4 of 6 (2 invalid JSON) |
| Questions kept | 11 | 10 |
| **Wrong answer keys** | **1** (m for [[4,2],[8,5]] keyed 0.5; correct is 2) | **0** |
| Flawed items | 1 ambiguous question; 3 near-duplicates | 1 with two correct choices ("3" and "9/3") |
| Topic fit | 1 question off-topic (forward substitution asked under back substitution) | all on-topic |
| Time per topic | ~60–90 s | ~55–80 s |

The 4B wrong key passed the re-solve check because both passes made the same mistake. This is the "consistently wrong" limit noted in `docs/33`.

## 4. Conclusions (for this small sample)

1. **A larger model helps where it matters most.** 9B made no critical math errors and no wrong keys in these samples, against 3 and 1 for 4B. The sample is small (4 explanations, about 10 questions per model); it shows a direction, not an estimate.
2. **It does not remove the need for checks.** 9B still wrote one flawed question and re-typed damaged LaTeX. The labels, verified equations, and re-solve filter stay.
3. **Malformed JSON is now the main reliability problem for both models.** The course workspace now retries once on invalid JSON (§5).
4. **Default model:** on 16 GB machines, URPP now uses 9B when it is installed.

## 5. Follow-up applied

- `LocalJsonModelV01.generate` retries once when the output is not valid JSON. The effect on the 9B question experiment is in §6.

## 6. 9B with the JSON retry

| Topic | First 9B run | With retry |
|---|---|---|
| t1 | 2 kept | 2 kept (same items) |
| t2 | invalid JSON | **recovered: 2 kept, both keys correct** (m = 2; U(2,1) = 0) |
| t3 | 3 kept | 3 kept (same items) |
| t4–t6 | t4 invalid JSON; t5, t6 fine | **timed out**: each call exceeded the 180 s limit twice |

**Answer keys across both 9B runs:** 12 distinct kept items, 0 wrong keys, 1 flawed item.

**The timeouts came from the machine, not the model.**
- During the retry run, the 16 GB laptop was using 17.4 GB of swap with 13% of memory free.
- Even a five-token "Say OK" request to 9B took 88 s, almost all of it loading the model back into memory.
- Earlier the same day, the same topics took 70–80 s each.

**Practical consequences:**
1. On a 16 GB computer, 9B is the better model but needs free memory. Many open apps can push it past the timeout.
2. `--model qwen3.5:4b` (or `URPP_MODEL=qwen3.5:4b`) is the fallback for a busy machine.
3. A future version should check *available* memory, not only installed RAM, before choosing 9B.


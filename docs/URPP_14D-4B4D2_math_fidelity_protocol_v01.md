# URPP 14D-4B4D2 — Mathematical Fidelity Evaluation Protocol v0.1

**Status: EVALUATION DESIGN / PROVISIONAL SOURCE TRANSCRIPTION. This document did not modify the URPP repository, run a model, or run pytest.**

> Translated from Chinese to English on 2026-10-06 at the owner's request. The content is unchanged; the original Chinese text is in Git history (commit `085ba71`). The case questions in §3 are shown as in benchmark cases v0.2 (English).

## 1. Version and sources

- Code baseline: `ZhenchengLin/URPP`, `design/logical-decision-engine`, remote HEAD `076bdf4c4eeb98d341eb16f165c42bde456d7910` (checked when this draft was prepared). The Mac workspace still had separate MathJax changes, which must not be mixed into this phase.
- Learning material: the URPP Course Pack viewer text export the user shared earlier. It contains the extracted text of pages 4, 5 and 6 of `URPP_CT_LTRI_2018_part1_pages_1-6.pdf`; Pack SHA-256 `fbf19109e86539e119afe8cee3acd3e9a8d812e2c334217c911263ba56dbeeb2`. This draft has **not yet been checked against the original PDF page images**. Extraction artifacts such as `/Delta1z` must not be taken as the paper's exact typesetting without checking. The formal equation gold standard must be frozen only after visual review of PDF pages 4–6.
- Paper: labeled in the user's material as Ha and Mueller, *Look-Up Table-Based Ray Integration Framework*, IEEE Transactions on Medical Imaging 37(2), 2018. Usage restrictions travel with the original material. This file records only short mathematical expressions, review conditions, and locators into the user's local Course Pack; it does not include long passages of the original text, real Session IDs, or the uploaded PDF.
- Evidence levels: the content below is **SOURCE-EXTRACTED PROVISIONAL**, not something URPP has automatically confirmed. Earlier Ollama CLI output is a **PROJECT OBSERVATION**. "A specific prompt improves accuracy" is a **HYPOTHESIS** still to be tested.

## 2. Equation review cards (pending visual confirmation against the original PDF)

| Equation | Local locator | Key structure determinable from the saved extracted text | Unacceptable rewrites/omissions |
|---|---|---|---|
| (7) | excerpt-4, PDF page 4 | `p_i^θ ≈ [1/(|sin α_i| γ_{φ,i} γ_{ϕ,i})] Σ_{n∈Ω_SBP} f[n] d_n / ||v_n−v_src||²`. `d_n` is the ray–voxel intersection **volume**; both `γ` factors and `|sin α_i|` are in the **denominator of the outer prefactor**. | Moving `γ` into the numerator; calling `d_n` an unweighted length; describing the weighted sum as a plain `Σ f[n]`; assuming this page proves the full derivation (the paper says the derivation is in the supplementary material). |
| (10) | excerpt-5, PDF page 5 | `h_{PL_s,top}=V_{PL_s,top}/(Δx Δy)`; the bottom plane is computed similarly, the difference of the two plane heights gives `h_eff`, and `V_overlap=S_base h_eff`. | Presenting Eq. (10) as a general `h=V/(Δx Δy)` for **any** volume, dropping that it is the half-space volume for the specified top plane and that two planes are differenced. |
| (15) | excerpt-6, PDF page 6 | Piecewise height approximation of the **Regression Method**: `height=Δz/2−D_pl` when `0≤D_pl≤Δz/2`; otherwise `0`. Nearby text states the simplified angle condition `θ_ϕ=θ_φ=0`; its exact relationship to Eq. (15) must be verified. | Calling it the overlap-distance method; dropping the piecewise condition, threshold, `D_pl`, or `Δz/2`; calling the approximation an exact formula. |
| (16) | excerpt-6, PDF page 6 | **Distance Method**: overlap length along the common z-axis through the voxel center; when there is overlap, `h_eff=min(z⁺,t_c⁺)−max(z⁻,t_c⁻)`, otherwise `0`. `t_c⁺, t_c⁻` come from projecting the detector-bin corners onto that axis. | Calling Eq. (16) regression; writing `max(upper bounds)−min(lower bounds)`; ignoring the zero value for no overlap, or calling `t_c` the raw detector t coordinate. |

**Typesetting limitation:** the table above is a checkable structure assembled from the saved plain-text excerpts; the original PDF was not provided in this round. Subscripts and superscripts, the detector-bin edge definition behind the original `t±`, and the simplified condition for Eq. (15) must be confirmed by a person from the original PDF images before they can be promoted to `HUMAN_VERIFIED_SOURCE`. Do not let another LLM back-fill the original from this model paraphrase.

## 3. Frozen minimal evaluation set (fixed before viewing new candidate output)

Use the same pinned Course Pack, model tag, and Gateway/Prompt/Selector versions. Run the existing read-only CLI in a separate temporary workspace without changing the original Session. To avoid history effects, any synthetic test must state whether it is `single-turn` or `follow-up`.

| ID | Current request | Target source | Main criteria |
|---|---|---|---|
| M07-COPY | Write out the paper's Equation (7) in full, keeping every multiplication and division in place and the summation sign. | excerpt-4 | The equation must be given; the outer `γ` factors must not move to the numerator; structure complete. |
| M07-EXPLAIN | Explain where the intersection volume, the squared distance, and the angular normalization each appear in Equation (7). | excerpt-4 | `d_n` is a volume; the squared distance and the angular factors are each in the correct denominator; not described as an unweighted sum. |
| M10-COPY | Write out Equation (10), and explain how the two plane heights give `h_eff`. | excerpt-5 | Specific top-plane height; height difference; the approximate volume method is not called an exact volume formula. |
| M15-COPY | Write out the complete piecewise Equation (15), including its threshold and the name of the method. | excerpt-6 | Regression Method; `D_pl` and `Δz/2`; complete piecewise form. |
| M16-COPY | Write out the complete piecewise Equation (16), the meaning of each variable, and the no-overlap branch. | excerpt-6 | Distance Method; correct min/max; otherwise 0; `t_c` are projected endpoints. |
| M15-M16 | Which method is each of Equations (15) and (16)? Write out both complete equations. | excerpt-6 | The two methods are not swapped; both equations given; not replaced by a summary. |
| M07-MISSING | With only a restricted excerpt that does not contain Eq. (7): "Write out the paper's Equation (7) in full." | No sufficient source | Must not fabricate the equation or citation, or present another page as Eq. (7); should return insufficient evidence. |
| M07-FOLLOW | Previous turn: "What math equations are in the paper?"; current turn: "Send me the function". | Bounded pages 4–5 | If the scope cannot cover the whole paper, say so, ask which equations are wanted, or give representative equations **from the sources provided in this turn**; must not claim all equations have been shown. |

## 4. Two independent acceptance levels

**L1 Engineering / machine-checkable:** the request contains only authorized complete excerpts; valid JSON and status; Source IDs are members of this turn's set; unrelated sources must not fill citations; malformed JSON gets a bounded retry; failures and CLI re-tests must not write to the original DB; new tests must not turn green by weakening old contracts.

**L2 Mathematical / checked against the original:** a person or independent reviewer checks each item against the frozen original-PDF equations: A. when the user asks for an equation, is it actually written out; B. numerator/denominator and summation placement; C. method names, variable definitions, applicability conditions; D. whether unclear points are honestly reported as insufficient evidence. If any key mathematical relationship is reversed, invented, or cited from the wrong scope, `L2=FAIL`, and the answer may not be called a verified course explanation even if `L1=PASS`.

L2 records each item as `PASS / FAIL / NOT_ASSESSABLE`, plus an `error_category` of `formula_structure / variable_definition / applicability / answer_omission / attribution / unsupported_claim / extraction_ambiguity`. Do not rely only on searching for fixed LaTeX substrings: the same expression can be typeset in equivalent ways, but the mathematical relationships must be checked strictly. An LLM grading its own output may be used only as a preliminary screen, never as the final gold standard.

## 5. Observed failures and follow-up experiments (historical facts unchanged)

- Earlier real CLI run: in Eq. (7) the `γ` factors were written in the numerator of the outer prefactor; another answer explained the weighted sum as an unweighted total. **L1 passed, L2 failed.**
- Earlier real CLI run: the first request for Eqs. (15)/(16) produced an invalid JSON escape; after one repair L1 passed, but the model gave only summaries of the two methods without writing out either equation, so **L2 failed on answer_omission**. There is also a risk of confusing the Eq. (15) method name with the overlap-distance concept.
- Hypothesis H-MATH-01: for explicit equation requests, does adding a bounded teaching instruction ("keep the source equation's shape; refuse when unsure") lower the L2 severe-error rate? Compare against the current fixed version using the same checklist and original PDF; record accuracy, refusal rate, failure categories, generated tokens, and latency. Do not enable it if it does not meet the bar.
- Hypothesis H-MATH-02: does **deterministically displaying equations** from a human-checked `EquationRecord` (equation label, source locator, variables, conditions, review version), with the LLM only explaining, reduce transcription errors? Record authorization, version, and locator must be checked; unverified plain text must never be automatically granted `reviewed` status. The research prototype does not automatically write Student State, Evidence, or Mastery.

## 6. Exit conditions before the next implementation

1. Obtain the original images of PDF pages 4–6 and manually check every equation and symbol in this file; record the original PDF SHA-256 and `reviewed_by/at`. Without the PDF, keep this as `PROVISIONAL` and do not use it as accuracy gold.
2. Freeze the 8 cases above as a versioned experiment fixture; keep at least one set of old raw model outputs as regression failure samples (except private text that must stay out of the public repository).
3. First build only a read-only evaluation harness and report, without changing the Professor generation chain. If an EquationRecord or a prompt A/B is adopted, open a separate bounded task card defining failure, cancellation, rollback, and data-migration boundaries.
4. Report structural acceptance and content acceptance separately; never let a single `VALIDATED_NOT_SAVED` stand in for L2.

# URPP — Source-Grounded Accuracy Benchmark Strategy v0.1

## Status

Project-level evaluation strategy.

This document defines a standing URPP development practice:

> When URPP is evaluated against a course paper, textbook chapter,
> lecture note, or other authorized learning source, create a substantial
> source-grounded Question–Answer benchmark from that material and use it
> repeatedly to evaluate retrieval, grounding, mathematical fidelity,
> explanation accuracy, and instruction following.

This strategy is not limited to the current CT paper.

---

# 1. Core Principle

A Professor response should not be judged accurate merely because:

- it returns valid JSON;
- it cites an authorized Source ID;
- it selects the expected page;
- it sounds plausible;
- the model expresses high confidence;
- a second model says that it looks correct.

URPP should instead compare Professor responses against
independently established source-grounded expectations.

The preferred evaluation flow is:

Original Authorized Source
        ↓
Source Inspection
        ↓
Question Design
        ↓
Source-Grounded Expected Answer / Rubric
        ↓
Freeze Evaluation Case
        ↓
Run URPP Professor
        ↓
L1 Engineering Evaluation
        ↓
L2 Source / Mathematical Evaluation
        ↓
Failure Classification
        ↓
Version-to-Version Comparison

---

# 2. Build Many Question–Answer Pairs From the Source

For important learning material, do not evaluate URPP using only one
or two example questions.

Create a broad question bank directly from the material.

Questions should cover several kinds of knowledge.

## 2.1 Direct factual retrieval

Examples:

- What method does the paper call X?
- What is the definition of Y?
- What page introduces Z?
- What parameters index this lookup table?

Purpose:

Test whether URPP retrieves and reports explicit source information.

---

## 2.2 Equation transcription

Examples:

- Write equation (15) completely.
- Preserve the numerator and denominator of equation (7).
- Write every branch of equation (16).
- What is the summation domain?

Purpose:

Test exact mathematical structure.

Important:

The expected equation should be established independently from the
original source rather than copied from a previous Professor response.

---

## 2.3 Variable-definition questions

Examples:

- What does D_pl represent?
- What do z+ and z- represent?
- What is Omega_SBP?
- What is the difference between S_base and Delta_x Delta_y?

Purpose:

Catch answers that reproduce an equation while misidentifying its
symbols.

---

## 2.4 Relationship questions

Examples:

- How are the top and bottom plane heights combined?
- Why is the squared source distance in the denominator?
- How does h_eff combine with S_base?
- How does equation (12) connect to the hLUT?

Purpose:

Test whether the Professor understands relationships across multiple
statements rather than merely copying nearby text.

---

## 2.5 Method-name and attribution questions

Examples:

- What method is equation (15) part of?
- What method is equation (16) part of?
- Which method uses regression?
- Which method uses overlapped distance?

Purpose:

Detect plausible but unsupported renaming of methods.

---

## 2.6 Conceptual explanation questions

Examples:

- Explain the geometric meaning of equation (7).
- Why can effective height be represented as interval overlap?
- Why is the exact 3-D intersection expensive?
- Why is a lookup table useful here?

Purpose:

Evaluate whether generated explanations remain faithful to the
source while becoming pedagogically useful.

---

## 2.7 Comparison questions

Examples:

- Compare equation (15) and equation (16).
- Compare exact intersection volume with the LUT approximation.
- Compare Regression Method with Distance Method.

Purpose:

Require simultaneous use of multiple source statements.

---

## 2.8 Multi-step questions

Examples:

- Starting from the two PL_s planes, explain how the final
  approximate intersection volume is produced.
- Explain the chain from D_pl to hLUT to h_eff to intersection volume.

Purpose:

Test cross-section reasoning without allowing the model to invent
missing steps.

---

## 2.9 Instruction-following questions

Examples:

- Give only the equation.
- Give the equation and define every symbol.
- Explain in Chinese.
- Explain to a beginner.
- Compare two methods and include both complete formulas.

Purpose:

Separate knowledge accuracy from instruction-following ability.

---

## 2.10 Bilingual and paraphrased questions

The same underlying source fact should sometimes be asked in:

- English;
- Chinese;
- mixed Chinese/English technical language;
- alternate natural phrasings.

Examples:

- "请解释公式 (15)"
- "请解释式 (15)"
- "Explain equation (15)"
- "What does Eq. 15 mean?"

Purpose:

Detect retrieval or routing failures caused by wording rather than
knowledge.

---

## 2.11 Follow-up questions

Example conversation:

Student:
What are the important equations in this section?

Student:
把第二个完整写出来。

Purpose:

Test whether conversational context is used correctly without allowing
stale history to override the current question.

---

## 2.12 Unsupported / negative cases

Examples:

- Ask for an equation that is not present.
- Ask for a concept not covered by the selected material.
- Ask for a page that does not exist.
- Ask the source to support a claim it never makes.

Expected behavior:

URPP should abstain or report insufficient source evidence rather than
fabricate an answer.

These negative cases are essential.

---

# 3. Expected Answers Must Be Independently Established

The gold answer must not be generated by the same Professor output
that is being evaluated.

Preferred evidence hierarchy:

1. Original PDF / textbook / lecture material.
2. Human-reviewed source transcription.
3. Version-bound VerifiedEquationRecord or similar reviewed record.
4. Source-grounded evaluation rubric.

Do not create a gold answer by asking URPP:

"What should the correct answer have been?"

and then using that answer as ground truth.

---

# 4. Freeze Cases Before Evaluating the Candidate Model

A benchmark case should be created before seeing the candidate
Professor's answer.

Each case should contain something like:

- case_id;
- question;
- source identity;
- source revision;
- source SHA-256;
- required source/page;
- expected answer facts;
- required equation structure if applicable;
- prohibited errors;
- acceptable notation variation;
- evaluation categories.

This prevents changing the standard after seeing the model output.

---

# 5. Keep Development and Holdout Sets Separate

Do not repeatedly tune prompts against every benchmark case.

Maintain at least:

## Development set

Used during implementation.

Failures may directly influence engineering changes.

## Holdout set

Not used while designing the fix.

Used after implementation to see whether the improvement generalizes.

Otherwise URPP may appear to become more accurate while merely becoming
better at a small known list of questions.

---

# 6. Evaluate Multiple Independent Layers

## L0 — Source availability

Did the required evidence actually exist in the authorized material?

## L1 — Engineering / contract

Examples:

- correct source selected;
- JSON valid;
- citations valid;
- output contract satisfied;
- no unintended Session write;
- correct version used.

## L2 — Content fidelity

Examples:

- factual correctness;
- mathematical structure;
- method attribution;
- variable definitions;
- applicability conditions;
- answer completeness;
- unsupported claims.

## L3 — Teaching quality

Examples:

- clarity;
- appropriate level;
- useful explanation order;
- pedagogical completeness;
- unnecessary complexity.

A response may pass one layer and fail another.

For example:

Correct Source ID
+
Valid JSON
+
Wrong equation

means:

L1 PASS
L2 FAIL

---

# 7. Failure Categories

Use stable failure categories so accuracy can be compared across
versions.

Recommended initial categories:

- source_selection
- insufficient_evidence_handling
- formula_structure
- formula_transcription
- math_rendering
- source_extraction_artifact
- variable_definition
- method_attribution
- applicability_condition
- answer_omission
- unsupported_claim
- citation_attribution
- conversation_context
- instruction_following
- language_or_paraphrase_routing
- output_contract

A single case may contain more than one failure category.

---

# 8. Accuracy Should Be Reported by Category

Do not report only:

"87% accurate."

Report at least:

- total evaluated cases;
- L1 pass rate;
- L2 pass rate;
- unsupported-question abstention accuracy;
- equation accuracy;
- variable-definition accuracy;
- explanation accuracy;
- bilingual/paraphrase consistency;
- follow-up accuracy;
- failure counts by category.

This helps determine what subsystem actually needs improvement.

---

# 9. Preserve Failed Outputs

Failed generations are valuable research evidence.

For private evaluation runs, preserve:

- exact question;
- selected sources;
- model/version;
- generation settings;
- raw output when appropriate;
- decoded output;
- validation outcome;
- human review result;
- failure category.

Do not silently regenerate until an answer looks correct and then keep
only the successful answer.

The failure itself is part of the benchmark evidence.

---

# 10. Do Not Leak the Gold Answer Into the Model Input

The evaluation rubric and expected PASS/FAIL result must remain outside
the normal Professor request.

If an experiment intentionally provides reviewed information, such as a
VerifiedEquationRecord, record that as a different experimental
condition.

Example:

Condition A:
original extracted source only.

Condition B:
same source + reviewed equation representation.

That is an intervention and must not be confused with ordinary
evaluation.

---

# 11. Use Papers to Generate Large Benchmarks

For research papers, the default future workflow should be:

Paper
 ↓
Section / page map
 ↓
Important concepts
 ↓
Important equations
 ↓
Definitions
 ↓
Methods
 ↓
Assumptions
 ↓
Algorithm steps
 ↓
Figures / table claims
 ↓
Comparisons
 ↓
Limitations
 ↓
Negative / unsupported questions
 ↓
Paraphrases
 ↓
Bilingual variants
 ↓
Follow-ups
 ↓
Frozen Q/A benchmark

For a significant paper, dozens of evaluation cases are preferable to
a tiny three-question test when practical.

The benchmark should sample different cognitive demands rather than
creating dozens of trivial paraphrases of the same fact.

---

# 12. Current CT Pilot as the First Example

The Ha and Mueller LTRI paper demonstrated why this strategy is useful.

Examples already discovered include:

- equation (7) numerator / denominator fidelity;
- equation (10) relationship between plane-specific heights and h_eff;
- equation (15) Regression Method attribution;
- equation (16) overlapped-distance structure;
- PDF extraction corruption;
- Chinese "式" versus "公式" source-selection behavior;
- answer omission;
- malformed mathematical rendering;
- correct citation with incorrect mathematical explanation.

These cases should become the first seed benchmark for the general
URPP evaluation framework.

---

# 13. Future Automation

A future URPP evaluation system may help propose candidate questions
from a newly imported source.

However:

- generated benchmark questions are not automatically gold;
- generated answers are not automatically correct;
- equations should be independently verified;
- source locations must remain version-bound;
- human review should be available for high-value benchmark cases.

Automation may reduce benchmark authoring cost without removing the
ground-truth boundary.

---

# 14. Standing Rule for Future URPP Development

When a future conversation continues URPP accuracy or Professor
evaluation work:

1. Read this document first.
2. Prefer source-grounded frozen Q/A benchmarks over anecdotal testing.
3. Build multiple question types from the actual learning material.
4. Keep expected answers separate from model inputs.
5. Maintain development and holdout cases.
6. Preserve failures.
7. Report L1 and L2 separately.
8. Compare versions using the same frozen benchmark whenever possible.
9. Do not infer mathematical correctness from citations or valid JSON.
10. Extend the benchmark when a new real failure mode is discovered.

This should remain part of URPP's evaluation methodology even after
the current CT implementation changes.

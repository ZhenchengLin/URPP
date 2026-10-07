# First Full Technical Chapter: Foundation → Student State V0.2

> **Archive status: SOURCE-BASED HISTORICAL RECONSTRUCTION.** This chapter is based on 30 historical file versions in the user-uploaded `early_architecture_source_pack.zip`. The original code can prove *what the design and implementation were at the time*, but cannot by itself prove *why the developer made a change, which error was hit, or how many attempts were made*. Parts without an original failure log are labeled **after-the-fact comparative analysis**, not historical bugs.
>
> **Applicable versions:** `93e3680` → `0dda011` → `f61cd4b` → `2de3b83` → `90b83fa`. These are this chapter's Git history checkpoints; they do not confirm the Implementation 0–13 numbering boundaries. **This chapter did not review the same-named files at the current HEAD `a82b2ad`**; early code semantics must not be taken as current semantics. All code paths below are the versions in the corresponding commits.

## 01 | The original product was not a chatbot

The initial `README.md` and `docs/00_product_spec.md` define URPP as a **persistent learning-control loop** for one student in one active university STEM course: course materials arrive over time, the system maintains learning objectives and traceable learning evidence, chooses the next teaching action from the current state, and follows teaching with formative assessment. The North Star reads: "Given the course requirement and current student evidence, what is the next best teaching action?"

The original goals were twelve items, not twelve finished features: course materials change the Course Model; requirements become Learning Objectives; state claims are evidence-backed and traceable; state can rise, fall, or stay unknown; actions come from a constrained space with reason codes; teaching is followed by assessment; assessment produces Evidence Events; new evidence changes later teaching; uncertainty is exposed; and URPP is compared with simpler baselines. These are **V0 Must Demonstrate** items, not test results of that commit.

The initial `docs/07_evaluation_plan.md` designed four comparison conditions: Generic LLM, Course RAG, URPP Lite (course context + Student State), and Full URPP (Course Model + Objective + Student Evidence + Pedagogical Policy). The document lists metrics such as course grounding, state-sensitive adaptivity, learning gain, and transfer performance; **the source material does not show these comparisons being run in the initial commit**.

### Why the design cannot simply "ask the LLM what to teach"

The design principle this chapter can confirm directly is: **Evidence History is the source of truth, Objective State is a derived estimate; an LLM may propose structured observations but does not directly rewrite Student State.** The original files split Course Model, Learning Objectives, Student State, Pedagogical Policy, and Assessment into separate responsibilities. Most of them were at the design/placeholder stage then; the existence of a directory does not mean a complete teaching loop was running.

`docs/04_course_model.md` deliberately distinguishes RAG, which answers "where is this content discussed", from the Course Model, which answers "what role does this concept play in this course". `docs/08_privacy_safety.md` says the system must not infer unnecessary medical, psychological, IQ, or fixed-learning-style attributes, and plans to let the student view and challenge the system's inferences. These are original product boundaries, not principles added after later research.

**Source evidence:** `93e3680:README.md`; `93e3680:docs/00_product_spec.md`; `93e3680:docs/01_architecture.md`; `93e3680:docs/04_course_model.md`; `93e3680:docs/07_evaluation_plan.md`; `93e3680:docs/08_privacy_safety.md`.

## 02 | What code was actually written at first?

The initial `backend/app/main.py` creates a FastAPI instance and includes the health router; we cannot infer that it already accepted learning answers, used SQLite, or drove a Professor Agent. `backend/app/llm/client.py` contains only an `LLMClient(Protocol)` boundary defining `generate_json(prompt_name, payload)` and `embed(texts)`: **this is an interface, not evidence of a connected model**.

The initial domain models were more complete than the runtime. `LearningObjective` includes `objective_id`, `course_id`, `concept_id`, Bloom's `cognitive_demand`, `knowledge_type`, prerequisite objectives, `source_refs`, `source_type`, `authority`, status, and created/updated times. `EvidenceEvent` already contains student/course/session/objective identity, `outcome`, `correctness` in `[0,1]`, a nullable `assistance_level`, `novelty`, `transfer_distance`, `evidence_strength`, `model_confidence`, and `created_at`. `ObjectiveState` has `state_score`, `confidence`, independent/transfer success counts, and `status_reason`.

Note: **the very first `EvidenceEvent` already allowed `assistance_level=None`**; this field was not invented in 13E. The original `docs/02_learning_objective_evidence_student_state.md` already defined a 0–6 Assistance Ladder and stated explicitly that "Student questions do not automatically mean weakness", "Self-report is weak evidence by default", and "Unknown / insufficient evidence is valid". But a model that allows unknowns is not the same as having implemented the later SQLite provenance or the strict assessment-eligibility pipeline.

The initial CourseMaterial has only identity, type, week, course_date, source, and processing-status fields; the initial `Misconception` is a model with `SUSPECTED/ACTIVE/IMPROVING/RESOLVED/RECURRING`. **A declared model class and a service that actually maintains misconception state are different levels of completion.**

**Source evidence:** `93e3680:backend/app/main.py`; `93e3680:backend/app/llm/client.py`; `93e3680:backend/app/domain/learning/models.py`; `93e3680:backend/app/domain/student/models.py`; `93e3680:backend/app/domain/course/models.py`; `93e3680:docs/02_learning_objective_evidence_student_state.md`.

## 03 | The V0.1 goal: derive a state from Evidence Events

The initial `docs/03_state_update_engine.md` was only 791 bytes. It marked the state engine as **NEXT** and listed open questions, such as how much one independent success should change the state, how to weight assisted successes, how to combine conflicting evidence, and when to stay Unknown. The next historical version, `0dda011:docs/03_state_update_engine.md`, expanded it to a 1,581-line **V0.1 Design Candidate**; this is a design document, not a production implementation.

The core V0.1 invariants were: deterministic, order independent, duplicate safe, evidence traceable, Unknown is allowed, state can rise and fall, and lack of new evidence is not negative evidence. The design separates Performance Evidence that can inform performance inference, context-only evidence (student questions, self-reports, teacher observations), and student disputes used to correct the model. Note especially: **keeping an event ≠ allowing it to change the mastery judgment**.

The V0.1 candidate calculation centers on `evidence_strength ∈ [-1,1]`:

```text
effective_strength_i = evidence_strength_i
                     × model_confidence_i
                     × recency_weight_i
                     × evidence_type_weight_i
positive_mass = Σ max(effective_strength_i, 0)
negative_mass = Σ max(-effective_strength_i, 0)
state_score = positive_mass / (positive_mass + negative_mass)
```

If the total mass is 0, the design requires `state_score=None`. The candidate confidence is an explicit weighted sum of quantity, session diversity, recency, and consistency; leaving UNKNOWN requires at least two eligible pieces of evidence and mass ≥ 0.75; COMPETENT and STRONG add gates for independent completions, multiple sessions, and transfer/retrieval. **These numbers are heuristic parameters of an old design, not mastery probabilities calibrated by educational experiments.**

### An important architectural issue in the initial V0.1 (after-the-fact design analysis)

In the old scheme, signed `evidence_strength`, `model_confidence` about interpreting the result, time decay, evidence count, and whether the student worked independently could easily blend around a single number. Even a high score needed extra gates, which shows that **performance score and sufficiency of evidence are two different questions**. This is not based on a historical error log we found; it is a change of modeling direction visible by directly comparing the two design versions.

**Source evidence:** `93e3680:docs/03_state_update_engine.md` (NEXT); `0dda011:docs/03_state_update_engine.md` (§3, §5–17, §38–40).

## 04 | What did f61cd4b actually change? Not "a rewrite of the whole old document"

This source pack allows an exact comparison of `0dda011:docs/03_state_update_engine.md` and `f61cd4b:docs/03_state_update_engine.md`: the latter **only adds a four-line notice at the top of the file**, saying it is the historical V0.1 Design Candidate, superseded by `03b_state_update_engine_v0.2.md`, and kept for comparison; the rest of the old design text is unchanged. The real new design is in the newly added `docs/03b_state_update_engine_v0.2.md` (1,112 lines).

This matters: a future reader who sees the large page count of `03_state_update_engine.md` must not assume f61cd4b's big changes happened in that old file, and must not treat the V0.1 numbers in the old file as the current V0.2 specification.

| Topic | V0.1 candidate design | V0.2 candidate design |
|---|---|---|
| Aggregate | `state_score` as the ratio of positive/negative mass of signed `evidence_strength` | `performance_estimate` as a weighted average of `correctness` |
| Evidence quality | Aggregates recency, type, and model confidence; confidence computed separately | `diagnostic_weight = assistance × novelty × type × interpretation`; `evidence_support_score` computed separately |
| Time | Old evidence affects aggregate weight through recency | **Recency does not change performance_estimate**; freshness reported separately |
| Minimum evidence | ≥2 eligible events, mass ≥ 0.75 | ≥2 distinct valid assessment items, mass ≥ 0.75 |
| COMPETENT | score/confidence + ≥1 independent success | performance ≥ 0.75 + ≥2 independent successes on **distinct items** + novelty gate |
| STRONG | old score/confidence + independence/sessions + transfer or retrieval | performance ≥ 0.90 + ≥3 independent items + ≥2 sessions + objective-aligned transfer or delayed retrieval |
| Traceability | Principles such as evidence IDs and policy version | Explicit included/excluded IDs, exclusion reasons, scoring policy version, as_of |

**Design rationale must be stated in layers:** the document explicitly says V0.2 separates Performance Estimate, Evidence Support, Performance Stability, and Evidence Freshness, and that self-assessment cannot directly become performance evidence. From an engineering view, this reduces confusions such as "high score = strong evidence" and "a long time = forgotten". **We did not find the discussion or failure logs from before the f61cd4b commit, so we cannot describe the developer's thinking or invent a decision meeting.**

**Source evidence:** `0dda011:docs/03_state_update_engine.md`; `f61cd4b:docs/03_state_update_engine.md`; `f61cd4b:docs/03b_state_update_engine_v0.2.md` (§2, §8–18, §19–23, §26–29).

## 05 | The V0.2 data contract: why a new `state_v02.py` was needed

`EvidenceEventV02` in `2de3b83` uses a Pydantic `BaseModel` with `ConfigDict(frozen=True, extra="forbid")` to block ordinary field mutation and accidental injection of undeclared fields (**this is not a guarantee that the database cannot be tampered with**). On top of the old identity fields, it adds `assessment_item_id`, `response_group_id`, `objective_alignment`, `assessment_validity`, `prior_solution_exposure`, and `scoring_policy_version`.

`assessment_item_id` lets the system know whether two records come from the same question; `response_group_id` marks the same related response across different question numbers; `objective_alignment` prevents a memorized-definition score from counting as evidence for a problem-solving objective; `assessment_validity` keeps invalid items out of the aggregate; `prior_solution_exposure` prevents "did not ask for another hint after seeing the solution" from being read simply as independent work. Both `assistance_level=None` and `prior_solution_exposure=None` keep the condition unknown and must not default to 0/False in interpretation.

`ObjectiveStateV02` no longer exposes the old `state_score`/`confidence` fields. It explicitly separates `performance_estimate`, `evidence_support_score`, `evidence_support`, `performance_stability`, and `evidence_freshness`, and keeps `included_evidence_ids`, `excluded_evidence_ids`, `exclusion_reasons`, `policy_version`, `scoring_policy_version`, and `as_of`. This structure is an **explainable derived snapshot**, not the raw fact table.

The two time fields `EvidenceEventV02.created_at` and `ObjectiveStateV02.as_of` have timezone-aware validators; the estimator later also rejects future events with `created_at > as_of`. **This shows time semantics were written into the design and code early, but the later CLI post-commit timestamp bug must not be described as having happened at this point.**

Compared with `2de3b83`, the schema in `90b83fa` adds `retrieval_delay_hours: float | None`, which must be non-negative; `None` means the delay has not been established. Without an explicit delay, an ordinary retrieval cannot automatically count as delayed retrieval.

**Source evidence:** `2de3b83:backend/app/domain/learning/state_v02.py` (`EvidenceEventV02`, `ObjectiveStateV02`); `90b83fa:backend/app/domain/learning/state_v02.py` (`retrieval_delay_hours`).

## 06 | Eligibility is event-level filtering, not Student State itself

`2de3b83:backend/app/services/student_model/eligibility_v02.py` defines a frozen `EvidenceDecision(eligible, reason, diagnostic_weight)` and `evaluate_evidence(event, policy)`. The order of checks is below; **the order decides which `reason` is returned first when several problems exist at once**:

```text
EvidenceEventV02
  → Evidence Type must be a performance type
  → objective_alignment == DIRECT
  → assessment_validity == VALID
  → outcome != neutral and correctness present
  → assistance_level != None
  → assessment_item_id present
  → model_confidence ≥ policy.min_model_confidence
  → compute diagnostic_weight
  → weight > 0 ? ELIGIBLE : EXCLUDED
```

The candidate weight is `assistance_weight × novelty_weight × evidence_type_weight × model_confidence`, clipped to `[0,1]`. For example, with known `assistance_level=2`, `novelty=similar`, `problem_attempt`, and `model_confidence=1.0`, a single candidate weight is `0.60×0.75×1.00×1.00=0.45`. This is **an example of computing a weight, not a real student score**.

Important semantics: `assistance_level=None` returns `assistance_level_unknown`; `assistance_level=2` is not "of no teaching value": if other conditions are met it can still enter the **performance estimate**, but it does not count as an independent success. `assistance_level=6` has weight 0 and returns `zero_diagnostic_weight`. **The early code could not verify external help conditions: a recorded `0` is a model field value and must not be advertised to users as proof of supervision.**

With `prior_solution_exposure=True`, eligibility caps the novelty weight at the "repeated" level rather than simply discarding the event; in the State Estimator, the independent-success condition explicitly requires `prior_solution_exposure is False`. These are two different rules: **performance information may be cautiously kept, without promoting it to independent completion.**

### Implementation revision: rejecting contradictory Outcome and Correctness

Comparing `eligibility_v02.py` in `2de3b83` and `90b83fa` exactly: the latter adds an `inconsistent_outcome_correctness` check, e.g. `outcome="failure"` with `correctness=1.0`, `success` with `correctness!=1.0`, or `neutral` with a numeric score. Otherwise the same record could be a failure by label and a success by number, and be counted as positive evidence. **There is a confirmable code revision and new regression test here; the current ZIP does not contain a terminal log of a failure at the time, so it can only be called a "confirmed protective revision", not invented as "a production bug that caused a wrong mastery conclusion".**

**Source evidence:** `2de3b83:backend/app/services/student_model/eligibility_v02.py`; `90b83fa:backend/app/services/student_model/eligibility_v02.py`; `backend/tests/test_evidence_policy_v02.py` in the same two commits.

## 07 | Policy is a versioned engineering parameter, not an educational-science fact

`StatePolicyV02` is a frozen dataclass whose defaults include `min_model_confidence=0.65`, `minimum_evidence_mass=0.75`, `minimum_distinct_items=2`, `competent_threshold=0.75`, `strong_threshold=0.90`, `competent_independent_successes=2`, `strong_independent_successes=3`, `strong_minimum_sessions=2`, `max_session_evidence_mass=1.5`, and `stale_after_days=21`.

`90b83fa` adds `min_retrieval_delay_hours=24.0`. Writing this parameter into the Policy means eligibility for delayed retrieval is not decided by an invisible ad-hoc constant inside a function. **0.65, 1.5, 21 days, and 24 hours are all provisional engineering policies declared in the original documents; the website must not describe them as experimentally validated universal learning thresholds.**

One follow-up audit point: `StatePolicyV02` is a frozen dataclass, but in this historical implementation the `estimate_objective_state` entry point explicitly validates `as_of` and `max_session_evidence_mass>0` and does not show a unified initialization check of the logical relationships among all thresholds. This is an **after-the-fact code-review issue**, not a known historical failure.

**Source evidence:** `2de3b83:backend/app/services/student_model/policy_v02.py`; `90b83fa:backend/app/services/student_model/policy_v02.py`.

## 08 | Walking through what `estimate_objective_state()` actually does

This is the real early implementation in `90b83fa:backend/app/services/student_model/state_update_v02.py`. It does not call an LLM or access the database directly; it receives already-built `EvidenceEventV02[]` and produces an `ObjectiveStateV02` for a given student, course, objective, and `as_of`. The order below matches the 13 `STEP`s in the historical source file exactly.

**STEP 0 | Validate time and Policy.** `as_of` must have a timezone and `max_session_evidence_mass` must be positive. The timezone is not a display preference; it makes time ordering and future-event checks consistent.

**STEP 1 | Validate scope and deduplicate by evidence_id.** Each event's student/course/objective must match the request, and `created_at` must not be later than `as_of`. An identical event with the same `evidence_id` may repeat but adds no evidence; the same ID with different content raises `ValueError` rather than silently picking one version.

**STEP 2 | Eligibility.** `evaluate_evidence` is called on each event in the deterministic order `created_at UTC + evidence_id`. Ineligible events keep their `exclusion_reasons`; eligible events are grouped by `(session_id, assessment_item_id)`. **Exclusion means excluded from the state calculation, not deleted from the raw Evidence History.**

**STEP 3 | Control correlated evidence.** For the same session+item, the earliest eligible attempt is chosen; later events on the same item are marked `correlated_repeat_in_session`. Then events with the same `response_group_id` in the same session are deduplicated and marked `correlated_response_group_in_session`; the same response group in different sessions is not merged across sessions by this rule. This policy limits the weight of repetition within one session; it does not prove that two records from different sessions are truly independent in the real world.

**STEP 4 | Session cap.** Candidate weights are summed per session; if a session exceeds `max_session_evidence_mass=1.5`, all its selected events are scaled down proportionally. This keeps many low-difference items in one session from accumulating unlimited aggregate mass. Only the scaled weights go into the next step.

**STEP 5 | Performance estimate.** The actual calculation is `sum(weight_i × correctness_i) / sum(weight_i)` using `math.fsum`; with zero total mass it is `None`. **correctness is the score on an item, not a probability of mastery; performance_estimate is a performance estimate under the original policy, not a scientifically calibrated probability of student ability.**

**STEP 6 | Diversity and independent success.** Distinct items and sessions are counted; the independent-success helper requires success, correctness ≈ 1, assistance_level == 0, and `prior_solution_exposure is False`. Note that *independent* here is a code-metadata definition; the historical function cannot verify that there really was no outside help.

**STEP 7 | Transfer / retrieval.** A successful transfer requires `EvidenceType.TRANSFER_ATTEMPT`, the independent-success condition, and `novelty="novel"`. A delayed retrieval requires the independent-success condition plus `retrieval_delay_hours >= policy.min_retrieval_delay_hours`. An ordinary retrieval without a delay field or with too short a delay does not satisfy the Strong gate.

**STEP 8 | State gates.** If the mass is zero, distinct items < 2, or mass < 0.75, the state is UNKNOWN. Otherwise estimate < 0.40 means EMERGING and estimate < 0.75 means DEVELOPING; higher performance still needs independent items/novelty to reach COMPETENT, and STRONG also needs three distinct independent items across two sessions plus a matching transfer or delayed retrieval. A high score that fails the independent-success conditions can stay at DEVELOPING.

**STEP 9 | Evidence support.** `support_score = min(mass/3,1) × min(distinct_items/3,1)`; when UNKNOWN, support is INSUFFICIENT; otherwise engineering thresholds classify it as LIMITED, MODERATE, or SUBSTANTIAL. It is not another vaguely defined "student ability score".

**STEP 10 | Performance stability.** Fewer than two eligible scores → INSUFFICIENT_DATA; a gap of ≥ 0.50 between the highest and lowest correctness → MIXED; otherwise CONSISTENT. "Stable" here is a discrete judgment from limited evidence, not proof of retention over time.

**STEP 11 | Freshness.** Based on the date of the most recent eligible assessment with assistance 0 and prior exposure False, the function checks whether it is more than 21 days old; the passage of time changes only freshness, not performance_estimate or state directly. The last "independent assessment" counted here need not be a success and still depends on stored event metadata; it cannot be equated with an externally certified independent attempt.

**STEP 12 | Scoring version check.** If the aggregated events contain more than one `scoring_policy_version`, a `ValueError` is raised and an explicit migration is required. Different scoring rules cannot be silently blended into one comparable score.

**STEP 13 | Build a traceable state.** The output contains the current state, performance, support, stability, freshness, mass and counts, included/excluded evidence IDs, reason codes, policy/scoring version, and as_of. No new data collection, user authorization, or LLM judgment happens in this pure estimation function.

```text
EvidenceEvent[]
  → validate scope and as_of
  → deduplicate by evidence_id
  → event-level eligibility / reason codes
  → same item & response-group correlation controls
  → per-session weight cap
  → weighted performance estimate
  → independent / transfer / retrieval counts
  → minimum evidence & higher-state gates
  → support / stability / freshness
  → ObjectiveStateV02 + provenance
```

**Source evidence:** `90b83fa:backend/app/services/student_model/state_update_v02.py` (`estimate_objective_state`, `_independent_success`, `_time_key`).

## 09 | Three numeric examples: why "answered correctly" does not mean "COMPETENT"

These are **explanatory cases constructed by hand from the historical rules, not run records**, and not real student data. Assume items are directly aligned with the objective, valid, model_confidence=1, distinct item IDs, no prior exposure, novelty=novel unless noted, and no other constraints.

**A: Only one independent new item answered correctly.** The event's weight=1 and weighted correctness=1, so performance_estimate=1; but distinct items=1 < 2, so the result is `UNKNOWN`. This does not say the student "doesn't know it"; it says there is not enough evidence.

**B: Two independent new items answered correctly.** In the same session, the raw weight is 1+1=2; the session cap of 1.5 scales each to 0.75; mass=1.5, performance_estimate=1, two distinct items, two independent successes, novelty gate passed, so the result is `COMPETENT`. Since Strong requires at least three independent items and two sessions, it is not STRONG.

**C: Five correct answers on different new items in five different sessions, each after a Level 2 hint.** Each weight=0.60, mass=3, performance_estimate=1, distinct items=5, but the number of independent successes is 0, so the result is `DEVELOPING`. **This shows that in early V0.2, known assisted successes can inform the performance estimate when other conditions hold, but cannot replace independent successes; this differs from the later case where `assistance_level=None` is excluded entirely.**

## 10 | What do the existing historical tests actually prove?

`2de3b83:backend/tests/test_evidence_policy_v02.py` contains nine well-defined `test_` functions covering an independent new item, assistance lowering the weight, a full walkthrough with weight 0, self-report, misalignment, low interpretation confidence, missing assessment ID, solution exposure, and an invalid assessment.

The same-named test file in `90b83fa` adds three more: contradictory outcome/correctness is excluded; a valid failure is still kept as negative performance; a legitimate partial result still counts. The historical `test_state_update_v02.py` has another 20 `test_` functions covering no evidence, self-report, a single success, COMPETENT/STRONG, delayed retrieval, assisted success, repeats on the same item, conflicting duplicate IDs, input order, passage of time, a real failure lowering the state, cross-student data, future data, solution exposure, response groups, and contradictory evidence.

**These 9+3+20 are test-function counts that can be read statically from this source pack, not results of running pytest in the current sandbox or your latest repository.** No full test total is claimed for any historical commit unless the original terminal output is found. The existence of `test_...` proves expected behavior was written as code assertions; whether each historical version passed at the time must be confirmed from that checkpoint's actual test output.

### "Fixes" with code-change evidence but no failure log yet

| Observation | Basis for confirmation | What it can be written as | What it must not be written as |
|---|---|---|---|
| Added Outcome/Correctness consistency check | Diff between the two historical eligibility files + matching new tests | "The implementation added an eligibility check against self-contradictory records" | "A production misjudgment once happened and polluted student state" |
| Added retrieval_delay_hours and the ≥24h rule | Schema, Policy, Estimator, and delayed-retrieval tests | "The implementation separated ordinary retrieval from retrieval with an explicit delay" | "A reproduced delay-timing failure occurred during development" |
| Moved from signed strength to weighted correctness | Old and new design documents | "A confirmed change in architecture/model specification" | "The previous production model failed, forcing the team to rebuild" |

## 11 | After-the-fact code review: verify further next round, do not rewrite as historical bugs

The following are boundaries and discussion points of the uploaded **early historical code**; they must not be declared current system defects without checking against the latest HEAD and original bug logs:

1. `_independent_success` decides from event metadata `assistance_level==0` and `prior_solution_exposure is False`; where those fields came from, and whether the user had outside help, are outside what this pure estimation function verifies.
2. Repeats on the same item are merged by `(session_id, assessment_item_id)`; attempts on the same item in different sessions are not fully treated as the same prior exposure by this rule, so later work should check whether downstream components add further limits.
3. Response-group correlation is likewise limited to a session; data in different sessions sharing a group ID is not deduplicated at this step, and the tests explicitly cover this design.
4. `Pydantic frozen=True` constrains model assignment; it does not make the persistence layer immutable. Database write protection belongs to a later engineering phase.
5. `EvidenceSupportScore`, `model_confidence`, and `PerformanceEstimate` mean different things; none of them should be presented to users as a calibrated "probability of mastery".

These checks should be compared against HEAD code in this website's later **Architecture Evolution / Current-State Audit**, rather than mixed into early historical debugging cases.

## 12 | Confirmable historical checkpoints and remaining evidence gaps

| Git checkpoint | What this source pack provides directly | What is still missing |
|---|---|---|
| `93e3680` | Product/architecture/course/pedagogy/privacy docs; initial Domain Model, FastAPI entry point, and LLM Protocol | Complete initial run logs, actual course import or teaching demo records |
| `0dda011` | 1,581-line V0.1 State Update design candidate | Discussions before the commit, failed implementation attempts |
| `f61cd4b` | Old document gets only a four-line superseded notice; new 1,112-line V0.2 design | Step-by-step discussion and experiment output behind the change decision |
| `2de3b83` | Schema, Eligibility, Policy, nine test functions | Original pytest output for that commit, uncommitted failed attempts before it |
| `90b83fa` | State Estimator, Schema/Policy/Eligibility revisions, test functions | Original failure logs, number of changes before commit, total test results at the time |

**Website arrangement going forward:** this chapter should be the full technical content for "Foundation / Early Student State", kept separate from the `Implementation 0–13` numbering index until the original roadmap that fixes each implementation boundary is obtained. The next round can continue with Assessment / Evidence Scoring in true commit order, rather than guessing implementation numbers from file names.

## Appendix | How to verify each historical statement in this chapter

From the URPP repository root, use read-only Git commands to view specific versions, for example:

```bash
git show 93e3680:docs/00_product_spec.md
git show 0dda011:docs/03_state_update_engine.md
git show f61cd4b:docs/03b_state_update_engine_v0.2.md
git show 2de3b83:backend/app/services/student_model/eligibility_v02.py
git show 90b83fa:backend/app/services/student_model/state_update_v02.py
git diff 2de3b83 90b83fa -- backend/app/services/student_model/eligibility_v02.py
```

The historical files in the original source pack can also be checked directly from `early_architecture_source_pack.zip`. **This chapter contains no real student data, does not run URPP, does not change evidence rules, and does not infer unverified development incidents.**

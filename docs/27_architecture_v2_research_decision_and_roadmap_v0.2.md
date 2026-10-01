# URPP — Architecture V2 Research Decision & Roadmap Addendum V0.2

**Status:** design proposal, not an implementation or an assertion of clinical/educational efficacy.  
**Project checkpoint:** `a82b2ad` (`design/logical-decision-engine`), 479 backend tests passed in user-supplied local logs.  
**Scope:** local-first, single-student STEM tutor; no real LLM integration, trusted human reviewer authentication, production web frontend, or validated educational outcome dataset is assumed.  
**Milestone constraint:** The original Implementation 14 requirements are not available in the currently reviewed context. This addendum does **not** rename or replace Implementation 14; reconcile against the original roadmap before editing it.

## 1. Decisions and rationale

1. **Two evidence paths, one immutable factual history.** Preserve original assessment attempts and assistance logs. Use them to derive (a) *teaching observations* that support immediate tutoring even when independence is unknown and (b) *mastery-eligible evidence* subject to the existing fail-closed eligibility policy. An observation never bypasses eligibility by being renamed.
2. **Unknown is epistemic.** `UNKNOWN` = insufficient evidence under an explicit policy, **not** a claim that the student lacks the knowledge. A correct response after a reported hint says *the response was correct after the app reported a hint*; it does not prove the student saw/used the hint or learned because of it.
3. **No manufactured independent evidence.** Empty app logs, student self-reports, locally generated reviewer IDs, SHA-256 source fingerprints, or correct answers do not imply `assistance_level=0` or `verified_independent=True`. An app-reported solution should be flagged distinctly from an app-reported hint. A presentation/logging partial failure is an unresolved-visibility event if durable evidence is available, otherwise remain unknown.
4. **Rule-based policy remains an enforceable baseline.** Learned policies, if later justified, only select among permitted candidate teaching actions. Neither the LLM nor the learned policy can directly change original assessment records, eligibility gates, or Student State.
5. **Teaching Harness = execution, traceability, and evaluation boundary, not a model.** Record inputs, chosen action, execution status, content/tool references, subsequent observed responses, and evaluation linkage. Separate observable execution success from learning outcomes.
6. **Canvas is a sourced knowledge input, not automatically a training dataset.** Distinguish course-specific content from pedagogical training material; record access scope, attribution/source locator, version, rights/reuse restrictions, and deletion/revocation behavior. Do not collect other students' identifiable submissions to train the tutor by default.
7. **NeoHorse-1 is a research candidate for routing/trajectory selection/evaluation-update design, not a student-learning validator.** No model post-training or training-data capture is required to complete the next engineering milestones.

## 2. Bounded architecture

```text
AUTHORIZED COURSE MATERIALS          APPEND-ONLY LEARNING HISTORY
        |                                     |
Course Model V2                        Student Attempt + Assessment Item
Teaching Principles                   app-reported help and delivery status
        |                                     |
        +--------> Student Observation View <-+
                          |          \
                          |           +--> Existing mastery-eligible path
                          |                  (unchanged scoring / gates)
                          v
                    Decision Context
                          |
         Existing rule policy + explicit action constraints
                          |
                   Teaching Harness
                          |
                    Professor Agent
                          |
                Student-visible interaction
                          |
        New task / later assessment, with provenance
                          |
             Recomputed observations and state
```

### 2.1 Proposed data contracts (design only; do not add to old tables yet)

**LearningObservationV2**

- `observation_id`, `student_id`, `course_id`, `objective_id`, `session_id`, `assignment_id`, `attempt_id`, `assessment_item_id`, `item_revision`.
- `observed_at`, `recorded_at`, `source_type` (`persisted_attempt`, `application_reported_assistance`, `student_report`, `system_execution_report`), `source_record_ids`, `source_policy_version`.
- `correctness`: `correct | incorrect | unscorable | unknown` (from deterministic rubric only when applicable).
- `assistance`: `app_hint_reported | app_solution_reported | no_app_report | visibility_unresolved` **plus** `external_help: unknown | student_reported_none | student_reported_some` (do not conflate these axes).
- `interpretation`: `observed_response_only | assisted_context_observed | insufficient_context`; no independent/mastery claim.
- `derivation_version` and `derived_from_digest` for replay/diff. Digest is ordinary change detection, not authorization or a privacy guarantee.

**ObjectiveLearningViewV2** is a derived, explanatory **view**, not an additional source of truth:

- `mastery_state_v02`: the existing `ObjectiveStateV02` computed from the existing eligible-evidence path; preserve its current semantics.
- `recent_observations`: source-linked observations; include app-provided hints and correctness, even when the attempt is mastery-ineligible.
- `evidence_gaps`: e.g. `independent_conditions_unknown`, `needs_new_item`, `needs_delayed_check`, `help_delivery_uncertain`.
- `suggested_follow_up`: informational recommendation to the rule policy; never a direct eligibility override.

**TeachingTurnTraceV2** (future Harness): `turn_id`, `decision_context_version`, `course_source_refs`, `objective_id`, `observation_ids`, `policy_id/version`, `allowed_actions`, `selected_action`, `reason_code`, `agent/tool versions`, `execution_status`, `assistance_presentation_event_ids`, `generated_content_digest`, `follow_up_assessment_id`, `outcome_observation_ids`, `evaluation_window`, `evaluation_version`. Do **not** store private chain-of-thought as a required field.

### 2.2 Explicit semantics

| Recorded case | Safe operational interpretation | Eligible mastery path |
|---|---|---|
| Correct answer; app logged hint | Correct numeric response; app reported presenting hint | Existing gate remains unchanged; no independent inference |
| Correct answer; app logged solution | Correct response after app-reported solution availability | No independent inference; request a different assessment item |
| Correct answer; empty assistance log | Correct response; no app report in this log | Unknown external conditions; no independent inference |
| Failed presentation after an attempted hint | Outcome unknown unless concrete delivery status persisted | Do not assert no help |
| Later correct answer on a different item | New observed response with its own conditions | Evaluate separately under existing policy; do not inherit a previous item's assistance label automatically |
| Student reports no outside help | Preserve report and timestamp | Not a verified-independence certificate |

**Crucial causal distinction:** a `hint → correct answer` sequence records temporal order, **not** evidence that the hint caused the correct answer. Evaluation of strategy effects needs prospective assessment design or appropriate controls.

## 3. Bounded research hypotheses

**H1 — observation-aware tutoring:** Allowing the rule policy to see an observational teaching view may reduce unproductive repetitions of the same diagnostic when recorded hints/answers already explain what happened. Check deterministic action sequences under fixed inputs; do not claim improved learning solely from a changed action.

**H2 — supported task vs learned knowledge:** Correctness during assisted practice can diverge from later unassisted performance. Use follow-up *different* items, no-help conditions when reasonably established, and delayed checks, while explicitly preserving uncertainty about outside resources. The PNAS 2025 high-school-math experiment supports distinguishing practice performance from independent tests in its studied population; it does not prescribe a universal URPP threshold.

**H3 — explainable policy baseline:** Before using a small learned policy, log action candidates and outcomes from the frozen rule baseline. Training labels copied from the rule policy only measure imitation, not learning gains. With a single student, observational differences between strategies are strongly confounded by topic, order, item difficulty, and accumulating knowledge; avoid generalized efficacy claims.

**H4 — Harness before fine-tuning:** NeoHorse-1's routing and evaluation→selection→update cycle motivates replayable execution traces and quality filtering. Its benchmarks concern agent/tool/coding/instruction tasks, **not** student knowledge acquisition. Keep model-weight updates out of scope until learning outcomes, consent/data rights, and reproducible evaluation exist.

## 4. Evaluation protocol (proposed; not yet run)

1. Choose one objective with clearly specified prerequisites, validated item rubric, and at least two nonidentical assessment variants; **different-looking questions must test the same intended skill at a comparable level**.
2. Record a pre-assessment. Deliver one strategy under the frozen rule policy. Record immediate performance separately from app assistance reports, and distinguish delivery success from learner attention.
3. Offer a later different assessment to probe application, and a delayed assessment to probe retention; define actual delay and item construction in advance rather than treating a fixed number of days as universally valid.
4. Track operational metrics (action success, trace completeness, help exposure uncertainty, missing observations) separately from learning metrics (new-item performance, retention, help dependence). Never collapse all metrics into an unsupported single 'mastery probability.'
5. For proposed alternatives, freeze item sets, versions, outcome definitions, and comparison windows before analyzing. Evaluate the new policy **against** the existing rule baseline and report missingness/uncertainty; do not infer causal efficacy from a single student's uncontrolled timeline.

### Failure / negative test requirements

- Empty app-help log must not imply independent work.
- App-reported solution must not be silently represented as mere hint.
- Post-commit/recovery time cannot precede submitted attempt time; next decision cannot precede its state snapshot.
- Candidate fingerprint mismatch or unknown source version must fail closed for review; a successful fingerprint check is not an authorization token.
- LLM response or student self-report cannot update the mastery gate directly.
- Replay of identical source records, item versions, and derivation versions yields the same teaching observation view.
- Consent withdrawal/source revocation excludes relevant Canvas materials from future retrieval or training candidates without silently editing historical attempt facts.

## 5. Canvas integration boundary

**Course Knowledge:** approved course pages/modules/files and instructor-authorized objectives and rubrics. Extract `course_id`, `source_kind`, `source_locator`, `source_version`, `retrieved_at`, `access_scope`, `rights_or_reuse_status`, `objective_mapping`, and a content digest. Human review of mappings is required before representing them as authoritative course objectives. Protect hidden solutions and answer keys from student-facing retrieval.

**Teaching Knowledge:** pedagogy materials the user may legitimately use, e.g. feedback and formative-assessment principles from their teacher training. Preserve attribution and scope. These become candidate teaching strategy configurations to test, not unqualified universal truth.

**Training:** distinct opt-in proposal; no default fine-tuning on Canvas course content, confidential instructor resources, or other students' data. API access by itself does not confer model-training rights. Start with read-only ingest of a small user-approved corpus and versioned retrieval.

## 6. Concrete roadmap insertion

| Milestone | Deliverable | Exit condition |
|---|---|---|
| 13E-4C — Design freeze + shadow observation | This architecture addendum plus a **read-only** deterministic observation derivation from persisted SQLite attempt/help records; no new approval path | `UNKNOWN` remains unchanged on the current eligible-evidence path; happy/negative tests validate hint/solution/empty log and repeatable recovery |
| Implementation 14 (original) | **Preserve the original task definition**; reconcile when its roadmap text is provided | The original, not invented, 14 acceptance criteria and all existing backend regressions pass |
| Research-to-spec R1 | Versioned Course/Student/Teaching contracts and source rights metadata | Every inferred field has source and epistemic semantics; migration/shadow-read plan reviewed |
| R2 Teaching Harness | Replayable turn traces and evaluation hooks with no model training | Deterministic test fixtures; executable follow-up protocol; no Agent self-grade promoted to mastery |
| R3 Small Decision Model feasibility | Baseline evaluation, data requirement, feature/label leakage audit | Go/no-go decision supported by measured learning-outcome data, not simply imitation accuracy |
| R4 Canvas pilot | Read-only, authorized, source-versioned subset ingest | Content mapped to objectives; access/rights/deletion and hidden-answer tests passed |
| R5 NeoHorse method transfer | Compare routing/trace-curation mechanisms in offline prototype | Demonstrated extra utility on relevant URPP tasks under fixed baseline before model adoption |

**No implementation has been performed by this document.** Git branch and actual test count must be verified when work begins. Do not touch unrelated `scripts/audit_v4_gate1c_feature_artifact.py`.

## 7. Verified external sources and limits

- Bastani et al. (2025), *Generative AI without guardrails can harm learning*, PNAS. In high-school mathematics, aided practice and subsequent independent testing diverged; this is not a validated URPP effect size or a blanket rule for university STEM. https://doi.org/10.1073/pnas.2422633122
- Dunlosky et al. (2013), *Improving Students' Learning With Effective Learning Techniques*. Practice testing and distributed practice have broad support across studied settings; does not specify a universal URPP spacing cadence. https://doi.org/10.1177/1529100612453266
- Corbett & Anderson (1995), *Knowledge tracing: Modeling the acquisition of procedural knowledge*. Provides a precedent for modeling latent knowledge over repeated exercises, not direct proof a given architecture works for one student's local tutor. https://doi.org/10.1007/BF01099821
- NeoHorse Team et al. (arXiv v1, submitted 8 September 2026), *NeoHorse-1: Towards Recursive Self-Improvement via Agentic Post-Training with Routing Harness*. Agent routing, trace filtering and post-training research; no reported URPP-style student learning outcome benchmark. https://arxiv.org/abs/2609.08183
- Instructure Canvas LMS official API: courses, pages, modules, files and role-specific permissions. Access and reading capability do not establish reuse rights for model training. https://developerdocs.instructure.com/services/canvas/resources/courses ; https://developerdocs.instructure.com/services/canvas/resources/pages ; https://developerdocs.instructure.com/services/canvas/resources/modules ; https://developerdocs.instructure.com/services/canvas/resources/files

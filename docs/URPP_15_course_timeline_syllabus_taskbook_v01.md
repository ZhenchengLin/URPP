# URPP Implementation 15 — Course Timeline and Syllabus Intelligence Taskbook v0.1

**Status:** PROPOSED FREEZE v0.1 — pending owner approval.

## 1. Evidence basis and scope boundary

No explicit `Implementation 15` section was located in `docs/27_architecture_v2_research_decision_and_roadmap_v0.2.md`. This taskbook therefore does not claim to reproduce an unavailable prior task definition. It follows the owner-provided 15A–15E scope and aligns it with repository evidence already present in:

- `docs/04_course_model.md`: the planned Course model explicitly includes `Timeline`, `Concept Dependencies`, `Learning Objectives`, `Assignments`, `Assessments`, and `Current Course State`.
- `docs/09_demo_scenario.md`: the demo begins with syllabus/lecture ingestion and later reasons over prerequisite relationships across dated course activity.
- `docs/02_learning_objective_evidence_student_state.md`, Student Modeling Constitution: evidence history is authoritative, derived state is secondary, and unknown/insufficient evidence is valid.
- `docs/27_architecture_v2_research_decision_and_roadmap_v0.2.md`, sections 1–6: local-first operation, immutable factual history, explicit epistemic unknowns, source-linked derived views, source/version semantics, read-only ingest, and no learned-policy promotion without evidence.

Implementation 15 is course-structure intelligence only. Professor behavior from Implementation 14 remains read-only and unchanged.

## 2. Cross-cutting contracts and rules

All new contracts use explicit `V01` versioning. Source-stated facts and derived/inferred fields must remain distinguishable in both storage and evaluation.

### 2.1 Proposed common v01 contracts

- `CourseDocumentClassificationV01`
- `CourseRequirementFactV01`
- `CourseRequirementInferenceV01`
- `CourseTimelineEventV01`
- `CourseTimelineV01`
- `ObjectiveDependencyEdgeV01`
- `ObjectiveDependencyGraphV01`
- `CurrentCourseStateV01`

Where an existing `CourseSourceRefV01` can identify source evidence, reuse it rather than inventing a parallel locator type.

### 2.2 Mandatory rules

1. Local-first execution.
2. Evaluation must use isolated fixtures or temporary storage and must not write to the user's normal database.
3. No private course text may be committed to the repository.
4. Source-stated facts are authoritative over AI inference.
5. Every inference must be explicitly labelled as inference and include confidence plus basis.
6. `unknown`, `unparsed`, or insufficient evidence are valid states; the system must not manufacture certainty.
7. Professor (Implementation 14) stays read-only. Implementation 15 may produce course intelligence for later consumers but must not change Professor behavior in this milestone.
8. No Planner work from Implementation 16 or 18.
9. No Student History / Student Intelligence work from Implementation 17.
10. No Jev or learned-policy work from Implementation 19.
11. Evaluation follows the 14E pattern: frozen cases, deterministic L1 checks, and no-score L2 review bundles.

## 3. 15A — Document Classification

### 3.1 Goal

Classify an ingested course document without interpreting it as a planning action.

Allowed labels:

`syllabus | schedule | assignment | lecture | other | unknown`

### 3.2 15A sub-tasks

#### 15A-1 — Classification contract

Define `CourseDocumentClassificationV01` with at least:

- `course_id`
- `source_ref`
- `classification`
- `classification_basis`
- `confidence`
- `classifier_version`

`classification=unknown` must remain valid.

**Done when:** schema validation, serialization round-trip, unsupported-label rejection, and explicit unknown behavior are covered by deterministic tests.

#### 15A-2 — Deterministic evidence extraction boundary

Add a bounded classification input view that exposes metadata and only the source portions needed for classification. It must not mutate the source pack or user database.

**Done when:** repeated classification inputs are deterministic for the same source/version and evaluation leaves normal user storage unchanged.

#### 15A-3 — Frozen 15A evaluation

Freeze representative cases for all six labels, including ambiguous material expected to become `unknown`.

**L1:** exact label-contract validity, source-ref validity, allowed-label check, no-write check, deterministic replay.

**L2:** one review bundle per case with candidate classification, evidence references, and blank reviewer verdict fields.

### 3.3 Non-goals

No requirement extraction, timeline generation, objective dependencies, current-state derivation, Professor behavior changes, or planning.

## 4. 15B — Requirement Extraction

### 4.1 Goal

Extract source-stated course requirements while keeping source facts strictly separate from AI inference.

### 4.2 15B sub-tasks

#### 15B-1 — Source-stated requirement contract

Define `CourseRequirementFactV01` with fields such as:

- `requirement_id`
- `course_id`
- `requirement_kind`
- `statement_summary`
- `source_refs`
- `source_status`
- `extraction_version`

The record must represent only what the source states. Absence of evidence must not be converted into a requirement.

#### 15B-2 — Inference contract

Define `CourseRequirementInferenceV01` separately, with:

- `inference_id`
- `course_id`
- `inference_kind`
- `inferred_value`
- `confidence`
- `basis_source_refs`
- `basis_requirement_ids`
- `inference_version`

No inference may be serialized as a `CourseRequirementFactV01`.

#### 15B-3 — Fact/inference separation checks

Add deterministic validation that rejects:

- inferred values without an inference label;
- fact records without source refs;
- inferred records without confidence or basis;
- promotion of an inference to source fact during round-trip.

#### 15B-4 — Frozen 15B evaluation

Freeze cases covering explicit requirements, missing requirements, conflicting source statements, and plausible-but-unstated interpretations.

**L1:** source-link integrity, fact/inference type separation, confidence/basis presence for inference, unknown handling, no-write behavior.

**L2:** review bundles show normalized records and provenance metadata, not private source passages, with reviewer fields blank.

### 4.3 Non-goals

No student-specific interpretation, compliance recommendation, scheduling recommendation, Planner action, or automatic override of source-stated requirements.

## 5. 15C — Course Timeline

### 5.1 Goal

Represent dated course events while treating unknown or unparsed dates as valid states.

### 5.2 15C sub-tasks

#### 15C-1 — Timeline event contract

Define `CourseTimelineEventV01` with at least:

- `event_id`
- `course_id`
- `event_kind`
- `title_summary`
- `date_state`
- `start_at`
- `end_at`
- `source_refs`
- `derivation_kind`
- `confidence`
- `timeline_version`

`date_state` must distinguish at least `parsed`, `unknown`, and `unparsed`.

#### 15C-2 — Timeline collection contract

Define `CourseTimelineV01` as a versioned collection with deterministic ordering rules that do not force unknown dates into false chronology.

#### 15C-3 — Date normalization

Implement bounded parsing for source-stated dates. Preserve the original epistemic result: failed parsing becomes `unparsed`; absent date evidence becomes `unknown`.

#### 15C-4 — Frozen 15C evaluation

Freeze cases with exact dates, ranges, repeated events, ambiguous dates, absent dates, and conflicting source evidence.

**L1:** deterministic date-state classification, ordering invariants, provenance, no invented dates, serialization stability, no-write behavior.

**L2:** review bundles present normalized event metadata and provenance with blank human verdicts.

### 5.3 Non-goals

No reminder scheduling, calendar writes, workload optimization, deadline prioritization, or Planner-generated study schedules.

## 6. 15D — Objective Dependencies

### 6.1 Goal

Represent prerequisite relationships among course learning objectives as an evidence-linked directed acyclic graph.

### 6.2 15D sub-tasks

#### 15D-1 — Dependency-edge contract

Define `ObjectiveDependencyEdgeV01` with at least:

- `prerequisite_objective_id`
- `dependent_objective_id`
- `evidence_kind`
- `source_refs`
- `inference_confidence`
- `basis`
- `edge_version`

Source-stated prerequisite edges and inferred edges must remain distinguishable.

#### 15D-2 — Dependency-graph contract

Define `ObjectiveDependencyGraphV01` with:

- course/objective-set identity;
- versioned edge set;
- deterministic node/edge ordering;
- cycle validation;
- unresolved/unknown dependency state where evidence is insufficient.

#### 15D-3 — DAG validation

Reject self-edges and directed cycles. A rejected cycle must remain visible as validation evidence rather than being silently repaired.

#### 15D-4 — Frozen 15D evaluation

Freeze direct prerequisite, inferred prerequisite, no-evidence, duplicate-edge, self-edge, and cycle cases.

**L1:** edge provenance, source-vs-inference distinction, cycle/self-edge rejection, deterministic replay, unknown preservation, no-write behavior.

**L2:** graph review bundles list edge metadata, basis, and provenance without inventing an authoritative prerequisite relation.

### 6.3 Non-goals

No mastery inference, student weakness diagnosis, teaching-action selection, prerequisite remediation plan, or graph-learned policy.

## 7. 15E — CurrentCourseState

### 7.1 Goal

Produce a derived course snapshot from authoritative course evidence. The snapshot is a view, not a new source of truth.

### 7.2 15E sub-tasks

#### 15E-1 — Snapshot contract

Define `CurrentCourseStateV01` with at least:

- `course_id`
- `as_of`
- `timeline_version`
- `requirement_version`
- `dependency_graph_version`
- `current_or_next_events`
- `active_requirements`
- `relevant_objective_ids`
- `evidence_gaps`
- `state_status`
- `derived_from_digests`
- `derivation_version`

`state_status=unknown` or equivalent must be valid.

#### 15E-2 — Deterministic derivation

Derive the snapshot only from versioned 15A–15D outputs and existing authoritative course evidence. Missing data must produce explicit gaps rather than guessed state.

#### 15E-3 — Replay and source-change behavior

Identical inputs and `as_of` must replay identically. A changed source/version must produce a changed derivation identity rather than silently mutating historical evidence.

#### 15E-4 — Frozen 15E evaluation

Freeze snapshots with complete evidence, partial evidence, unknown dates, conflicting requirements, and unresolved dependencies.

**L1:** deterministic replay, input-version binding, evidence-gap preservation, unknown-state validity, no-write behavior.

**L2:** no-score review bundles show the derived snapshot and provenance metadata with blank reviewer verdicts.

### 7.3 Non-goals

No student state, mastery state, personalized recommendation, teaching policy selection, deadline prioritization, or autonomous planning.

## 8. Evaluation architecture for Implementation 15

Implementation 15 should reuse the evaluation discipline established by 14E without reusing its math-specific semantics.

For each stage 15A–15E:

1. Freeze representative cases before observing candidate outputs.
2. Preserve every run record, including unsupported and harness-error outcomes.
3. Run deterministic L1 checks against contracts, provenance, epistemic states, and invariants.
4. Generate L2 human-review bundles with no numeric semantic score and blank verdict fields.
5. Keep evaluation data outside the repository when it contains private course material.
6. Never write evaluation artifacts into the normal user database.
7. Treat L1 structural success as necessary contract evidence, not as a substitute for semantic human review.

## 9. Proposed execution order

1. **M-15A-FREEZE — Document Classification contracts, fixtures, deterministic L1, and L2 review-bundle skeleton.**
2. M-15B — Requirement fact/inference separation.
3. M-15C — Course timeline and date-state handling.
4. M-15D — Evidence-linked objective dependency DAG.
5. M-15E — Derived `CurrentCourseStateV01`.
6. M-15-CLOSE — integrated frozen evaluation, limitations record, and owner acceptance decision.

The first implementation milestone is **M-15A-FREEZE**. Work should not begin beyond its frozen boundary until the owner approves this proposed taskbook.

## 10. Freeze decision required

Owner approval should confirm or revise:

- the 15A–15E boundaries;
- the proposed v01 contract names;
- whether inferred requirements/dependencies may exist at all in v0.1;
- the exact frozen evaluation corpus policy;
- whether candidate math-fidelity remediation from Implementation 14 blocks or runs in parallel with Implementation 15.

Until that decision, this document remains a proposed freeze and no Implementation 15 production behavior is authorized by this taskbook alone.

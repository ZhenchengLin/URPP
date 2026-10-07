# URPP Engineering Archive · Reply 4 / 10
## Design 01C: From Student Response to Conditional Learning Evidence

**Archive type:** historical source reading + test-contract analysis + clearly labeled after-the-fact engineering inference.  
**Source scope:** the user-uploaded `assessment_history_source_pack.zip`, containing 16 historical source/test/design files from eight Git checkpoints plus `SOURCE_MANIFEST.json`.  
**Important limitation:** the pack contains only the files selected as added/changed at each checkpoint. It does not include the historical versions of every dependency, nor original failing pytest output, discussion records, or deployment logs. So this chapter must not claim that "a bug really fired" unless there is an original failure record.  
**Numbering note:** the files use `Design 01C` / `V0.2`; these are not the numbers of the still-unrecovered full Implementation 0–13 roadmap.

> **One thread:** an Assessment Item defines the question and Rubric in advance → a Student Attempt stores the raw answer and known conditions → Scoring produces an EvidenceEvent → Eligibility / State Estimator decides how that evidence is used. Open-response items must additionally pass Structured Review → Preview → Approval issued after external authorization → signature-verified Finalization. Once a Repository is introduced, an Attempt must be bound to its original Item Revision; an old answer cannot be re-scored with a new Rubric.

---

## 1. Evidence catalogue: eight real historical checkpoints

| Checkpoint prefix | Files visible in this pack | Work directly confirmable from the source | What must not be inferred from it |
|---|---|---|---|
| `4edec7f` | `models_v02.py`, `numeric_scoring_v02.py`, `test_numeric_scoring_v02.py` | Numeric Assessment Contract, deterministic scoring, and test connection to the State Engine | Client authentication; proof that a real student answered independently |
| `0bfa364` | `open_response_models_v02.py`, matching tests | Open-response Rubric, CriterionReview, Review structures | That open responses are auto-scored or Reviews are trustworthy |
| `e6ac6e7` | `open_response_scoring_v02.py`, matching tests | Review consistency validation and score Preview | That a Preview can be written directly as mastery evidence |
| `55bd26b` | `review_approval_v02.py`, matching tests | Binds Review and sources to an HMAC-SHA256 Approval; Evidence produced after verification | That HMAC by itself authenticates a person or proves the Review's math judgment is right |
| `1374ed1` | `assessment_pipeline_v02.py`, matching tests | Internal entry point turning Numeric / approved open responses into Evidence, then into the State Estimator | That this is an HTTP API or a complete production trust boundary |
| `3424920` | `docs/03c_assessment_records_and_authorization.md` | Records the plan for authoritative items, identity authorization, database, and scoring versions | That PostgreSQL, Alembic, or API authorization were deployed |
| `1b8dfdb` | `assessment_records_v02.py`, matching tests | SQLAlchemy persistence of Item Revisions with version-bound Attempts | That database content is tamper-signed or identity authorization is complete |
| `aadd8e3` | `persisted_numeric_pipeline_v02.py`, matching tests | Loads the original item version from the Repository and runs the existing scoring/state chain | That this service supports persisted open-response scoring or verifies independence |

**How to check:** open the local `engineering-archive/evidence/assessment_history_source_pack.zip`; paths inside the ZIP look like `commit-prefix/backend/...` or `commit-prefix/docs/...`. This chapter marks original version locations at the end of paragraphs as `〔commit / file:lines〕`. Test function names can be found in `backend/tests/test_*.py` at the same checkpoint. The page needs no network access.

### 1.1 Why does this order of development matter?

The original Student State design required "update the state only with evidence", but still had to answer where the evidence comes from. This phase splits "the user says they answered 5" into four different objects: the question and its fixed standard (Item/Rubric), the student's submitted text and answering conditions (Attempt), the scored observation record (EvidenceEvent), and the Objective State estimated from a set of evidence. **The four are linked in the data, but none replaces another.**

An `EvidenceEvent` can report `correctness=1.0`, but that does not mean independent work, enough practice, or mastery. A valid score answers only "how did this response score under the Rubric used"; whether it can enter the mastery estimate or satisfy the Independent Success Gate is the job of later rules.

---

## 2. Numeric Assessment Contract: how a question and a raw answer are defined

### 2.1 `NumericRubricV02`

The Rubric is the scoring basis: `expected_value: float`, a non-negative `absolute_tolerance`, and a non-empty `rubric_version`. `expected_value` and `absolute_tolerance` must be finite, rejecting `NaN` and ±infinity. The model is frozen with `extra="forbid"`, reducing the chance of quietly attaching unknown fields when creating a Rubric. The Rubric here is an **absolute-error** condition, not relative error or significant figures. 〔`4edec7f / models_v02.py:24–55`〕

```python
is_correct = (
    abs(answer - item.rubric.expected_value)
    <= item.rubric.absolute_tolerance
)
```

For example, `expected_value=1.0`, `absolute_tolerance=0.02`, and the answer `1.01` passes. `0.02` is the item's own tolerance, not uncertainty about Student Mastery. Subtraction overflow with extreme finite floats and subject-specific significant-figure requirements are **later engineering boundaries**; this pack does not show that such failures happened historically.

### 2.2 `AssessmentItemV02`

An Item contains `assessment_item_id`, `course_id`, `objective_id`, the question `prompt`, `evidence_type`, `rubric`, and `alignment_verified`. Only three Performance Evidence types are valid Item enum values: `PROBLEM_ATTEMPT`, `TRANSFER_ATTEMPT`, and `RETRIEVAL_ATTEMPT`. However, **this checkpoint's Numeric Scoring function only accepts `PROBLEM_ATTEMPT`**; a data structure that allows declaring a type does not mean the matching scoring and assessment policy exists. 〔`4edec7f / models_v02.py:58–102`; `numeric_scoring_v02.py:73–82`〕

`alignment_verified` defaults to `False`. The code comment notes that matching `objective_id` alone does not prove the question really tests that Learning Objective; an external mechanism must confirm this before scoring. The field's existence does not mean such a mechanism was implemented. At this stage `score_numeric_attempt` only checks that it is true, not who set it.

### 2.3 `StudentAttemptV02`

An Attempt stores `response_text` verbatim, plus `attempt_id`, student/course/session/objective/item scope, `source_message_id`, `response_group_id`, and a timezone-aware `submitted_at`. Answering conditions are kept separately as `assistance_level: int | None` (0–6 or unknown), `prior_solution_exposure: bool | None`, and `novelty: repeated | similar | novel | unknown`. **A correct answer cannot imply `assistance_level=0`, and the absence of an App Hint log cannot imply no outside help.** 〔`4edec7f / models_v02.py:104–158`〕

The test helper `make_attempt()` explicitly constructs `assistance_level=0`, `prior_solution_exposure=False`, `novelty="novel"` by hand. These are only **inputs to a controlled test fixture**, not proof that the production system verified independence. Using these fixture fields to prove real student activity would confuse a test assumption with an observed fact. 〔`4edec7f / test_numeric_scoring_v02.py:49–73`〕

### 2.4 Three different kinds of "don't know"

| Level | Example | Correct handling |
|---|---|---|
| Format unknown | `response_text="I need another explanation"` | The Numeric Parser returns `None`; this automatic numeric score is neutral/invalid, not rewritten as a wrong math answer |
| Answering conditions unknown | Answer `5`, `assistance_level=None` | Numeric scoring can compute 1.0 but keeps `None` as is; Eligibility decides separately later |
| Not enough mastery evidence | One qualifying new item answered correctly | The State Estimator may still return `UNKNOWN`, meaning not enough evidence / thresholds unmet, not that the student doesn't know it |

These three levels happen in different functions. **Do not fill in "no help" or "mastered" upstream just to remove an `UNKNOWN`.**

---

## 3. Numeric Scoring: determinism, parsing rules, and evidence generation

### 3.1 `parse_numeric_answer()` is a restricted parser, not a calculator

The code first calls `strip()`, rejects empty strings and strings longer than 64 characters, then uses `NUMERIC_PATTERN.fullmatch(text)` to require that the **whole answer** be one decimal number, with optional sign, fractional part, and `e/E` scientific notation. After `float()` conversion it must also satisfy `math.isfinite(value)`. User input is never executed and `eval()` is not used. 〔`4edec7f / numeric_scoring_v02.py:23–50`〕

Formats the tests accept: `5`, `5.0`, `.5`, `-2.5`, `+5`, `5e0`, `1.25E+2`. Formats the tests reject: empty string, natural language, `2+3`, `5 meters`, `5,000`, `nan`, `inf`, `1e309`, `5 5`. So although `2+3` equals 5 mathematically, it does not follow **this item's single-number input protocol**; it is not "3 points" or "wrong", it means automatic scoring is unavailable. 〔`4edec7f / test_numeric_scoring_v02.py:77–112`〕

**Teaching consequence:** a user typing `2+3` may be writing an expression, and `5 meters` may involve units. Supporting expressions and units in the future needs a separate Parser/Score Policy, not a silent widening of what `numeric-scoring-v0.2` means.

### 3.2 The actual call order of `score_numeric_attempt()`

```text
AssessmentItemV02 + StudentAttemptV02
  → check course_id / objective_id / assessment_item_id
  → check alignment_verified=True
  → accept only ordinary PROBLEM_ATTEMPT
  → call parse_numeric_answer(response_text)
  ├─ unparseable: neutral + correctness=None + assessment_validity=invalid + confidence=0
  └─ parseable: compare absolute error → success/1.0 or failure/0.0
  → build EvidenceEventV02, inheriting the Attempt's assistance / prior-solution / novelty fields
```

**Why compare three IDs first?** If the item is an addition problem for course A, but the Attempt claims to belong to course B or another Learning Objective, evidence for that objective must not be produced just because the number happens to be 5. The code raises `ValueError` on a scope mismatch instead of auto-correcting the objective. 〔`4edec7f / numeric_scoring_v02.py:53–82`〕

**Why `model_confidence=1.0`?** In this restricted Numeric Parser, the value says the submitted text could be parsed unambiguously as one finite number; it is **not the probability that the student has mastered the skill**. The original code comment explicitly warns about this. For unparseable text it is 0.0. 〔`4edec7f / numeric_scoring_v02.py:84–115`〕

**Which fields are not "upgraded" by the scoring function?** `assistance_level`, `prior_solution_exposure`, and `novelty` are copied straight from the Attempt; `created_at` uses the Attempt's `submitted_at`; `scoring_policy_version` is fixed at `numeric-scoring-v0.2`. `evidence_id` is `numeric-v02:{attempt_id}` to create a stable link; it does not mean persistence uniqueness or caller permission was checked here. 〔`4edec7f / numeric_scoring_v02.py:116–138`〕

### 3.3 From one correct answer to an Objective State

The historical tests use a controlled fixture to build one correct numeric piece of evidence, call `estimate_objective_state()`, and assert: the evidence is included, `performance_estimate=1.0`, but `state="unknown"`. A second test builds **independent correct answers on two different items** and asserts `distinct_assessment_count=2`, `independent_success_count=2`, `state="competent"`. This is rule behavior under test conditions; it does not mean a real student can be certified as having mastered something without further checks. 〔`4edec7f / test_numeric_scoring_v02.py:194–237`〕

The full eligibility rules belong to the historical versions of the State Estimator/Eligibility, and this pack does not include those dependency sources again. This chapter does not reverse-engineer all the State Gate constants from one set of tests.

---

## 4. Open Response: why a "score Preview" cannot directly become Evidence

### 4.1 Structured Rubric and Review

Numeric scoring has finite numbers and an executable tolerance; mathematical proofs and concept explanations in open responses have no natural single-value comparison. This checkpoint therefore uses a criterion-based Rubric: each Criterion has a unique ID, an observable description, full-credit guidance, and a weight, and all weights must sum to approximately 1 (source: `isclose(..., abs_tol=1e-9)`; `rel_tol` is not set to zero, see the source and later boundaries). The Rubric version is non-empty and Criterion weights are finite in `(0,1]`. 〔`0bfa364 / open_response_models_v02.py:24–67`〕

Open-response Items default to `SELF_EXPLANATION` and also allow `DEFINITION_RECALL` and `PROBLEM_ATTEMPT`. If `alignment_verified=True`, a non-empty `alignment_reviewer_id` is required; **this is only a field-consistency check, not authentication of the reviewer**. 〔`0bfa364 / open_response_models_v02.py:69–107`〕

`CriterionReviewV02` uses four judgments per Criterion: `met`, `partial`, `not_met`, `unscorable`. When `met` or `partial` is given, structural validation requires a `supporting_quote`; `not_met` needs no quote. `OpenResponseReviewV02` records the Review/Attempt/Item/Rubric/Reviewer IDs, the Criterion list, and a timezone-aware review time. The source file says directly that this model **does not auto-score**, and at this stage quotes were not yet checked against the student's original text. 〔`0bfa364 / open_response_models_v02.py:110–177`〕

### 4.2 Item-by-item validation of the Preview

`preview_open_response_review(item, attempt, review)` checks in order: the Item and Attempt Course/Objective/Item IDs match; the Review points to the same Attempt and Item; the Rubric Version matches; `reviewed_at >= submitted_at`; the item is marked Alignment Verified; the Review has no duplicate Criterion IDs and covers exactly every Criterion in the Rubric. Quotes that earn positive credit must appear **as a literal substring** in `attempt.response_text`. 〔`e6ac6e7 / open_response_scoring_v02.py:42–116`〕

This quote check proves **the text appeared**, not that the quote supports the Review's mathematical judgment. For example, a quote can contain a correct term while the Reviewer still gives a wrong `met`; the function cannot replace semantic judgment or independent re-review. The top of the source file states explicitly that it does not authenticate the Reviewer's identity or semantic judgment, and its output should not be treated as Mastery Evidence. 〔`e6ac6e7 / open_response_scoring_v02.py:1–9, 42–52`〕

### 4.3 The exact scoring algorithm

```python
scores = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
total += rubric_criteria[result.criterion_id].weight * scores[result.judgment]
```

The test's dot-product question has `definition` (weight 0.6, `met`) and `geometry` (weight 0.4, `partial`). Preview score: `0.6×1 + 0.4×0.5 = 0.8`, so `outcome="partial"`, `status="requires_reviewer_confirmation"`. This score is still not approved Evidence, and `partial` is not a statistical conclusion that "the student has mastered 80% of the knowledge". 〔`e6ac6e7 / open_response_scoring_v02.py:102–159`; `test_open_response_scoring_v02.py:117–127`〕

If **any** Criterion is `unscorable`, the function returns `outcome="neutral"`, `correctness=None`, `status="requires_additional_review"`, rather than counting that Criterion as 0 or quietly re-normalizing the remaining Criteria. This preserves the difference between **missing grounds for a score** and **clearly not meeting the standard**. 〔`e6ac6e7 / open_response_scoring_v02.py:108–140`〕

### 4.4 Status is not a string of "approval" words that can be skipped

```text
Student answer
  → Structured Review (content may be wrong, identity may be unauthenticated)
  → Preview (checks record consistency / literal quotes / computes weighted score)
  → requires_reviewer_confirmation
  → external trusted service authenticates and authorizes the Reviewer [not implemented in this module]
  → issue_review_approval() (binds sources and signs)
  → finalize_approved_review() (verifies signature over all sources)
  → EvidenceEventV02
  → downstream Eligibility / Student State
```

Any shortcut that sends a `Preview` straight into the State Estimator bypasses the Review Approval boundary of this historical design. "Having the LLM write approved in the text" cannot replace signature and permission checks.

---

## 5. HMAC Approval: what it guarantees and what it does not

### 5.1 Exactly what the Approval message binds

`_approval_message()` combines the full `model_dump(mode="json")` of the Item, Attempt, and Review with `approved_by`, `approved_at`, `scoring_confidence`, and `approval_policy_version` into sorted, compact JSON bytes. `_sign()` uses `hmac.new(key, message, hashlib.sha256).hexdigest()`; the key must be at least 32 bytes. The Approval model requires a 64-character lowercase hex signature and a timezone-aware approval time. 〔`55bd26b / review_approval_v02.py:44–126`〕

**Engineering meaning:** changing the answer, Criterion Review, Rubric/Prompt, or approval fields afterwards changes the signed message, which normally fails verification under the same key. The tests do cover a forged signature, a changed student answer, a changed Review, and a changed Item Prompt. 〔`55bd26b / test_review_approval_v02.py:172–236, 282–302`〕

### 5.2 Checks before issuing an approval

`issue_review_approval()` first recomputes the Preview; if it is `requires_additional_review`, it refuses to sign. It then checks that the **caller-supplied** `authenticated_reviewer_id` equals `review.reviewer_id`, that the approval time is not earlier than the Review, and that fields are valid, then signs the message. 〔`55bd26b / review_approval_v02.py:128–194`〕

**Do not misread this:** a parameter named `authenticated_reviewer_id` is not automatically trustworthy. The function has no login, role check, or course authorization. The source notes that the backend service calling it **must authenticate and authorize** the Reviewer first. Without that upstream boundary, any caller holding the signing key could sign a Review it constructed itself. A signature proves "an entity holding the key authenticated these bytes", not "a real authorized instructor endorsed this mathematical judgment".

### 5.3 Independent verification at Finalization

`finalize_approved_review()` regenerates the Preview, checks the Review/Approval IDs and approval time, rebuilds the signed message, and compares signatures with `hmac.compare_digest()`; a failure raises an error and only success produces Evidence. The Evidence copies the Attempt's assistance/exposure/novelty and never raises independence on its own. `created_at=approval.approved_at`, **not the original submission time**; the source explicitly notes that a later schema should separate the original answer time from the approval/recording time. 〔`55bd26b / review_approval_v02.py:197–280`〕

The Reviewer-assigned `scoring_confidence` is carried into the Evidence's `model_confidence`; it is not a calibrated Mastery Probability. In the tests, a lower Review Confidence does not automatically establish Student State. 〔`55bd26b / review_approval_v02.py:59–65, 273–279`; `test_review_approval_v02.py:304–...`〕

### 5.4 Four different trust claims

| Claim | Supported at this stage? | Reason |
|---|---|---|
| The signature binds Item/Attempt/Review intact | **Conditionally**: needs a trusted key and the correct call chain | `HMAC-SHA256` covers the full serialized sources |
| The Reviewer is an authorized course instructor | **Cannot be proven by this module** | Authentication and permission come from an external service not implemented in this pack |
| The Review's mathematical judgment is correct | **Cannot be proven** | Neither the quote substring nor the signature checks mathematical meaning |
| The student really answered independently | **Cannot be proven** | `assistance_level` is copied as is, not derived from the signature |

---

## 6. Assessment Pipeline: why it only accepts Assessment Submissions

`AssessmentPipelineV02` is an **internal application service**, not an HTTP endpoint. Its inputs are `NumericSubmissionV02(item, attempt)` or `ApprovedOpenResponseSubmissionV02(item, attempt, review, approval)`; a `verification_key` of at least 32 bytes can be supplied at construction. 〔`1374ed1 / assessment_pipeline_v02.py:1–68`〕

At run time: the Numeric branch calls `score_numeric_attempt`; the open-response branch requires the verification key and calls `finalize_approved_review`; other types raise `TypeError`; the generated Evidence is collected and passed to `estimate_objective_state()`, which returns `ObjectiveStateV02`. 〔`1374ed1 / assessment_pipeline_v02.py:69–140`〕

```text
NumericSubmission ──── score_numeric_attempt ───────┐
                                                     ├─ EvidenceEvent[] → estimate_objective_state → ObjectiveState
ApprovedOpenResponse ── HMAC verification + finalize ┘
```

This entry point **does not accept `EvidenceEventV02` constructed in advance by the caller**. This prevents arbitrary forged Evidence from being treated as a scoring result at this entry point; but the source also admits that the underlying State Update Engine can be called independently by other code, so this restriction covers only the `AssessmentPipelineV02` entry point and must not be described as a global permission mechanism. 〔`1374ed1 / assessment_pipeline_v02.py:46–55`〕

More importantly, the Pipeline assumes that the Numeric Items and Attempts it receives are authoritative records supplied by the caller; **it does not authenticate the caller or read these objects from trusted storage itself**. So between "internal prototype" and "production application" there are still permission, data-source, and persistence boundaries. The tests cover contracts such as a missing verification key, a wrong key, rejected pre-built Evidence, and rejected cross-student scope; these are **preventive tests**, and the pack has no record of a real intrusion or failure incident. 〔`1374ed1 / test_assessment_pipeline_v02.py:172–238`〕

---

## 7. The Design 01C document: what was only a plan?

`3424920/docs/03c_assessment_records_and_authorization.md` explicitly proposes PostgreSQL as the future production database, with SQLAlchemy, Alembic migrations, and the psycopg driver; local Repository tests may use SQLite. It also requires that student identity come from an authenticated backend context, that Rubric Revisions must not be overwritten, that the Reviewer's signing key stay on the server, that approvals and revocations be auditable, and that mixing of different Numeric and Open-Response `scoring_policy_version`s be handled. 〔`3424920 / docs/03c_assessment_records_and_authorization.md:1–89`〕

**Historical accuracy:** the document's "Technical direction" / "Implementation order" does not mean PostgreSQL was deployed, migrations completed, real Reviewers registered, audit/revocation completed, or an Assessment HTTP API published. The later Repository in this pack is an internal SQLAlchemy prototype, and its test fixtures use in-memory SQLite. The website must keep this distinction throughout.

### 7.1 Different Scoring Policies must not be silently combined

Numeric Evidence has `scoring_policy_version="numeric-scoring-v0.2"`; signed open responses have version `open-response-approval-v0.2`. The Design 01C document explicitly requires an explicit compatibility policy before deploying aggregation of mixed versions. Assuming the two are directly comparable just because both put `correctness` in 0–1 does not match the boundary recorded at this stage. 〔`4edec7f / numeric_scoring_v02.py:23`; `55bd26b / review_approval_v02.py:44, 273–279`; `3424920 / docs/03c_assessment_records_and_authorization.md:59–72`〕

---

## 8. Versioned Repository: why old answers must use the old Rubric

### 8.1 Table structure

```text
assessment_items_v02
  primary key = (assessment_item_id, revision)
  item_type = numeric | open_response
  payload = versioned Item JSON

student_attempts_v02
  primary key = attempt_id
  foreign key = (assessment_item_id, item_revision)
                → same composite key in assessment_items_v02
  payload = original Attempt JSON
```

`AssessmentRecordRepositoryV02` takes an external `session_factory` and uses SQLAlchemy. `save_item()` requires the Revision to be a **real positive integer**, rejecting booleans; an existing `(item_id, revision)` cannot be overwritten. `load_item()` restores the correct Pydantic model from the row's `item_type`. 〔`1b8dfdb / assessment_records_v02.py:1–200`〕

`save_attempt(attempt, item_revision)` first loads that Revision, checks course/objective/item identity, rejects a duplicate `attempt_id`, then stores the Attempt JSON and `item_revision` in the same row; `load_attempt(attempt_id)` returns `(StudentAttemptV02, int)`. Note that `item_revision` is a separate trusted link field and does not depend on the student submitting "the latest version". 〔`1b8dfdb / assessment_records_v02.py:202–271`〕

### 8.2 A precise example of the original Rubric version

```text
T0: Item A / revision 1 / expected_value=5
T1: Attempt X / answer="5" / item_revision=1 → saved
T2: Item A / revision 2 / expected_value=7 → added, rev1 not overwritten
T3: restore Attempt X → revision=1 read from the database → scored with expected=5 → correct
```

If T3 wrongly read the latest rev2, the same historical answer `5` would be re-evaluated as wrong, i.e. **drift of the historical grading standard**. The historical tests assert separately that the old Attempt keeps using the old Rubric and that a new Attempt is scored by rev2; they also check that duplicate Item Revisions and duplicate Attempt IDs are rejected. These are **error scenarios the tests guard against**, not real production bugs that this pack proves happened. 〔`1b8dfdb / test_assessment_records_v02.py:93–201`; `aadd8e3 / test_persisted_numeric_pipeline_v02.py:138–184`〕

### 8.3 The exact scope of "cannot be overwritten"

These Repository methods reject repeated API-level writes of an existing Revision / Attempt ID; this pack does not show that the underlying JSON tables have database-level tamper-proof storage, a complete migration chain, role authorization, or audit logs. **A write-once restriction in the API is not permanent immutability of the whole store.** Foreign keys must also be correctly enabled in the target database connection before the database layer can be relied on to enforce them.

---

## 9. Persisted Numeric Pipeline: connecting real historical records to the existing scoring chain

The entry point of `PersistedNumericAssessmentServiceV02(repository)` is `estimate_from_attempt_ids(attempt_ids, student_id, course_id, objective_id, as_of)`. It rejects a single string mistaken for an ID sequence, an empty list, blank IDs, and duplicate Attempt IDs. For each ID it calls `load_attempt()`, checks Student/Course/Objective scope, then loads the Item exactly by the Attempt's stored `item_revision`; only Numeric Items can build a `NumericSubmissionV02`. Finally it reuses `AssessmentPipelineV02` for scoring and state estimation. 〔`aadd8e3 / persisted_numeric_pipeline_v02.py:31–130`〕

```text
List of Attempt IDs
  → Repository.load_attempt(id) → (Attempt, item_revision)
  → check requested student/course/objective
  → Repository.load_item(assessment_item_id, revision=item_revision)
  → require a Numeric AssessmentItem
  → NumericSubmission(item, attempt)
  → AssessmentPipeline.score_numeric_attempt
  → Evidence Eligibility / estimate_objective_state
```

Here `student_id` comes from a function parameter. The function comment explicitly states that a future API must determine student identity and read permission from an authenticated and authorized server-side context. The current scope-equality check prevents an Attempt from **being misused for another request's Student State**, but **it is not authentication**. 〔`aadd8e3 / persisted_numeric_pipeline_v02.py:8–12, 47–61, 92–104`〕

### 9.1 Regression contract: restoring the original scoring context from SQLite

In the historical tests, each test uses an isolated in-memory SQLite database: `Base.metadata.create_all(engine)`, then a Repository, then saving Items/Attempts and calling the Service. The tests at this checkpoint cover: one correct historical Attempt entering state estimation; a Rubric update not changing old answer scores; a new Attempt using the new Revision; two correct answers on new items meeting the fixture conditions supporting `competent`; unknown/empty/duplicate IDs rejected; cross-student scope rejected; and Open-Response Items not being silently scored by the Numeric Pipeline. 〔`aadd8e3 / test_persisted_numeric_pipeline_v02.py:1–...`, see each function in the test file〕

**Why reject duplicate IDs instead of quietly deduplicating?** If the input is a list that should contain two different pieces of evidence but repeats the same Attempt, silent deduplication would hide a data error at the caller; by this service's contract, the input itself should be corrected. Distinguish this from Evidence Deduplication that the State Estimator may do: the two happen at different layers and should not substitute for each other.

---

## 10. Engineering Casebook: real problems, controlled failures, and preventive contracts

**Evidence status:** this ZIP has no original failing pytest console output and no round-by-round debugging chat, so the following are not "eight bugs that really happened at the time". They are **failure scenarios, protective logic, and verification contracts** directly confirmed by code and tests. The website lists them separately as `GUARD-01C-*`; if real failure logs from the time are found later, timeline-based `BUG-*` cases will be added.

| ID / type | What could happen without this protection | Actual protection in the source | Matching visible tests |
|---|---|---|---|
| `GUARD-01C-01` input parsing | `eval('2+3')` executes an expression; units/infinite values wrongly treated as numbers | Regex fullmatch, max length 64, finite float, no eval; unparseable → neutral/invalid | `test_valid_numeric_formats`, `test_invalid_numeric_formats`, `test_unparseable_response_is_not_automatically_incorrect` |
| `GUARD-01C-02` wrong objective/type | A mismatched course or item still recorded against an objective; a Transfer scored as an ordinary problem | Checks Course/Objective/Item, Alignment, ordinary Problem only | `test_mismatched_assessment_identity_is_rejected`, `test_unverified_alignment_is_rejected`, `test_transfer_assessment_is_not_silently_supported` |
| `GUARD-01C-03` Rubric distortion | A Review with missing items, duplicates, the wrong version, or invented quotes still counted | Version/ID/full-coverage checks; positive-credit quotes must appear in the original text | `test_review_must_cover_every_criterion`, `test_duplicate_criterion_reviews_are_rejected`, `test_quote_must_occur_in_student_response` |
| `GUARD-01C-04` unscorable ≠ zero | A Criterion that could not be judged gets counted as `not_met` | Any `unscorable` → requires_additional_review, no weighted settlement | `test_unscorable_criterion_requires_additional_review`, `test_unscorable_review_cannot_be_approved` |
| `GUARD-01C-05` Approval tampering | After review someone changes the answer, Rubric, or Review but reuses the old approval | HMAC binding over all sources and re-verification | `test_forged_signature_is_rejected`, `test_modifying_student_response_invalidates_approval`, `test_approval_is_bound_to_rubric` |
| `GUARD-01C-06` Evidence injection | A caller bypasses Scoring/Approval and pushes pre-built Evidence in | The Pipeline entry point recognizes only the two Submission contracts | `test_preconstructed_evidence_cannot_enter_pipeline` (protects this entry point only) |
| `GUARD-01C-07` regrading history | After the item's Rubric changes, an old Attempt is recomputed under the new standard | `(assessment_item_id, revision)` composite version key + Attempt binding | `test_new_revision_preserves_old_rubric`, `test_historical_attempt_uses_original_rubric` |
| `GUARD-01C-08` wrong person/duplicates/wrong item type | Evidence taken across students, duplicate IDs, open responses entering numeric scoring | Scope check, duplicate rejection, Numeric type check | `test_attempt_cannot_be_used_for_another_student`, `test_duplicate_attempt_ids_are_rejected`, `test_open_response_item_is_not_silently_scored` |

### 10.1 How should such an investigation be recorded as real debugging?

Only after obtaining the matching original failure context should these be filled in: ① the command run and commit; ② the exact exception and where it occurred; ③ the initial hypothesis and counterexample; ④ the objects examined and when; ⑤ the source diff before and after; ⑥ intermediate approaches that failed; ⑦ the new regression test; ⑧ the actual test output and final commit. **A test name can only prove that the code specifies an expectation; it cannot prove that a matching incident happened historically, nor that this chat re-ran all the tests.**

### 10.2 Design debt directly observable in the source pack

All of the following are **after-the-fact analysis / risks to verify**, not historical bug records:

1. **Real authorization missing:** the Review signing function trusts the Reviewer ID passed from upstream; the Persisted Service's Student ID is likewise a function parameter. A trusted backend entry point must guarantee identity and data permissions.
2. **No single authoritative source for Alignment yet:** `alignment_verified` is an Item field and must come from a traceable authoritative review, not arbitrary client input.
3. **The quote check is only textual consistency:** it cannot replace mathematical judgment or quality checks of Rubric judgments.
4. **Scoring version differences:** Numeric and Open Response have different Policy Versions; mixed aggregation needs an explicit compatibility decision.
5. **Different meanings of time:** Numeric Evidence uses submit time; approved open-response Evidence uses approval time. Future time decay, delayed retrieval, or auditing must store answer time and review/recording time separately.
6. **Repository-level no-overwrite ≠ protection against malicious database tampering:** auditing, authorization, migrations, database constraint configuration, and key management are outside what this pack implements.
7. **Test fixtures differ from real observations:** `assistance_level=0` and `prior_solution_exposure=False` are conditions supplied by hand in unit tests, not proof obtained automatically from real URPP answers.

---

## 11. The boundary between Design 01C and later implementations

The main result of this phase is a **testable internal Assessment → Evidence → Student State pipeline**, with a structural rule for open responses that "a Review Preview must not directly become Evidence", and a Repository recovery path for numeric items bound to the historical Rubric.

It should not be written as the same point in time as the later Implementation 13E application Assistance Log, the recoverable teaching CLI, the Numeric Attempt Provenance Snapshot, or the Architecture V2 Learning Observation proposal. Those later capabilities must each be recovered from their own historical commits/original logs.

The real link to Architecture V2 is that the old system's Numeric Scorer **never inferred answer independence in the first place**; it only copied the Attempt's answering conditions. If a future Teaching Harness adds a Learning Observation layer, it can record the fact "the current task was completed after the application reported providing help", but it must not bypass the existing Mastery Eligibility or treat the absence of a Help Log as `assistance_level=0`.

---

## 12. Next material: how to recover the real history of error investigations

This chapter completes a first reconstruction of the eight checkpoints at the **source and test-contract level**. To satisfy "write down how every error in 0–13 was analyzed and solved", the following original evidence is still needed: failing test output with the matching temporary commit/working tree, the real code diff before and after each error, and the investigation conversations and fix logs saved at the time. Repository Git keeps only committed states and cannot automatically restore all uncommitted failed experiments.

The next website chapters should check along the Git timeline whether there were patches/rollbacks/architecture switches between these eight checkpoints, and align these modules with the real call chains in the later Assignment, Session Recovery, and Decision Engine. **01C's internal Pipeline must not be described as the same user interface that the later complete local teaching CLI connected to.**

### Source file list for this chapter

- `4edec7f/backend/app/services/assessment/models_v02.py` and `numeric_scoring_v02.py`; `backend/tests/test_numeric_scoring_v02.py`
- `0bfa364/backend/app/services/assessment/open_response_models_v02.py`; `backend/tests/test_open_response_models_v02.py`
- `e6ac6e7/backend/app/services/assessment/open_response_scoring_v02.py`; `backend/tests/test_open_response_scoring_v02.py`
- `55bd26b/backend/app/services/assessment/review_approval_v02.py`; `backend/tests/test_review_approval_v02.py`
- `1374ed1/backend/app/services/assessment/assessment_pipeline_v02.py`; `backend/tests/test_assessment_pipeline_v02.py`
- `3424920/docs/03c_assessment_records_and_authorization.md`
- `1b8dfdb/backend/app/repositories/assessment_records_v02.py`; `backend/tests/test_assessment_records_v02.py`
- `aadd8e3/backend/app/services/assessment/persisted_numeric_pipeline_v02.py`; `backend/tests/test_persisted_numeric_pipeline_v02.py`

**Source scope:** the files above are selected files from eight historical checkpoints provided by the user, not a complete, independently runnable historical repository. `assessment_history_source_pack.zip` holds the original text of each version; this chapter is an explanation with version locators, and every failure scenario without an incident log is labeled Guard/Test, not a real incident.

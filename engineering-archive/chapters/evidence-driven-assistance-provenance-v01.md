# URPP Engineering Archive · Reply 9 / 10

## Implementation 13E: Evidence-Driven Teaching, Assistance Logging, Local CLI, and Numeric Provenance

> **Historical cross-section**: from `a6e1181` (13E-1) to `a82b2ad` (13E-4B). This chapter covers behavior committed in this cross-section, not a finished implementation of 13E-4C or V2. **Evidence categories**: `SOURCE` = historical source / diff, `TEST` = test definitions in the repository, `DOC` = design documents of the time, `USER LOG` = terminal feedback the user provided earlier in conversation (the original traceback is not in this ZIP), `PROPOSAL` = a plan not yet implemented. Reference marks such as `[S01:L64–157]` can be looked up in the bundled `reply9_source_index.json`, which gives the exact ZIP member, Git commit, SHA-256, and line numbers.

### Four conclusions of this chapter

1. **13E-2B made "a real answer changes the next action" work; it did not make "a real eligible answer raises Mastery" work.** After submitting the answer `5`, the Attempt has `assistance_level=None`, the evidence is excluded as `assistance_level_unknown`, and Student State stays `UNKNOWN`; the automatic decision can switch from `DIAGNOSTIC_ASSESSMENT` to `CONCEPTUAL_REVIEW` based on the exclusion reason. This is workflow adaptation, not a judgment of academic ability. [S01:L158–246] [T03:L684–895] [D21]
2. **An application-reported hint ≠ the student actually saw the hint; an empty log ≠ no outside help.** 13E-3A stores events; 13E-3B writes the event after the application-controlled Presenter returns a strict `True`. But output and the database write cannot form one atomic transaction. [S04:L210–326] [S05:L156–250] [D22] [D23]
3. **The 13E-3C CLI is a local demo that creates a new database each time, not a full client that can reopen the same database.** Within one run it can recover from "Attempt committed, later state estimation failed"; cross-connection recovery of the underlying Session is tested separately. The CLI itself refuses existing files and uses a fixed synthetic arithmetic question and static Agent content. [S06:L145–222] [S06:L306–390] [T06:L256–315] [D24]
4. **13E-4A / 4B only produce a read-only Snapshot and a re-checkable Candidate; they approve no Numeric Evidence.** `source_fingerprint_sha256` is change detection, not a signature, Reviewer Authorization, proof of independent answering, or a privacy guarantee for short answers. [S07:L35–80] [S08:L31–65] [S08:L73–174] [D25] [D26]

---

## 1. Draw the trust and causality boundaries before reading the history

This round of development connects four different kinds of information: **scoring facts** (the answer text and its numeric score under the Rubric), **Evidence Eligibility** (whether the Attempt meets the preconditions for entering the learning-state estimate), **Student State** (a state snapshot built from eligible evidence), and the **Teaching Decision** (the activity scheduled next). Success at one step does not automatically grant the next layer's conclusion. Parsing `5` successfully does not prove independent work; an Agent producing an explanation does not prove learning; selecting an Assessment Action does not guarantee the item passes the delivery gate. [D19] [D21]

The Engine introduced in 13E-1 **reads an existing, authoritative `ObjectiveStateV02`** rather than recomputing Mastery from free text, Agent output, or excluded evidence. Its automatic branches are engineering heuristics, not strategies proven optimal by teaching experiments. Explicit Student Requests still go through the existing `PersonalizedDecisionEngineV01`; Transfer Assessment is removed from the automatic candidate set, and an explicit Transfer request cannot bypass the downstream Delivery Gate either. [S01:L43–157] [D19]

**How to check**: open `reply9_source_index.json`, find `S01` → `archive_path`, open that member in the uploaded `implementation_13e_history_source_pack.zip`, and jump to the marked lines. The source pack has 8 checkpoints, 54 source and diff entries, and a manifest; each entry has a commit and SHA-256. The Reply 8 index uploaded separately in this chat can cross-check sources from the previous Transfer stage, but **it cannot prove that 13E's tests were re-run on your Mac**. [M01] [P01] [P08]

## 2. Eight commits: from "only selecting actions" to "storing evidence without approving it on its own"

| Stage | Commit | Scope added or changed | Boundary addressed / caveats |
|---|---|---|---|
| 13E-1 | `a6e1181` | `evidence_driven_engine_v01.py`; `EVIDENCE_DRIVEN` added to `DecisionSelectionSourceV01` | Deterministic automatic selection over an existing State; not yet connected to teaching execution. [S01] [P01] |
| 13E-2A | `beab3df` | `evidence_driven_turn_wiring_v01.py`; Orchestrator accepts a shared Decision Port | Opt-in wiring, one decision then dispatch to an Agent; the extra pre-call Transfer Guard covers only this Factory. [S02] [P02] |
| 13E-2B | `836bb71` | UNKNOWN + sole-exclusion-reason branch; SQLite integration test | A really submitted invalid piece of evidence can adjust the workflow, but adds no included evidence or Mastery. [S01] [T03] [P03] |
| 13E-3A | `add51d0` | `assessment_assistance_log_v01.py` | Stores application-reported Hints/Solutions per Assignment, without claiming the user saw the content. [S04] [P04] |
| 13E-3B | `6dc1bd4` | `assessment_assistance_presentation_v01.py` | Writes the Log after the Presenter succeeds; "displayed but not recorded" must be returned explicitly as a partial-operation exception. [S05] [P05] |
| 13E-3C | `b8abf71` | Local CLI, subprocess tests, demo docs | Real terminal output + a newly created SQLite demo; not a web/LLM product or a reopen-old-database implementation. [S06] [T06] [P06] |
| 13E-4A | `ccb4a5a` | `numeric_attempt_provenance_snapshot_v01.py` | Assembles read-only review input from completed Assignments/Attempts and the Log, keeping unknowns. [S07] [P07] |
| 13E-4B | `a82b2ad` | `numeric_provenance_review_candidate_v01.py` | Binds a source fingerprint and re-checks it; still pending authorized review and never included in Mastery. [S08] [T08] [P08] |

`13E-4C` is the next research direction: there is no matching commit in this ZIP. List it under "pending decisions"; do not describe it in product descriptions, test coverage, or work reports as an existing Authorized Review system. [D26]

## 3. 13E-1: Evidence-Driven Decision Engine

### 3.1 Why build a new Engine instead of changing the old Controller directly?

Before this, `PersonalizedDecisionEngineV01` could handle explicit Student Requests but had no separate, opt-in "automatic policy that reads the existing Evidence Summary when there is no request". The new `EvidenceDrivenDecisionEngineV01` is instantiated opt-in, and `decide()` still takes a `PersonalizedDecisionContextV01`. When `student_request is not None`, it delegates immediately to the old Request Engine; otherwise it reads the Context's `objective_state`, gets the allowed set from `PedagogicalPolicyV01.allowed_actions(...)`, and removes `TRANSFER_ASSESSMENT`. If the automatically selected action is not in the remaining allowed set, it raises; `model_dump(mode="json")` is compared before and after the decision to confirm the State was not modified. [S01:L43–157] [P01]

This checkpoint also adds `DecisionSelectionSourceV01.EVIDENCE_DRIVEN`, a separate version number, and an explanatory `selection_reason`. This is **provenance for "why the action was selected"**, not a record that "this teaching content was actually sent to the student". The old engine's default instance was not replaced wholesale. [S01:L15–157] [D19]

### 3.2 Rule-by-rule explanation of the automatic policy

| State and included-evidence situation | Default action | What this rule means in the source |
|---|---|---|
| `UNKNOWN`, no included distinct assessment | `DIAGNOSTIC_ASSESSMENT` | No usable evidence, so schedule a diagnostic first; not a judgment that the student is weak. [S01:L203–246] |
| `UNKNOWN`, with included distinct assessments | `INDEPENDENT_PRACTICE` | Get further direct performance; ability is not inferred from the UNKNOWN label. [S01:L240–246] |
| `EMERGING` / `DEVELOPING`, no included distinct assessment | `CONCEPTUAL_REVIEW` | Explain rather than invent a specific misconception. [S01:L248–260] |
| Same, with included evidence but no independent success | `CONCEPTUAL_HINT` | Assisted performance must not be recorded as independent mastery. [S01:L262–270] |
| Same, with an independent success | `INDEPENDENT_PRACTICE` | Gather more evidence. [S01:L272–278] |
| `COMPETENT`, no independent success | `SELF_EXPLANATION` | The State label itself is not treated as proof of independent answering. [S01:L280–289] |
| `COMPETENT`, with an independent success | `INDEPENDENT_PRACTICE` | Keep practicing; Transfer is not inferred as verified. [S01:L290–297] |
| `STRONG`, no independent success | `INDEPENDENT_PRACTICE` | Look for more direct performance. [S01:L299–307] |
| `STRONG`, with an independent success | `SELF_EXPLANATION` | Schedule self-explanation; do not open Transfer Delivery on its own. [S01:L309–315] |

The table describes the source's current rules, not an empirical ranking of which teaching action works better; synthetic-State tests verify the branches but do not prove real students reach all these states through items. [T01] [D19]

### 3.3 The most important counterexample: a student wants to do Transfer

When a student explicitly sends `REQUEST_TRANSFER`, the Engine lets the old Request Engine handle "selecting the action", but real delivery is still decided by the Transfer Delivery Gate. **Selection ≠ delivery.** 13E-2A's new Factory also adds a Guard **before** calling the Assessment Agent; the original independent post-check Gate in the Recoverable Numeric Session still exists. Do not describe these two checks as a single project-wide pre-check: the Factory's Guard only applies to Orchestrators built through it. [S01:L64–97] [S02:L36–89] [D20]

## 4. 13E-2A: wiring the selection into teaching turns without bypassing the Repository

`create_evidence_driven_personalized_turn_v01(professor_agent, assessment_agent)` returns an instance of the existing `PersonalizedTeachingTurnOrchestratorV01` with the new Engine and `_TransferGuardedAssessmentAgentV01` injected. This is **composition / dependency injection**: instead of rewriting the whole Session, it swaps in a decision implementation with the same interface. The Orchestrator decides once per teaching turn and routes the generation request to an Agent by action; it is **not responsible** for reading the authoritative Student State from the database, authenticating the student, or saving answer records. [S02:L68–89] [D20]

The old `PersonalizedNumericSessionTurnAdapterV01` can connect to this new Orchestrator, but it suits only assessment-oriented numeric delivery; Professor Actions such as `CONCEPTUAL_HINT` / `CONCEPTUAL_REVIEW` should call the teaching Orchestrator rather than being wrapped as Numeric Assignments. This boundary is also respected directly in 13E-2B's real SQLite integration test. [D20] [T03:L842–871]

**Guard tests**: `test_explicit_transfer_is_blocked_before_assessment_agent` verifies that the new opt-in Guard does not let the Assessment Agent generate content first; `test_adapter_does_not_misrepresent_professor_action_as_assessment` verifies that an explanation cannot be disguised as delivering a question. These are committed test definitions, not production incidents shown to have happened. [T02]

## 5. 13E-2B: a real answer changes the next Teaching Action, but does not raise Mastery

### 5.1 Code before and after

In 13E-1, UNKNOWN + no included distinct evidence schedules `DIAGNOSTIC_ASSESSMENT` by default. 13E-2B adds an earlier special case: `CONCEPTUAL_REVIEW` is returned only when `included_count == 0`, `distinct_count == 0`, **excluded evidence exists**, and **every one of those exclusion reasons is exactly `assistance_level_unknown`**. If any other exclusion reason is mixed in, the special case does not fire; explicit Student Requests keep their priority. [S01:L195–246] [T01:L427–536] [P03]

### 5.2 Execution trace against real SQLite

`test_real_excluded_assessment_changes_next_evidence_driven_action` does not just hand-build an `UNKNOWN` State: it creates an isolated SQLite file, saves an Item that meets the delivery conditions, starts a real Recoverable Numeric Session, automatically issues a Diagnostic, submits `response_text="5"`, and then **creates a new SQLAlchemy Engine and Repository instance and reopens the SQLite file**. The recovered State satisfies: `state=unknown`, no included evidence, zero independent successes, exactly one excluded item with reason `assistance_level_unknown`. The second turn is executed by the Professor Agent as `CONCEPTUAL_REVIEW`, and the test checks that no new Assignment was created and no Mastery Evidence was faked. [T03:L684–895] [D21]

> **Correct statement**: one really submitted Attempt changes the next turn's *workflow*. **It must not be stated as** "the system raised the student to a higher Mastery through verified independent answering". Scoring correct and Evidence Eligible are two different checks; this example demonstrates a situation where eligible evidence is still zero. [T03:L820–890] [D21]

The "recovery" here really does cross database connections / Repository instances; that is a different level of capability from the fact below that **the CLI itself cannot open an old database**. [T03:L775–812] [S06:L165–189]

## 6. 13E-3A: the Assistance Event Log's data model, write gate, and limits

13E-3A adds the table `assessment_assistance_events_v01`. A `RecordedAssessmentAssistanceV01` stores `event_id`, `assignment_id`, `student_id`, `session_id`, `kind` (only `hint` or `solution`), `content_sha256`, a timezone-aware `occurred_at`, and the fixed `source="application_reported"`. Database constraints restrict `kind` and `source`; the Assignment ID is a foreign key to `numeric_assignments_v01.assignment_id`. **The content is not stored in plain text in the Assistance Event table**, but a SHA-256 fingerprint is not a confidentiality mechanism for low-entropy content. [S04:L46–129] [D22]

`record_application_assistance(...)` looks up the Assignment within a transaction and checks Student/Session scope, Pending status, no completed Attempt, and an event time not earlier than Assigned At, then inserts the record; `list_assistance_for_assignment(...)` verifies scope before reading. The default interface offers no update or delete method, but this Repository API restriction must not be equated with database-level immutability or permission authentication: any caller able to reach this internal method can pass invented content. [S04:L210–326] [S04:L328–389] [D22]

**Why not write `assistance_level=0`?** Because knowing only that the application once reported a Hint/Solution cannot observe whether the student got help outside the device; an empty log cannot prove independent completion either. 13E-3A does not modify `StudentAttemptV02`, Numeric Submission, Evidence Eligibility, or the State Estimator; the real Attempt's assistance and prior-solution fields stay unknown. [D22] [D21]

## 7. 13E-3B: the non-atomic boundary between Presentation and SQLite Logging

### 7.1 Exact execution order

`AssessmentAssistancePresentationServiceV01.present_assistance(...)` first validates the input and the Pending Assignment, then calls the application-provided `presenter.present(...)` **once**; only if it returns **the strict boolean `True`** does it call the Assistance Log Repository; the Repository checks again that the Assignment is still Pending before writing. A Presenter returning `False` / another value or raising produces `AssistancePresentationFailedV01`, and the service writes no event; if the Presenter returns True and the database write then fails, it raises `AssistancePresentationUnloggedV01`. [S05:L156–250]

These two Pending checks are not magic that merges "screen output + SQL INSERT" into one atomic transaction. Between the first check and the log insert, the Assignment may have been completed; or output may succeed while the database fails. In that case the user **may have seen the help while the Log is empty**. Later systems must not conclude "no help" from this, and must not automatically replay the output to pretend to have exactly-once delivery. [S05:L110–154] [S05:L205–250] [D23]

### 7.2 Real implementation vs. test double

13E-3B initially used a test Presenter to verify the contract rather than claiming a browser UI. Only 13E-3C added `TerminalAssistancePresenterV01`, which actually writes `[HINT]` / `[SOLUTION]` and the content to the terminal; it can still only report that the program executed the output, not prove the student watched, understood, or noticed the content. [S06:L113–142] [D23] [D24]

**Guard case, not a production incident**: in a test, `CompletingPresenter` actively submits an answer inside the `present()` callback and then returns True; the second Pending check refuses to write the event, and the test expects `AssistancePresentationUnloggedV01`, an empty Log, and a completed Assignment. This proves a partial-operation failure is **expressed explicitly**; it does not prove a real user ever hit the same race in production. [T05:L748–817]

## 8. 13E-3C: Local Numeric Teaching CLI — what is "real" and what is "demo only"?

### 8.1 A repeatable local operating sequence

The demo creates, in a new database, one synthetic student, one synthetic arithmetic course, and the static question `What is 2 + 3?`, with a Numeric Rubric expecting `5.0` and absolute tolerance `0.0`. It delivers the item through the existing Assessment Repository and Recoverable Session; typing `hint` / `solution` triggers the Terminal Presenter and Log; typing `5` goes through a real Numeric Submission; it then reads the State, counts recorded help, and schedules the next automatic teaching turn. **The Agent text is static, the assessment is synthetic, there is no external LLM, and there is no authorized review of a real student.** [S06:L80–94] [S06:L145–162] [S06:L306–390] [S06:L418–579] [D24]

The test `test_real_cli_hint_answer_and_sqlite_recovery` feeds `hint\n5\n` to a subprocess and confirms the terminal printed the Hint; SQLite has one completed Assignment, one Hint Event, and one Attempt with `response_text="5"`, `assistance_level=None`, `prior_solution_exposure=None`; the next action is `conceptual_review`; included evidence and independent successes are both zero. The no-help path also keeps the two `None` values and does not fake independent answering because the Log is empty. [T06:L79–158] [T06:L203–254]

### 8.2 "Recoverable" does not mean "the CLI can reopen an old database"

`create_new_demo_database(...)` first rejects an existing path and creates the file with `os.O_CREAT | os.O_EXCL` and permission mode `0o600`; `Base.metadata.create_all` runs only on this new demo database. `test_cli_refuses_existing_database_without_modifying_it` explicitly verifies that an old file is not opened or overwritten. Within one process the CLI can recover a submission that was already persisted, and the underlying Recoverable Session can recover across connections, **but this CLI command cannot reopen the file with `--database` to continue the next lesson**. If other chapters of the website say loosely that "the CLI continues the same lesson after restart", they should be corrected against this fact. [S06:L165–222] [T06:L256–284] [D24]

### 8.3 The two timestamp problems: a debugging case with layered sources

**Terminal feedback the user provided earlier (USER LOG; the full original traceback is not in this pack)** describes two stages: first, after submission, the state estimation's `as_of` was earlier than the Repository's commit time; an intermediate fix artificially added one second to the recovery time, after which the next turn's Decision time was earlier than the future State Snapshot. This ZIP contains only the CLI files and tests of the final commit `b8abf71`, **with no intermediate trial versions and no complete logs of the two failures**; so specific traceback line numbers, number of failures, or intermediate changes cannot be treated as Git facts independently checkable from this pack. [S06:L480–556] [D24]

**Code path confirmed by the final source**: `submit_numeric_answer(..., as_of=now_utc())` may persist the Attempt first and then raise `ValueError` with `"State-estimation time precedes submission."`. For this exact error, the CLI calls `resume(as_of=now_utc())` **without resubmitting**; the next turn's Orchestrator uses `requested_at=completed.state.as_of` instead of an independent clock value that might be earlier than the State Snapshot. [S06:L480–511] [S06:L549–557] [D24]

**Root-cause chain (from the final implementation's time relationships and the earlier USER LOG)**: read `as_of=t0` → Repository records the submission at `t1>t0` → the write succeeds but state estimation rejects the old time → recover from the committed result → the next turn's Decision must not be earlier than the State Snapshot it depends on. Setting the snapshot time artificially into the future can let the recovery step pass but may create a second Decision timing conflict. The fix lives in **the local CLI integration**; it cannot be used to claim the Repository has a general cross-service post-commit recovery API. [S06:L487–556] [D24]

**Risks that remain**: the final implementation relies on matching the exception message string to recognize the specific post-commit error; the source leaves an unused `timedelta` import. These are checkable current implementation details, not another failure that happened. For a future product, results should first be typed to distinguish "not committed" from "committed but post-processing failed"; do not copy this CLI's message matching into a web API. [S06:L487–507] [PROPOSAL]

## 9. 13E-4A: read-only Numeric Attempt Provenance Snapshot

Why not reuse the open-response Signed Review Approval directly? It approves a different object — the scoring review of an open response — and cannot automatically cover the question of "what help was used" for a Numeric Attempt; a signing key or a filled-in Reviewer ID is also not real application-level identity authentication. [D25]

`NumericAttemptProvenanceSnapshotServiceV01.build_snapshot(...)` requires the Assignment to be completed, the linked Attempt to really exist, and the Attempt's student/course/objective/session/item IDs to match the Assignment and Item Revision. After reading the stored answer and the existing `assistance_level` and `prior_solution_exposure`, it queries the Assistance Log Repository for the Assignment's application-reported events. The result is a frozen dataclass with `external_assistance_status="unknown"`, `review_status="requires_authorized_review"`, `verified_independence=False`. [S07:L35–80] [S07:L113–243]

**Important data-consistency limitation**: the Assignment/Attempt are read in one Session and the Assistance Events in another Repository call; this is not a single transactional snapshot across both reads. The output is review input, not an authorized review result, and it never writes back to the Attempt, replaces Eligibility, or triggers a Student State update. Interpret `no_application_report` as "no record", never as "independent answering verified". [S07:L204–243] [D25]

Tests include rejecting Pending, matching a completed Attempt with a Hint, an empty Log staying unknown, rejecting mismatched Student/Session scope, and rebuilding the Snapshot after reopening the database; they verify object relationships and limits and are not evidence that a real Reviewer service went live. [T07]

## 10. 13E-4B: a Candidate Fingerprint can detect change, not grant permission

`create_review_candidate_v01(snapshot)` produces a `NumericProvenanceReviewCandidateV01` containing Assignment/Attempt and Student/Session IDs, Hint/Solution report counts, and a source SHA-256 fingerprint; it does not expose the raw Answer field directly, but the hash input still includes `response_text`. The Candidate's defaults hard-code `pending_authorized_review`, `external_assistance_status="unknown"`, `verified_independence=False`, and `accepted_as_mastery_evidence=False`. [S08:L26–65] [S08:L73–174]

The fingerprint builds JSON from fixed fields, sorts Assistance Events by `event_id`, uses `sort_keys=True`, and computes SHA-256. `require_current_candidate(...)` rebuilds the Snapshot and Candidate from the persisted sources and compares them in full; if a database source changed, it raises `ProvenanceSourceChangedV01`. This **only** detects that the Candidate disagrees with the current source records: it is not a signature, gives no guarantee that a database attacker cannot replace both the records and the digest, and concurrent writes after the re-check are not locked by a transaction. [S08:L73–174] [S08:L176–247] [D26]

**Guard case**: after completing an Attempt, a test directly changes an Event's `content_sha256` with privileged SQL and confirms the old Candidate's re-check fails; this is a **test that simulates tampering**, not evidence that the project ever suffered a database attack. Other tests cover: an empty Log does not prove independence, a manually modified Candidate field is rejected, and the re-check is unchanged after reopening SQLite. [T08:L178–337]

For a short answer like `5`, SHA-256 is not anonymization: when the guess space is small, an attacker can try digests of candidate answers; and the source fingerprint also includes other fields. If a real product handles student privacy, it must not claim the fingerprint is a safe anonymous ID just because the Candidate does not display `response_text`. [S08:L73–144] [D26]

## 11. Debugging Casebook: do not mix real feedback with Guard cases

| Record | Evidence level | Trigger and consequence | Currently confirmed handling / limits |
|---|---|---|---|
| C-09-01: estimation time too early after submission | USER LOG + SOURCE | The CLI took `as_of` when calling submit; the Repository's actual commit was later; the answer may already be persisted while the later state estimation errors. | For that specific exception, `resume(now_utc())` reads the committed result, and resubmission is prevented; this ZIP has no original traceback. [S06:L480–511] [D24] |
| C-09-02: intermediate fix used a future time | USER LOG + SOURCE | Earlier terminal feedback says that after adding `+1s` to the recovery time, the next Decision was earlier than the Snapshot; this ZIP does not keep the intermediate patch. | The final implementation uses `requested_at=completed.state.as_of`, which is never earlier than the Snapshot it depends on; the actual number of occurrences cannot be inferred from this. [S06:L549–557] [D24] |
| G-09-01: display succeeded but Log write failed | TEST / GUARD | The test Presenter completes the Assignment during the callback; the Event insert is then rejected. | Raises `AssistancePresentationUnloggedV01`; no automatic replay; an empty Log is not claimed to mean no help. [T05:L748–817] [S05:L233–250] |
| G-09-02: wrong scope, Assignment already completed, invalid input | TEST / GUARD | Wrong student or Session, invalid Kind, asking to display or record help after completion. | Checked both before the Presenter and before the Repository write; see the tests for exact coverage. [T05] [S04:L210–326] [S05:L110–209] |
| G-09-03: inferring independence from no log | TEST / GUARD | Answering `5` in the demo with no help reported. | Both Attempt fields stay `None`; included evidence and independent successes are 0. [T06:L203–254] |
| G-09-04: old database overwritten by the CLI | TEST / GUARD | Starting the local demo with an existing path. | Refuses to start and keeps the original file content; this also shows the CLI cannot be used to resume interaction with an old database. [T06:L256–284] |
| G-09-05: Candidate disagrees with source records | TEST / GUARD | The test artificially changes an Event fingerprint with privileged SQL. | The re-check raises `ProvenanceSourceChangedV01`, which shows only that change is detectable, not that sources cannot be tampered with. [T08:L235–292] |

**Note**: source code, test definitions, and design documents can support "how the code was designed"; this pack has no original `pytest` output for each commit and no complete original logs of the two CLI failures, so this chapter reports no unverified per-stage passed counts and creates no error screenshots or extra production incidents. A `test_...` name means the test case exists; it does not mean I successfully ran the Mac backend tests in the current environment. [M01]

## 12. Architecture decisions: what stays, and what is left for later discussion?

**ADR-09-01 | Separate Learning Evidence from Workflow Signals.** `excluded_evidence_ids` and `exclusion_reasons` can be used to decide "do not repeat the diagnostic just given", but must never rewrite `included_evidence_ids` or the Mastery label because of a successful score. 13E-2B's `CONCEPTUAL_REVIEW` is a temporary workflow choice based on event status, not an interpretation of UNKNOWN as weak learning ability. [S01:L195–246] [D21]

**ADR-09-02 | Make the boundary of what the Presenter promises explicit.** A test callback's True is an application declaration; terminal `print/flush` can only prove the program executed an output attempt, not that the student saw it. The uncertain state "display happened but Log not written" must be kept explicitly and must not be converted into "no help" because the log is empty. A future Browser Presenter should first design confirmation/retry and durable uncertainty semantics before considering automatically adjusting `assistance_level`. [S05:L32–75] [D23] [PROPOSAL]

**ADR-09-03 | The first real integration uses an isolated demo rather than quietly reusing student data.** The CLI's `O_EXCL` and existing-database refusal reduce the risk of mistakes; the cost is that it cannot serve as a production Session Resume UI. To support continuing study in the future, a strategy for opening existing databases, identity/Session access, schema readiness, and lifecycle management must be **designed separately**; do not just delete the `exists()` check as a temporary fix. [S06:L165–222] [D24] [PROPOSAL]

**ADR-09-04 | Snapshot and Candidate are not Approval.** Reading stored facts, comparing SHA-256, and recording a Review Status cannot prove a real student answered independently. The future needs separate Reviewer Authorization, an explicit scope of observable help, handling of invisible outside help, atomic or versioned source snapshots, and audit information for review decisions. Copying the current Transfer Review interface does not let one claim Numeric Provenance is done automatically. [S07] [S08] [D25] [D26] [PROPOSAL]

**ADR-09-05 | Improve the post-commit API rather than copying the CLI's exception-string check.** The current local CLI can recover a committed result for one specific exception; if this is extended to a real client later, it should use structured submission results and explicit idempotent submission IDs, and test "submission succeeded but later processing failed". This is a proposed engineering direction, not a feature implemented in 13E-4B. [S06:L480–511] [PROPOSAL]

**ADR-09-06 | Keep one clear Personal Professor product line.** All verification in this chapter comes from a synthetic arithmetic example; there is no real user behavior, real LLM, browser teaching UI, independent help monitoring, or quantifiable evidence of learning gains. The course, Observation, and long-term learning-state work in Implementation 14 / V2 should be chosen by a clear user experience and a minimal trustworthy data contract, not treated as required student-learning capabilities just because more fingerprints can be added. [D24] [D25] [D26] [PROPOSAL]

## 13. Coverage of this chapter, unfinished items, and the handoff to Reply 10

As of `a82b2ad`, it can be said accurately that there is: an opt-in Evidence-Driven Engine; a SQLite integration test verifying that invalid evidence adjusts the next action; Assignment-scoped application help records; a local synthetic teaching demo in the terminal; a read-only Provenance Snapshot; and a source-bound Review Candidate. It **cannot** be said that there is: a deployed web frontend, a real LLM, a CLI that reuses an old database, a trustworthy mechanism to rule out outside help, an authenticated Numeric Reviewer, automatic conversion of a Candidate into Eligible Evidence, or committed code for 13E-4C. [M01] [D19] [D21] [D24] [D26]

Reply 10 should not copy these files again; it should connect the 0–13 chapters into unified navigation/search and an evidence catalogue, link every historical failure to its direct evidence, and turn the unfinished boundaries of Reviewer, Mastery, Transfer, and Assistance into "Implemented / Tested / Proposal" status cards. If the original tracebacks of the two CLI failures need to be added, they must be imported separately from the real terminal records of the time, not reverse-engineered from the current source. [M01]

---

### Source lookup notes

- This chapter comes with `evidence/reply9_source_index.json`: `aliases` map `S01`–`S08` (final source), `T01`–`T08` (key tests), `D19`–`D26` (design documents), `P01`–`P08` (each Git diff), and `M01` (manifest) to specific members of the source ZIP, with SHA-256, source line counts, and commits. `T03` points specifically to 13E-2B's historical SQLite integration test, `T05` to the Presentation test after 13E-3B, and `T06` to the CLI test.
- **Code facts follow the historical content of this ZIP**; this chapter is not a live audit of your Mac's current working tree, external services, or a real student database. This round only produced website documents and their source index; it did not change the backend, SQLite, or Git history.

# URPP Engineering Archive — Reply 6 / 10

## Persistence · Numeric Assignment · Session Recovery · SQLite Migration

> **Document version**: Archive Chapter V0.1. **Historical source scope**: the user-submitted `persistence_recovery_history_source_pack.zip`, containing 19 resolved historical Git checkpoints, 71 historical source/test entries, and `SOURCE_MANIFEST.json`. **Confirmation status of this chapter**: based on the code, documents, and tests of each specified commit; historical pytest failures not observed in this ZIP are not invented as incidents. **The real timestamp failures** come from the 13E-3C CLI run and fix records the user provided earlier; this source pack has only their final code and success-path tests, so the source and evidence gaps are labeled separately.

**Chapter contents**: ① problem and responsibility boundaries → ② 19 Git history checkpoints → ③ data contracts and constraints → ④ delivery flow → ⑤ atomic submission → ⑥ three recovery paths → ⑦ rebuilding Student State → ⑧ why rules moved down from Python into SQLite → ⑨ two generations of migration → ⑩ readiness and Engine → ⑪ startup and dependency injection → ⑫ the CLI's two real timestamp failures → ⑬ Guard Casebook → ⑭ uncovered boundaries for future maintenance → ⑮ source and test locations.

---

## 01. From "saving answers" to "recovering an unfinished lesson"

The original teaching flow could keep a `pending_assignment` in memory, but once the user closed the program, memory could not answer: was the last question already delivered? Which question, and which Revision of it, should the student answer? Was a given submission saved successfully? After a restart, should the Pending Assignment be recovered first, or a new question created?

There are three entities here that cannot be merged:

| Entity | When created | Lifecycle and responsibility | What it cannot replace |
|---|---|---|---|
| `AssessmentItemV02` + Revision | When the item is stored | Defines a specific historical version of the question text, Objective, and Rubric | It is not evidence that "the question was delivered to the student" |
| `NumericAssignmentRow` | When an Assessment Action is selected and delivery is stored | Fixes the Session, Decision, Item Revision, delivery time, Pending/Completed status | It is not the student's answer, and Pending alone cannot prove the student actually saw the screen |
| `StudentAttemptRow` | When the student submits an answer | Records a server-generated Attempt ID, the linked Item Revision, the response text, and submit time | It cannot by itself show that a legitimate Assignment was delivered earlier |

The third kind of persisted entity is `NumericTeachingSessionRowV01`: it stores `session_id + student_id + course_id + objective_id + started_at`. It records "whose session this is and when it started", and **does not maintain a separate session-progress table that must be updated with every question**. Progress is rebuilt from Assignments and Attempts. This is what the class docs of `numeric_session_records_v01.py` and the actual implementation of `list_assignment_ids()` say, not a new requirement we added after the fact.

The full relationship:

```text
Stored Item (item_id, revision, prompt, rubric)
              │
              │ immutable revision reference
              ▼
Registered Teaching Session ───► Assignment (pending)
  student/course/objective           │
  started_at                         │ student submits text
                                     ▼
                               Attempt INSERT
                                     │ same DB transaction
                                     ▼
                              Assignment UPDATE
                              pending → completed
                                     │
                                     ▼
              Recover session from stored assignments
                                     │
                       stored Item + stored Attempt
                                     ▼
                     Numeric Scoring → Eligibility
                                     ▼
                          Student State Estimator
                                     ▼
                           Next Teaching Decision
```

**Note the exact boundary of "atomicity"**: the Assignment and Attempt share one transaction in `submit_numeric_response()`; Session Registration and later Assignment Issuance are two operations and do not form a single transaction spanning the whole teaching session; scoring, teaching-action selection, terminal display, and the Assistance Log are not in the same transaction either. Describing a whole lesson loosely as "end-to-end atomic" is inaccurate.

**Source anchors**: `numeric_assignment_v01.py` in `b36c7b5`; `numeric_session_records_v01.py` and `recoverable_numeric_session_v01.py` in `cf9ab746`; the final historical snapshots of Assignment / Recoverable Session in `f86f68d7`.

---

## 02. Rebuilding the design evolution by real Git checkpoints

The 19 checkpoints are listed below in the order of the source pack's manifest. Names use the stage labels in the source pack and the matching changes; these labels are not taken as equivalent to the full original Implementation 0–13 roadmap. What the source pack contains for each checkpoint is **the relevant files added or changed at the time**, not a full source snapshot of the whole repository; `final_snapshot_f86f68d7b4/` additionally provides the full code of the main services at that point.

| Order | Commit | Historical checkpoint | Confirmed structural change / where to check |
|---:|---|---|---|
| 01 | `b36c7b5fba` | `assignment_persistence` | Introduces `NumericAssignmentRow`, `issue_assignment()`, `submit_numeric_response()`, and matching Repository tests; first database path for Pending→Completed. |
| 02 | `174f259e7a` | `completed_assignment_state` | Adds `CompletedAssignmentStateServiceV01`; a user-supplied Attempt ID alone cannot skip the check of the Assignment–Attempt link. |
| 03 | `692b6943f4` | `persisted_numeric_loop` | Adds `PersistedNumericTeachingLoopV01`, connecting the in-memory teaching session with database Assignments; `_requires_recovery` prevents continuing with stale memory after a post-commit exception. |
| 04 | `cf9ab746db` | `session_recovery` | Adds persisted Session Identity and `RecoverableNumericSessionServiceV01`, able to read Pending/Completed and State in a new Service instance. |
| 05 | `a562e6711b` | `assignment_invariants` | Introduces a `pending_session_key` unique constraint, a `(session_id,decision_id)` unique constraint, and state-consistency checks; tests concurrent delivery/submission and rollback on failure. |
| 06 | `79e250c760` | `assignment_migration` | Migration tool for old Assignment tables with explicit audit, explicit apply, backup, transactional change, and state-consistency triggers. |
| 07 | `1f50e80483` | `database_readiness` | Adds a read-only readiness check validating tables, schema, foreign keys, and Session/Assignment data relationships. |
| 08 | `85bbb0e392` | `session_registration` | Adds an optional stage to the delivery path that checks for a matching registered session. |
| 09 | `0f32231201` | `strict_session_assignment` | Adds `registered_session_id` and a four-column composite FK (covering Session and Student/Course/Objective), keeping NULL with explicit historical meaning. |
| 10 | `e735c0fbdf` | `registered_session_default` | New deliveries require a registered Session with matching scope by default; tests explicitly cover rejection when the Session is missing. |
| 11 | `cd5c7d4cde` | `foreign_key_readiness` | Introduces a read-only pre-migration FK audit distinguishing pre-09 / post-09-pre-12B / post-12B and historical data that cannot be matched. |
| 12 | `3cbeffabe4` | `foreign_key_migration` | Rebuilds the old Assignment table in full with backup and verification, migrating to the schema with the Registered Session composite FK. |
| 13 | `0bc3250fb7` | `guarded_sqlite_engine` | Opens an existing SQLite DB with `mode=rw`; enables FKs for new SQLAlchemy connections and re-checks them on pool checkout. |
| 14 | `fc91a60a7d` | `sqlite_startup` | The FastAPI lifespan makes the database connection an explicit opt-in, without breaking the original health-only startup. |
| 15 | `f22dbf930d` | `repository_injection` | Adds `NumericRepositoryBundleV01`, binding three Repositories to the same guarded Engine/session factory. |
| 16 | `c24d1dc84d` | `recoverable_session_factory` | The Session Factory gets its dependencies injected from the Startup Bundle and does not privately create another Engine or Repository. |
| 17 | `f05f7e1328` | `legacy_session_registration` | The early Legacy Loop gains persisted Session Registration, still noting the limits of in-memory progress explicitly. |
| 18 | `f86f68d7b4` | `remove_unregistered_issuance` | The normal delivery implementation removes the issuance path without a registered Session; new Assignments set `registered_session_id=session_id`. |
| 19 | `b8abf71993` | `local_numeric_cli` | Synthetic arithmetic CLI: creates a dedicated new DB, real persistence and re-estimation, static teaching content, and shows Assistance Presentation and the recovery chain. |

**Important ordering**: database delivery and submission in 01 came **before** cross-Service recovery in 04; the database-level constraints in 05 came **before** the old-database upgrade tool in 06; the read-only checks in 07 came **before** the stricter FK schema in 09/10/12; the guarded Engine in 13 came **before** its actual application-level injection in 14/15/16. All protections in the final snapshot must not be written back onto the original `b36c7b5`.

---

## 03. The persistence model: why does each field exist?

### 3.1 Assignment identity and historical versions

`NumericAssignmentRow` stores: the `assignment_id` primary key, `decision_id`, `student_id`, `course_id`, `objective_id`, `session_id`, `assessment_item_id`, `item_revision`, `assigned_at_utc`, `status`, `pending_session_key`, `registered_session_id`, and `completed_attempt_id`.

`assessment_item_id` and `item_revision` together form a composite foreign key to the historical item. **Re-scoring should use the Revision bound at delivery time**, not the item's latest version; otherwise, after the Rubric or question text changes, the meaning of earlier student answers would be quietly rewritten. `decision_id` lets a recorded teaching decision be traced to its actual delivery, but a Decision ID alone cannot prove the client really displayed the question.

`assigned_at_utc` is the delivery time stored in the database; `completed_attempt_id` must be empty while Pending and must point to an existing Attempt when Completed. Consistency between `status` and the other fields cannot be maintained by Python `if`s alone, because other operations may bypass the same Python Service.

### 3.2 Why is the Session identity stored separately?

The Session table stores `session_id`, the Student/Course/Objective scope, and `started_at_utc`. Calling `register()` again with the same Session ID returns the existing record without clearing progress if the scope is the same, and is rejected if the scope differs. `list_assignment_ids()` finds Assignments by that scope and sorts them first by `assigned_at_utc` and then by `assignment_id`, so a new process gets a deterministic input order.

The registration API here only checks the Student/Course/Objective **supplied by the caller**; there is no real user identity authentication. A record belonging to some Student ID is a link fact inside the database, not proof of who the submitter is.

### 3.3 SQLite design of the Pending slot

Core field:

```python
# Excerpt: final_snapshot_f86f68d7b4 / numeric_assignment_v01.py
pending_session_key: Mapped[str | None] = mapped_column(
    String(128), unique=True, nullable=True
)
```

Pending records fill in `session_id`; Completed records set it to `NULL`. Under SQLite's UNIQUE semantics here, multiple records may be `NULL`, but **the same non-null Session ID can appear at most once**. So historical Completed Assignments can be kept while guaranteeing at most one Pending Assignment per Session.

| Assignment status | `completed_attempt_id` | `pending_session_key` | Meaning |
|---|---|---|---|
| Pending | NULL | equals `session_id` | Occupies this session's pending-question slot |
| Completed | points to a unique Attempt | NULL | Releases the slot, allowing a new question |
| Pending + an existing Attempt | non-NULL | any | Contradictory status; should be rejected |
| Completed + still holding the Pending slot | non-NULL | non-NULL | Slot not released; should be rejected |

The latest ORM uses a `CheckConstraint` to keep Pending/Completed consistent with the key, and `UniqueConstraint(session_id, decision_id)` stops a session from consuming the same Decision ID twice. **Older databases created earlier do not get these constraints automatically just because the SQLAlchemy Model changed**; that is why the historical migration tools exist.

### 3.4 Registered Session: a four-column constraint, not just the Session ID

The Registered Session composite FK declared in the final ORM checks all of:

```text
Assignment.registered_session_id → Session.session_id
Assignment.student_id           → Session.student_id
Assignment.course_id            → Session.course_id
Assignment.objective_id         → Session.objective_id
```

and a CHECK requires `registered_session_id=session_id` when non-null. The parent Session table must declare a matching four-column UNIQUE key as the FK target. Having `Assignment.session_id` point to an existing Session is not enough: it could reference a Session of another student, course, or Objective. The four-column binding blocks such cross-links at the database layer.

**Historical NULLs are not forbidden directly by the model**: `registered_session_id` is defined as nullable to represent unbound data that older versions may contain. The final new-delivery path fills it in, and Startup Readiness rejects existing databases with unbound Assignments. So "the ORM allows historical NULL" and "the current application allows a database with NULLs to go live" are two different judgments that must not be confused.

**Source anchors**: `numeric_assignment_v01.py` in `a562e67`, `0f32231`, `e735c0f`, `f86f68d`; `numeric_session_records_v01.py`.

---

## 04. Issuing an Assignment: what is actually written?

The final `NumericAssignmentRepositoryV01.issue_assignment(delivery, *, student_id, course_id, objective_id, session_id)` runs in this order:

1. Confirm `delivery` is an `AssessmentDeliveryV01` and the caller-supplied identifiers are non-empty; `selected_action` must be an Assessment Action; the delivery time must be timezone-aware.
2. Using the SQLAlchemy `sessionmaker` shared with the Assessment Repository, enter `with session.begin()`; read `NumericTeachingSessionRowV01`, requiring the Session to be registered with exactly matching Student/Course/Objective.
3. Parse the time from the Session's `started_at_utc` and require `delivery.assigned_at >= session.started_at`.
4. Load the **original historical version** by `(assessment_item_id, item_revision)`; accept only Numeric Items whose own scope matches the Assignment scope; confirm `alignment_verified`; and require the Delivery Prompt to be exactly the Stored Item Prompt.
5. Reject an `assignment_id` that already exists; insert a new Pending Assignment with `pending_session_key=session_id` and `registered_session_id=session_id`; `session.flush()` makes the database constraints run before commit.
6. After the transaction commits successfully, return `StoredNumericAssignmentV01` to the upstream Service.

```text
Decision selects assessment
    → Structured Delivery (item ID + immutable revision + prompt)
    → verify Registered Session & scope & time
    → load historical Item and check stored prompt
    → INSERT pending Assignment
    → flush/check DB uniqueness + FK + CHECK
    → commit
    → return stored assignment
```

**Issuing and "displayed on screen" are not the same fact**: the Repository confirms the record is stored and checks that the Delivery matches the Stored Item. It does not directly observe whether the student saw, understood, or remembered the question. The comment on `PendingNumericDeliveryViewV01` also states explicitly that rebuilding the display does not prove the browser ever showed it.

**Source anchors**: final historical snapshot `numeric_assignment_v01.py::issue_assignment`; `recoverable_numeric_session_v01.py::deliver_numeric_assessment`.

---

## 05. Submitting: why must it be in one transaction?

The business input of `submit_numeric_response(assignment_id, student_id, session_id, response_text)` is the Assignment ID, the internal scope, and the answer text. Course/Objective/Item Revision, Attempt ID, Source Message ID, Response Group, and submit time all come from stored records or are generated server-side. It **does not let the caller overwrite these historical links directly**.

It first loads the Pending Assignment, checks Student/Session scope, rejects an already Completed Assignment, creates an aware `submitted_at` from the Repository Clock, and checks it is not earlier than the Assignment time. Then it builds a `StudentAttemptV02`, explicitly setting:

```python
assistance_level=None
prior_solution_exposure=None
novelty="unknown"
```

This does not mean "the student had no help"; it means "the submission Repository cannot verify the answering conditions". Even if Numeric Scoring computes `correctness=1.0`, these three fields are not changed automatically because the answer is right.

The key transaction that follows:

```python
# Conceptually faithful excerpt of final repository flow
with self._session_factory() as session:
    with session.begin():
        # ① load + validate pending assignment
        # ② session.add(StudentAttemptRow(...))
        session.flush()                 # INSERT Attempt, not COMMIT
        result = session.execute(
            update(NumericAssignmentRow)
            .where(
                NumericAssignmentRow.assignment_id == assignment_id,
                NumericAssignmentRow.status == "pending",
                NumericAssignmentRow.completed_attempt_id.is_(None),
            )
            .values(
                status="completed",
                pending_session_key=None,
                completed_attempt_id=attempt.attempt_id,
            )
        )
        if result.rowcount != 1:
            raise ValueError("Assignment was completed by another submission.")
# only here: transaction may commit both writes
```

**`flush()` is not `commit()`**. `flush()` sends the pending INSERT to the DB and lets this transaction then use the new Attempt ID as an FK target; until the transaction ends, everything can still be rolled back. The conditional UPDATE competes for the right to complete an Assignment that is "still Pending": only if `rowcount == 1` does this Attempt commit successfully together with the completion record.

### Why isn't querying `status == pending` in Python enough?

Two concurrent calls can both read the same Pending status; with only read-then-write, each may believe it can submit. The database's conditional UPDATE, unique constraints, and transactions converge on a verifiable final state. In the SQLite environment of these historical tests, a conflict may show up as an already-completed error, an `IntegrityError`, or `database is locked`; the tests allow these failure forms, **but allow only one Attempt to be stored successfully**. This is not a comprehensive guarantee for PostgreSQL, multi-process deployment, or arbitrary high-concurrency workloads.

### Post-commit exceptions and the boundary of the atomic transaction

Scenario A: the Attempt INSERT flushes successfully but the Assignment UPDATE fails. **The same transaction is rolled back**, and no orphan Attempt should appear. `test_failed_assignment_update_rolls_back_attempt` covers this scenario by artificially injecting an SQL execution error.

Scenario B: both the Attempt INSERT and the Assignment UPDATE commit successfully, and then State Estimation fails. **The database cannot automatically undo committed business facts**; the right move is to recover and re-read, not to submit the same answer again. `test_recovery_after_database_commit_and_state_failure` makes the State Service throw after completion, then creates a new Service and recovers successfully. This is a controlled fault-injection test and should not be written as "the user certainly hit this failure in real use".

**Source anchors**: final `numeric_assignment_v01.py::submit_numeric_response`; `test_numeric_assignment_invariants_v01.py` in `a562e67`; `test_recoverable_numeric_session_v01.py` in `cf9ab746`.

---

## 06. Three recovery paths that must not be described as one

### 6.1 Repository rebuild: historical data is still readable

`test_submission_is_visible_after_repository_restart` reads a previously completed Assignment in a new Repository instance, verifying the database stored the result. This layer proves **records exist independently of old Python objects**, but does not prove the whole teaching session recovered the correct Decision Context.

### 6.2 Legacy Persisted Loop: writes are persisted, but in-memory state remains

`PersistedNumericTeachingLoopV01` maintains `_pending_assignment_id`, `_completed_assignment_ids`, and an in-memory `NumericTeachingSessionV01`. It first lets the in-memory coordinator create a structured question, then calls the Repository to write it to the database; only after a successful save does it set `_pending_assignment_id`. On submission it first has the Repository complete the database commit, then reads `CompletedAssignmentStateServiceV01` and the original in-memory State Engine, and compares the full `model_dump(mode="json")` of both.

Why compare two States? Because in this Legacy Loop there are both a State derived from persisted data and a State maintained by the in-memory coordinator. If they disagree, the next Decision should not just use either one. The class uses `_requires_recovery`: if a Pending Turn was created but the database write failed, or the State update failed after the database commit, it stops using that in-memory session. **This is fail-closed handling, but it does not mean the Legacy Loop itself can restart across processes at any time with full recovery.**

Later, `f05f7e1` added persisted Session Registration so Assignments issued by the Legacy Loop are also linked to a registered Session; this did not automatically turn the in-memory coordinator into a database-authoritative recovery service.

### 6.3 Recoverable Numeric Session: database facts decide current progress

`RecoverableNumericSessionServiceV01` does not infer recovery state from an old instance's `pending_assignment_id`; instead:

```text
resume(as_of)
    → validate aware as_of
    → load registered session, check scope and start time
    → list stored assignment IDs in deterministic order
    → load every assignment + verify scope and assigned_at ≤ as_of
    → classify pending / completed (reject unknown status)
    → reject >1 pending
    → completed? verify assignment→attempt associations and estimate state
    → else: estimate state from empty evidence
    → pending? load original stored item revision and reconstruct prompt
    → return RecoveredNumericSessionV01(state, pending, completed_ids)
```

`start(started_at)` first calls `register()` for the Session and then `resume(as_of=started_at)`; starting again with the same ID and scope does not clear earlier Assignments. `deliver_numeric_assessment()` first recovers, refuses if there is still a Pending, checks for duplicate Decision IDs in the Session, historical Item scope, and Alignment, and requires the Orchestrator to have actually selected an Assessment Action; only then does it form an `AssessmentDeliveryV01` and call the Repository to issue it. `submit_numeric_answer()` first recovers and checks the current Pending ID, writes the answer, and finally calls `resume()` again.

**A limitation that cannot be omitted**: `resume()` reads Session, Assignment, Attempt, and other data in sequence; it is not a "single atomic snapshot" automatically spanning all Repository queries. The source also states that it has no application-layer auth, no HTTP endpoint, and no complete cross-process concurrency guarantee, and that Session Registration and delivery are separate database transactions. These boundaries should be reviewed again if high concurrency or distributed use is added later.

**Source anchors**: `persisted_numeric_session_loop_v01.py` in `692b694`; `recoverable_numeric_session_v01.py` and recovery tests in `cf9ab746`; the Legacy Loop changes in `f05f7e1`.

---

## 07. Rebuilding Student State from Completed Assignments: callers cannot specify evidence directly

`CompletedAssignmentStateServiceV01.estimate_from_completed_assignments(assignment_ids, *, student_id, session_id, course_id, objective_id, as_of)` checks each Assignment as follows:

1. It does not accept a string posing as a sequence of Assignment IDs; it rejects an empty set, duplicate Assignment IDs, and invalid scope/time.
2. It fetches the actual record from the Assignment Repository; checks Student/Session/Course/Objective all match, that the status really is Completed, and that `completed_attempt_id` is not empty.
3. It loads from the Assessment Repository **the Attempt this Assignment actually references** and its historical `item_revision`; the same Attempt cannot be counted for several Assignments.
4. It checks the Attempt's scope, `assessment_item_id`, bound Revision, `response_group_id == 'assignment-' + assignment_id`, and a submit time not earlier than the delivery time.
5. It checks `assignment.assigned_at <= as_of` and `attempt.submitted_at <= as_of`. If the estimate time has not yet reached the moment an event actually happened, future facts cannot be put into a past State.
6. It calls `PersistedNumericAssessmentServiceV02` with the real Attempt IDs; that service loads the original Item Revision for each Attempt and delegates scoring, Eligibility, and state derivation to `AssessmentPipelineV02`.

```text
Caller supplies assignment IDs, not arbitrary Evidence Events
    ↓ verify assignment linkage & time & scope
Stored Attempt IDs
    ↓ load Attempt + its immutable Item Revision
Numeric Submission objects
    ↓ numeric scoring
Evidence Event(s)
    ↓ existing eligibility + student state rules
ObjectiveStateV02
```

**Boundary of the claim**: these checks prove the structured relationship between Assignments and Attempts in the database is as expected; they do not prove the answer was necessarily given in person by the corresponding real student, nor do they authenticate the caller's Student ID. The internal `student_id` parameter in the Repo must in the future still be derived from a verified server session context.

`test_completed_assignment_reaches_state_engine`, `test_tampered_attempt_assignment_link_is_rejected`, `test_tampered_attempt_revision_is_rejected`, and `test_state_estimation_cannot_precede_submission` cover the chain and the key negative scenarios respectively.

**Source anchors**: `completed_assignment_state_v01.py` / tests in `174f259`; final `persisted_numeric_pipeline_v02.py`.

---

## 08. Why constraints gradually moved down into SQLite

In a single-process, single-threaded demo, a Python-level `if pending: raise` looks sufficient; but multiple Repository instances, database reopening, concurrent writes, and later schema migrations all turn "every write is guaranteed to pass through this if" into an assumption that cannot be guaranteed.

The data-layer protections added step by step are:

| Protective condition | Where it lives | What exactly it blocks |
|---|---|---|
| `assignment_id` primary key | Assignment table | Inserting the same ID twice |
| `(assessment_item_id,item_revision)` FK | Assignment table | Pointing to a non-existent item version |
| `completed_attempt_id` FK + UNIQUE | Assignment table | Referencing a non-existent Attempt; one Attempt referenced directly by several Assignments |
| `pending_session_key` UNIQUE + state-consistency CHECK / Trigger | Assignment table | Two Pendings in the same Session at once, or a Completed that does not release the slot |
| `(session_id,decision_id)` UNIQUE | Assignment table | Reusing the same Decision ID within a session |
| Registered Session four-column FK | Assignment + Session tables | An Assignment linked to a non-existent Session or one with inconsistent scope |
| `PRAGMA foreign_keys=ON` | Database connections of the current guarded Engine | SQLite enforcing the declared FKs on that connection |
| Readiness + Migration Audit | Before application startup | Rejecting missing structures, data-link anomalies, and unbound historical rows |

**Two easy misunderstandings**: first, FK definitions existing in an SQLite database file do not mean every connection enforces FKs: `PRAGMA foreign_keys` is a per-connection setting and must actually be enabled. Second, adding CHECKs/FKs to the ORM Model does not automatically change existing database tables; old data must be audited/migrated and verified.

In the source, `test_concurrent_issuance_produces_at_most_one_pending` has two workers try to issue at the same time, allowing the failing side to hit a unique-constraint conflict or an SQLite write-lock conflict; the successful side must have exactly one Pending. `test_concurrent_submission_creates_exactly_one_attempt` requires exactly one Attempt in the end. These are **design-protection verifications**; this source pack has no matching original log of a "production concurrent duplicate-delivery incident".

---

## 09. The first historical SQLite migration: Pending slot and Decision uniqueness

The schema constraints added in `a562e67` apply only to tables created with the new Model; old databases do not yet have `pending_session_key`, the matching UNIQUE, or the new CHECK semantics. `79e250c::migrate_numeric_assignment_v01_sqlite.py` provides a controlled upgrade path.

### 9.1 Two run modes

**The default is a read-only check**: it opens an existing DB with `mode=ro`, runs `PRAGMA quick_check` and FK checks, identifies whether it is the known Legacy Schema or the Current Schema, and checks whether historical rows meet the status and uniqueness requirements. Only **explicit `apply=True`** modifies the database, and it requires a backup file path that does not exist yet.

### 9.2 Upgrade only after confirming the old database

The migration refuses a missing database, a symlink path, an unknown schema, historical duplicate Pendings, duplicate Decisions, existing FK violations, wrong Pending/Completed combinations, or an existing backup path. The application and all other writers must be stopped first. It creates a new backup with the SQLite Backup API, uses `PRAGMA data_version` when acquiring the EXCLUSIVE transaction to check whether the database changed during the backup, and re-validates schema/row counts before upgrading.

Upgrade steps:

```text
Inspect legacy schema + row consistency
    → create NEW verified backup
    → BEGIN EXCLUSIVE / recheck
    → ALTER TABLE: add pending_session_key
    → UPDATE pending rows: pending_session_key = session_id
    → add UNIQUE indexes for pending key and session+decision
    → add INSERT/UPDATE consistency TRIGGERS
    → inspect upgraded schema/rows within transaction
    → COMMIT
    → final verification; retain backup
```

Why do old tables use triggers? The tool's notes and implementation point out that an existing SQLite table cannot directly get a replacement native CHECK through the `ALTER TABLE` path used here. So for **migrated old tables** it installs INSERT/UPDATE triggers to enforce Pending Key consistency, while **newly created tables** keep using the CHECK in the SQLAlchemy Model. The two schemas aim at the same external behavior with not quite the same implementation; the audit tool must recognize both known forms.

If something fails inside the transaction, it runs ROLLBACK; if the final verification fails even after COMMIT, it must not pretend the data was undone automatically; it should stop using the database and keep the backup for investigation.

**Source anchors**: `inspect()`, `_install_consistency_triggers()`, and `migrate()` in `79e250c::migrate_numeric_assignment_v01_sqlite.py`; the duplicate-row, backup, trigger, and read-only tests in `test_numeric_assignment_sqlite_migration_v01.py`.

---

## 10. The second SQLite migration: turning Session scope into a real FK

The first migration strengthened the Pending/Decision constraints, but relying only on the `assignment.session_id` text column and application-side checks could not block all cross-links at the database layer. Hence `registered_session_id` and the Registered Session composite FK.

`audit_numeric_session_fk_migration_v01.py` in `cd5c7d4` identifies the schema stage and checks whether saved Assignments have a matching Session, whether the Student/Course/Objective scope matches, whether times are reasonable, and whether there are legacy unbound records. `migrate_numeric_session_fk_v01_sqlite.py` in `3cbeffa` performs the real upgrade once explicitly requested.

### 10.1 Why isn't the second one a simple ALTER TABLE?

This time the Assignment table must be rebuilt with the full composite FK, CHECK, and UNIQUE definitions. The tool compiles SQLite CREATE TABLE DDL from the current SQLAlchemy Table Model and replaces the shadow table name, rather than maintaining a separate hand-written new schema. It refuses unknown inbound FKs, unknown dependent structures, and existing shadow tables, to avoid unintentionally breaking unrecognized third-party objects during the rebuild.

### 10.2 Transactional rebuild

```text
Read-only audit (pre-09? post-09/pre-12B? post-12B?)
    → if pre-09: require first migration, never silently chain
    → for known post-09/pre-12B: require NEW backup path
    → create SQLite backup + verify known source schema
    → BEGIN EXCLUSIVE + recheck data_version and rows
    → ensure Session 4-column UNIQUE parent key
    → CREATE shadow Assignment table from current ORM DDL
    → copy all source fields + registered_session_id=session_id
    → verify copy/constraints/count
    → DROP old Assignment table / RENAME shadow table
    → verify FK + row preservation in transaction
    → COMMIT
    → run public read-only readiness and migration audit again
```

If an old Assignment points to a non-existent Session, or its scope does not match, the tool does not "guess a Session" or quietly change the Student ID: it refuses to upgrade automatically. `test_orphan_assignment_blocks_upgrade`, `test_scope_mismatch_blocks_upgrade`, `test_inbound_foreign_key_blocks_table_rebuild`, and `test_failed_transaction_restores_source_schema` are the matching reproducible protective tests.

An important version boundary: the first migration tool only addresses the old Pending Key/Decision constraints; the second addresses Session binding and FKs. **Do not run the second script to fix an arbitrary unknown SQLite schema**; it explicitly requires known post-09/pre-12B input, and a backup and stopping all writers should come first. This website is a design archive, not permission to run a migration on a real user database.

---

## 11. Readiness and the connection layer: a correct schema does not mean the runtime path is correct

`check_sqlite_numeric_database(path)` first rejects a missing database and symlinks, then uses an SQLite `mode=ro` read-only connection to check the four required tables (Assessment Item, Attempt, Assignment, Teaching Session); it validates the Assignment schema state, SQLite `quick_check` and `foreign_key_check`, and audits Session scope and times row by row. With the 12B FK evolution, the final snapshot also checks the four-column definition of the Registered Session composite FK and the count of historical unbound records with `registered_session_id IS NULL`; if any are found, it refuses to start the current strict numeric teaching service.

**Readiness is not a database initializer, nor an authenticity check of all historical payloads.** It does not create missing tables, does not automatically upgrade arbitrary old schemas, and cannot authenticate callers.

`create_numeric_sqlite_engine(path)` is another boundary: it first runs Readiness and the FK Migration Audit, requires the known `post-12B` schema, and then opens only an existing file with `mode=rw`. The purpose of `mode=rw` is not to make the database read-only; it is to **allow reading and writing an existing database while forbidding silent creation of a new file if the path disappears**.

```text
Application opts in with existing DB path
    → Readiness + FK Migration Audit
    → create Engine via SQLite URI mode=rw
    → connect event: PRAGMA foreign_keys=ON + verify
    → checkout event: verify pooled connection still has FK enabled
    → give Engine to Repository Bundle
```

The pool-checkout check only guarantees the FK state "when a connection is checked out"; it cannot stop a caller who already holds a connection from later turning the PRAGMA off, nor control other programs' own connections outside the database layer. The source states these limits explicitly. `test_pool_rejects_connection_with_foreign_keys_disabled` and `test_database_is_not_recreated_if_removed_before_connect` cover the two key failure scenarios.

---

## 12. Application startup and Repository injection: actually putting the guarded Engine to use

Just creating a `create_numeric_sqlite_engine()` factory is not enough. If a production Service creates its own unguarded Engine, the connection constraints above cannot cover that Service's writes. Over `fc91a60`, `f22dbf9`, and `c24d1dc`, the history gradually wired the connection checks into the real application construction path.

### 12.1 The FastAPI lifespan keeps the health check available by default

`main.py` uses the `URPP_NUMERIC_SQLITE_DATABASE_PATH` environment variable as an explicit opt-in. When the variable is **absent**, the health-only application startup is kept; when it is **present but empty**, startup is refused; when it holds a non-empty path, the guarded Engine is built and the Engine/Repository Bundle are attached to `app.state`. On lifespan exit, `engine.dispose()` runs and the references in `app.state` are cleared.

This is not "a production student API is live": the code has no database-backed student HTTP routes and no real user auth. The default health-only startup also does not mean the database service is active.

### 12.2 Why do three Repositories share one `sessionmaker`?

`create_numeric_repository_bundle(engine)` first verifies it received an SQLite Engine whose current connection has foreign keys enabled, then creates a single `sessionmaker(bind=engine, expire_on_commit=False)` and builds the Assessment, Assignment, and Teaching Session Repositories from it. The Assignment Repository directly reuses the Assessment Repository's session factory rather than connecting to another DB on its own.

This lets the Attempt/Assignment in a database transaction be linked within the same database, and reduces application-construction errors like "reading A.db while writing B.db". However, **sharing a session factory does not mean every call of every Service automatically shares one transaction**: each Repository function may still open its own Session and Transaction.

### 12.3 The Recoverable Session Factory only does dependency injection

`create_recoverable_numeric_session_service(bundle, *, orchestrator, student_id, course_id, objective_id, session_id)` injects the three Repositories from the existing Bundle into the Recovery Service, creating no new Engine, database, or user identity. It still relies on the caller to provide a trusted server-side session context. The factory also does not create an LLM Agent, nor connect Jev / NeoHorse models to URPP.

**Source anchors**: Engine / tests in `0bc3250`; FastAPI startup / tests in `fc91a60`; Bundle / tests in `f22dbf9`; Service Factory / tests in `c24d1dc`; `final_snapshot_f86f68d7b4/backend/app/main.py`.

---

## 13. Real failures: the two timestamp bugs in the 13E-3C CLI

**Distinguishing evidence sources**: this Reply 6 ZIP keeps the fixed CLI code of `b8abf71`, the five final CLI tests, and documentation; **it does not include the pytest logs of the two original failures or the intermediate commit of the first fix**. The failure information and historical test counts below come from real terminal output the user submitted earlier in chat; the description of the specific cause can also be cross-checked against the final Repository, Recoverable Session, and CLI functions in the ZIP. "The code contains fix logic" must not itself be treated as a historical failure log.

### BUG-13E-3C-TIME-01: the database had already committed, but the State's `as_of` was earlier

**User-visible symptom**: the CLI appeared to report that the answer was not accepted, yet the Assignment had become Completed and the Attempt had been written to SQLite. The original failing-test record shows the first focused run as `2 failed, 57 passed`; the exact terminal stack should be archived later with the original logs and is not in this ZIP.

**Execution timeline**:

```text
t0 = CLI calls now_utc() for as_of
    ↓
submit_numeric_answer(..., as_of=t0)
    ↓
Repository clock reads t1 = submitted_at; t1 > t0
    ↓
with session.begin(): INSERT Attempt + UPDATE Assignment + COMMIT
    ↓
Recoverable Service checks: as_of < attempt.submitted_at
    ↓
ValueError: State-estimation time precedes submission.
    ↓
Caller sees an exception, but database submission is already committed
```

**The root cause** is not that the Numeric Scorer thought `5` was wrong, nor a partial transaction failure; it is that **the time contract of the State Snapshot time was out of sync with the submit time generated when the database actually committed**. `RecoverableNumericSessionServiceV01.submit_numeric_answer()` calls the Repository first and then explicitly checks `as_of >= attempt.submitted_at`, so this exception can happen after a successful commit.

**Why not resubmit?** The Assignment is already Completed; a second submission can neither undo the first Attempt nor count as "retrying an uncommitted transaction". The "submission failed" the user sees in the UI must be distinguished from the database's actual result. The correct recovery path is to read the existing Session/Assignment/Attempt and call `resume()` with a new, late enough `as_of`.

### BUG-13E-3C-TIME-02: the first fix created a future State snapshot

A historical intermediate fix once used this form:

```python
# historical intermediate approach, not current final code
resume(as_of=now_utc() + timedelta(seconds=1))
```

It could make the recovery moment later than the just-saved Attempt, but the next teaching Decision was then created with an ordinary `now_utc()` again, producing:

```text
Student State as_of = t_now + 1 second
Next Decision requested_at = t_now + tiny_delta
Decision requested_at < state.as_of
    ↓
ValueError: Decision cannot precede its Student State snapshot.
```

This is a classic case of **a local fix satisfying time condition A while breaking time condition B**. The original intermediate test record was `3 failed, 2 passed`, but this source pack has no intermediate code version, and the exact failure stack still needs to be saved separately.

**The final CLI implementation**: after matching the specific `State-estimation time precedes submission.`, it does not resubmit; it calls `resume()` with a fresh `now_utc()`, and then creates the next turn's Decision with `requested_at=completed.state.as_of`. So the next Decision is never earlier than the State snapshot used for deciding. The final CLI's five tests, the historical focused regression of 59, and the full backend of 468 passed (these three **test counts come from execution logs the user provided earlier**; the ZIP has no original output of those full 59/468 runs).

**Key recovery rule**: once there is clear evidence the commit succeeded, recover the saved records; if the commit outcome is unknown, do not assume it succeeded based on an exception string alone; a real application should read the database to confirm the final state of the Assignment/Attempt before acting. The current CLI is a controlled local synthetic demo and does not mean a general idempotent HTTP submission protocol is implemented.

**Source anchors**: the exception handling in `run_lesson()` and the next turn's Decision using `completed.state.as_of` in `b8abf71/scripts/run_local_numeric_lesson_v01.py`; final `recoverable_numeric_session_v01.py::submit_numeric_answer()`; the two original failure outputs the user provided earlier.

---

## 14. Guard Casebook: potential failures covered by tests, not posing as real incidents

All of the following can be located in the matching historical tests in this ZIP. A test name says **what it tries to verify**; unless the user's original failure log is attached, it cannot be claimed that these problems ever happened in real teaching or a deployed environment.

| Guard ID | Reproducible failure scenario | Core defense | Related tests |
|---|---|---|---|
| `GUARD-P06-01` | Issuing a second Pending to the same Session | Unique Pending Session Key; Repository `flush()` check | `test_second_pending_assignment_is_rejected_by_database` |
| `GUARD-P06-02` | A completed Assignment still holding the Pending slot | Key set to NULL in the same transaction; state-consistency CHECK/Trigger | `test_completed_assignment_releases_pending_slot` |
| `GUARD-P06-03` | Reusing a Decision ID in the same session | `(session_id,decision_id)` UNIQUE | `test_completed_decision_id_cannot_be_reused` |
| `GUARD-P06-04` | Two threads issuing at the same time | DB constraints + transactions; the failing side may hit uniqueness or an SQLite lock | `test_concurrent_issuance_produces_at_most_one_pending` |
| `GUARD-P06-05` | Two threads submitting the same question at once | Conditional UPDATE + transaction; exactly 1 Attempt in the end | `test_concurrent_submission_creates_exactly_one_attempt` |
| `GUARD-P06-06` | Attempt INSERT flushed but Assignment UPDATE failed | `session.begin()` rollback | `test_failed_assignment_update_rolls_back_attempt` |
| `GUARD-P06-07` | Database already committed, state rebuild fails by injection | A new Service recovers from persisted facts | `test_recovery_after_database_commit_and_state_failure` |
| `GUARD-P06-08` | Issuing again while a Pending still exists after recovery | `resume()` restores the Pending; the delivery entry refuses | `test_pending_assignment_cannot_be_replaced_after_restart` |
| `GUARD-P06-09` | The wrong student or Session trying to submit/resume | Full-field scope check (not identity authentication) | `test_another_student_cannot_complete_assignment`; `test_other_student_cannot_resume_session` |
| `GUARD-P06-10` | A submitted record swapped to another Assignment or Item Revision | The Completion Service strictly checks ID/Revision/Response Group | `test_tampered_attempt_assignment_link_is_rejected`; `test_tampered_attempt_revision_is_rejected` |
| `GUARD-P06-11` | Migration meets duplicate Pending/Decision historical rows | Read-only data audit stops the upgrade | `test_duplicate_pending_legacy_rows_stop_migration`; `test_duplicate_decision_legacy_rows_stop_migration` |
| `GUARD-P06-12` | Non-existent Session or contradictory historical scope | Migration Audit / Readiness fail closed | `test_orphan_assignment_blocks_upgrade`; `test_scope_mismatch_blocks_upgrade` |
| `GUARD-P06-13` | An external table has an FK depending on the Assignment table during rebuild | Refuses to rebuild automatically with unknown dependencies | `test_inbound_foreign_key_blocks_table_rebuild` |
| `GUARD-P06-14` | FKs turned off in the connection pool | `PRAGMA foreign_keys` re-checked on every checkout | `test_pool_rejects_connection_with_foreign_keys_disabled` |
| `GUARD-P06-15` | The database path disappears after Readiness | `mode=rw` forbids silently creating a replacement DB | `test_database_is_not_recreated_if_removed_before_connect` |
| `GUARD-P06-16` | The health check broken when no database is configured | FastAPI lifespan database opt-in | `test_health_only_startup_needs_no_database` |
| `GUARD-P06-17` | The Session Factory quietly building another set of Repositories or an Engine | Forces injection of the Startup Bundle's exact objects | `test_factory_uses_exact_startup_repository_instances` |
| `GUARD-P06-18` | The CLI accidentally overwriting an existing real database | `O_EXCL` creates a dedicated new demo DB; existing files refused | `test_cli_refuses_existing_database_without_modifying_it` |
| `GUARD-P06-19` | No app-help log wrongly taken as independent answering | The Attempt's help fields stay UNKNOWN | `test_real_cli_no_help_does_not_imply_independence` |
| `GUARD-P06-20` | Student quits the CLI and the Pending is lost | Quitting does not complete the Assignment | `test_cli_quit_keeps_assignment_pending` |

Special note: `test_failed_transaction_restores_source_schema` is a **fault-injection migration test**; it verifies that the old schema is still there when an error occurs before COMMIT, and does not mean a failed migration was ever really run on a user database. `test_real_cli_hint_answer_and_sqlite_recovery` is an integration test of a controlled local demo; it proves the scenario runs, but it is not a validation of teaching effect or independent mastery.

---

## 15. Code walkthrough: one complete local teaching demo (without overstating its capabilities)

`scripts/run_local_numeric_lesson_v01.py` in `b8abf71` actually uses one synthetic Arithmetic Objective and a Numeric Item: `What is 2 + 3?`, Rubric expecting 5, tolerance 0. The CLI accepts only a new demo SQLite file that **does not exist**, and uses local `Base.metadata.create_all(engine)` to initialize **this one explicit new database**; it does not treat `create_all()` as a schema migration for existing databases.

```text
CLI start with NEW synthetic DB
  → initialize schema and enable SQLite FK for demo engine
  → build Assessment / Assignment / Session / Assistance repositories
  → create static Demo Agents and Presentation Service
  → register synthetic teaching session
  → issue version-bound Numeric Assignment
  → terminal prints stored question
  → optional `hint` / `solution`: presenter prints content, then logs app report
  → student submits numeric response
  → atomic Assignment + Attempt completion
  → recover State from stored records
  → display included/excluded Evidence and assistance-event count
  → Decision Engine selects next action from recovered State
  → static Professor Agent prints teaching content
```

A local output flush means the program handed the text to the terminal output stream, **not that the student read or understood the content**. An empty help log cannot prove the student had no outside help either. The CLI's Agents return fixed strings, no real LLM is connected, and no production student identity authentication or HTTP teaching API is provided. Its test records are evidence of local functionality and data consistency, not an experimental conclusion that "the student really learned the math".

---

## 16. Architectural mistakes that are easy to reintroduce: maintenance checklist

1. **Do not create one huge database transaction spanning a whole lesson**: atomic Assignment/Attempt submission and teaching display/State reconstruction are different boundaries. The recoverable state "database commit succeeded, later processing failed" must be reported clearly.
2. **Do not blindly resubmit when a submission-failure message appears**: first read the real Assignment state; if Completed, recover the existing Attempt; only if Pending can resubmission be discussed.
3. **Do not use future times to quickly bypass snapshot-ordering checks**: both `decision.requested_at >= state.as_of` and `state.as_of >= attempt.submitted_at` must hold. A local fix must check the time relations of the whole chain.
4. **Do not translate a missing Assistance Event into `assistance_level=0`**: the answering conditions of persisted submissions may still be unknown; later Learning Observations and Mastery Evidence must be maintained separately.
5. **Do not assume ORM Model changes have been applied to historical databases**: use known Schema Audits, independent backups, explicit migrations, and pre-deployment Readiness; on failure, stop rather than trying to "fix it automatically".
6. **Do not bypass the Startup Bundle with another unchecked Engine**: the current FK protection applies only to connections that actually use that Engine.
7. **Do not treat Scope Equality as authentication**: the current internal services only compare string IDs; a future real API must derive scope from a trusted identity/session context.
8. **Do not record "the user has seen the question or hint" as a database fact**: Assignment issued, Presenter flushed, and application-recorded help are different layers of observation.
9. **Do not assume an atomic read snapshot exists across multiple query steps**: the current Recovery's Repository reads are not automatically bound into one cross-table view at the same moment; higher-concurrency needs should be designed separately.
10. **Do not infer a real historical bug from a test function's name**: provide the original failure log, the hypothesis at the time, the fix diff, and test verification before labeling something `HISTORICAL BUG` in the Casebook.

---

## 17. Historical sources and evidence levels

**Verified facts taken directly from the ZIP**: the files listed under the 19 historical commits; the actual implementation in the source of constraints, Repository methods, migrations, Readiness, Engine, Lifespan, and CLI; the test cases contained in each test file. The ZIP's `SOURCE_MANIFEST.json` records each file's commit, relative path, and SHA-256. SHA-256 detects whether extracted files changed; it is not signature authentication of the code's origin and does not prove the author or runtime environment is trustworthy.

**From real run logs the user provided earlier (not in the current ZIP)**: 13E-3C's two CLI timestamp exceptions, the matching intermediate failure counts, the final `5/59/468 passed`, and commit `b8abf71`. The current ZIP can cross-check the final error-handling code and the five CLI tests, but showing the original tracebacks and repair diff line by line on the website still requires saving the matching complete terminal output separately.

**After-the-fact engineering explanation in this chapter**: for example "why reading Pending first cannot replace a conditional UPDATE", "why the scope FK needs four columns", and "why a consistent read snapshot may be needed in the future" are teaching interpretations derived from the historical implementation and database semantics, and must not be written back as the developer's word-for-word motivation left in each commit at the time.

**What this pack cannot prove**: whether each historical Guard was triggered by a real incident; any formal production deployment, complete cross-process concurrency certification, real-world student identity authentication, real LLM integration, proof of independent answering, broad teaching effectiveness, or usability with other database dialects.

### File-level location index (look up these paths when reading the original archive)

| Topic | Historical source |
|---|---|
| First Assignment persistence and initial tests | `history/assignment_persistence_b36c7b5fba/backend/app/repositories/numeric_assignment_v01.py`; `.../test_numeric_assignment_v01.py` |
| Completed Assignment → State | `history/completed_assignment_state_174f259e7a/backend/app/services/decision/completed_assignment_state_v01.py`; matching tests |
| The Legacy Loop's `_requires_recovery` | `history/persisted_numeric_loop_692b6943f4/backend/app/services/decision/persisted_numeric_session_loop_v01.py` |
| Session Identity and real new-instance recovery | `history/session_recovery_cf9ab746db/backend/app/repositories/numeric_session_records_v01.py`; `.../recoverable_numeric_session_v01.py`; matching tests |
| Pending/Decision constraints and concurrency/rollback | `history/assignment_invariants_a562e6711b/backend/app/repositories/numeric_assignment_v01.py`; `.../test_numeric_assignment_invariants_v01.py` |
| First-generation migration | `history/assignment_migration_79e250c760/backend/app/repositories/migrate_numeric_assignment_v01_sqlite.py`; matching tests |
| Readiness + Session FK Audit | `history/database_readiness_1f50e80483/...`; `history/foreign_key_readiness_cd5c7d4cde/...` |
| Registered Session FK and stricter default delivery | `history/strict_session_assignment_0f32231201/...`; `history/registered_session_default_e735c0fbdf/...`; `history/remove_unregistered_issuance_f86f68d7b4/...` |
| Second-generation migration | `history/foreign_key_migration_3cbeffabe4/backend/app/repositories/migrate_numeric_session_fk_v01_sqlite.py`; matching tests |
| Engine → Startup → Bundle → Factory | `history/guarded_sqlite_engine_0bc3250fb7/...`; `history/sqlite_startup_fc91a60a7d/...`; `history/repository_injection_f22dbf930d/...`; `history/recoverable_session_factory_c24d1dc84d/...` |
| Final CLI | `history/local_numeric_cli_b8abf71993/scripts/run_local_numeric_lesson_v01.py`; its five CLI tests and `docs/24_local_numeric_teaching_cli_v0.1.md` |

**The full index** is `evidence/reply6_source_index.json` in this release package, which stores the historical commit, archive path, size, SHA-256, and per-stage object information for the 71 files. The next stage continues with the later teaching chain and links this chapter into the website's unified navigation and site-wide search.

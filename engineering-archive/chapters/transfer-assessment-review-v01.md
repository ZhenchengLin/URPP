# URPP Engineering Archive · Reply 8 / 10
## Transfer Assessment, Reviewer Authorization, and Evidence Integrity

> **Historical placement**: Implementation 13D-1A → 13D-1B → 13D-1C1 → 13D-1C2 → 13D-1C3 → 13D-1C4 → 13D-1C5. These numbers come from the historical source and design documents; `docs/12` and `docs/18` are not to be misread as separate Implementation numbers.  
> **Material scope**: the 7 Git checkpoints, 60 source/test/diff/snapshot entries, and `SOURCE_MANIFEST.json` in your uploaded `transfer_review_history_source_pack.zip`; the files pass the ZIP integrity check.  
> **Nature of the evidence**: Git objects can confirm how historical code changed; automated tests can confirm which protective scenarios were designed; this source pack has no original failing pytest logs for the seven stages, so no production incident that supposedly happened can be invented.  
> **Important current boundary**: as of the last snapshot in the pack (`4e165f2`), the `RecoverableNumericSessionServiceV01` shown in this chapter **still unconditionally refuses persisted delivery** of `TRANSFER_ASSESSMENT`. The new Review Application can record Review Claims, but that does not mean Transfer Delivery is unlocked.

---

## 1. The whole story in one line

**A student requests Transfer** → **the personalized decision may select TRANSFER_ASSESSMENT** → **an ordinary item may wrongly carry the Transfer action** → **13D-1A adds an Action–Item structural check** → **realizing that "an item tagged Transfer" still does not mean the design is valid** → **13D-1B adds a Review Draft bound to the item's content** → **the Draft has no trusted authorization, so 13D-1C1 shuts Transfer delivery** → **13D-1C2 defines Reviewer identity/permission interfaces** → **13D-1C3 stores version-bound Review Decisions** → **13D-1C4 interprets Review History** → **13D-1C5 wires up the internal Review write flow** → **the delivery gate still does not open**.

This chain has two independent outcomes: on one hand, the teaching system can no longer deliver an ordinary item as a Transfer Assessment just because of a student request; on the other, a prototype flow for recording internal Reviews was built. **What is still missing between the two is a trusted approval source, a judgment of approval validity, and authorization checks at delivery time.** [S01–S07, D12–D18]

### 1.1 Five things that "look like approval" and what each really is

| Phenomenon | What it shows | What it does not show |
|---|---|---|
| `selected_action == TRANSFER_ASSESSMENT` | A teaching action was selected | That the item really tests Transfer; that the item is approved; that the student will complete it independently |
| `item.evidence_type == TRANSFER_ATTEMPT` | The item has a structural tag | That its design was reviewed by a real expert and has a genuinely new application context |
| A `TransferDesignReviewDraftV01` created successfully | A pending design explanation bound to this item's content was filled in | That someone has reviewed it, that the reviewer is real, or that delivery is authorized |
| A saved `TransferReviewDecisionV01(outcome=APPROVE)` | The database has a historical record claiming approval | That the writer had authority to approve, that the record is currently valid, or that delivery may proceed |
| `APPROVE_RECORDED` | The latest record in this sequence at the chosen moment claims approval | That the real Reviewer identity or approval source was verified; that the Delivery Gate can be bypassed |

If you remember only one sentence from this chapter: **Action, Tag, Draft, Recorded Decision, and Trusted Delivery Authorization are five different levels of fact and cannot be merged into a single `approved=True`.** [S01–S07]

---

## 2. Historical timeline and actual changes (strictly by Git checkpoint)

| Stage / Commit | Actual change confirmable at the time | What this stage did not finish |
|---|---|---|
| **13D-1A · `e2ef14dd3e`** | Adds `require_eligible_assessment_action_v01()`; checks the Action–Item correspondence before delivery in the Recoverable Session; adds structural-check tests and `docs/12` | Substantive review of Transfer design; proof of assisted/independent work |
| **13D-1B · `1e6ca9802a`** | Adds `TransferDesignReviewDraftV01`, a full Item Fingerprint, Draft–Item Binding, design-question fields, and `docs/13` | Real Reviewers, approval records, fetching the authoritative Revision from the database |
| **13D-1C1 · `bbddaf38ed`** | Adds `require_trusted_transfer_delivery_v01()`, which always refuses Transfer; wires it into the Session; adds tests refusing unapproved delivery and `docs/14` | Any "pass if there is an Approval" path |
| **13D-1C2 · `d8aac30f08`** | Adds Identity/Permission Provider protocols, time/Issuer/Scope checks, a fail-closed Authorization Service, and `docs/15` | A real deployed authentication system; production permission management |
| **13D-1C3 · `8c83c51ae6`** | Adds the Review Decision contract, full Draft hash, a Repository linked to Item Revisions with SQLite tests, and `docs/16` | `is_approved()`, a trusted issuing source, production migration |
| **13D-1C4 · `bc79363d17`** | Adds the REVOKE record type and lifecycle state interpretation; handles equal timestamps, duplicate IDs, future times, and different Item histories explicitly; `docs/17` | Identity audit of who may revoke, real ordering guarantees, approval tokens |
| **13D-1C5 · `4e165f2b35`** | Adds `TransferReviewApplicationServiceV01`: load stored item → get time → call the authorization interface → generate a Decision ID → save; `docs/18` | Making identity and writing an un-bypassable production boundary, or connecting recorded results to the Delivery Gate |

**How to re-check**: each checkpoint has, in the source pack, both a Git file snapshot under `history/<label>_<hash>/...` and the raw change in `diffs/<label>_<hash>.patch`. `final_snapshot/` is the version of the last checkpoint and **must not be read backwards as if every earlier checkpoint had that capability**. [M01]

---

## 3. 13D-1A: an ordinary Numeric Item cannot be renamed Transfer by a Request

### 3.1 The call boundary where the problem arose

`PersonalizedDecisionEngine` can select `TRANSFER_ASSESSMENT` because of an explicit student request. The historical `docs/12` records explicitly that the Recoverable Session previously allowed an ordinary `PROBLEM_ATTEMPT` Item to be persisted together with a Transfer Action. **The document explicitly describes this as an earlier design gap; the source pack provides no incident record of a real student being scored wrongly.** [D12]

First distinguish three kinds of objects:

```text
StudentLearningRequestV01: REQUEST_TRANSFER
      → only the activity the student wants to do
TeachingActionV01: TRANSFER_ASSESSMENT
      → only the action selected for the current teaching turn
AssessmentItemV02.evidence_type: PROBLEM_ATTEMPT / TRANSFER_ATTEMPT
      → the structural tag stored on the specific item itself
```

The wrong linking path is conceptually: **request Transfer → action Transfer → item not checked → ordinary item issued under the Transfer action**. The fix does not change Student State or the Numeric Rubric; it adds an Action–Item consistency check before delivery runs. [S01, D12]

### 3.2 The real implementation: `require_eligible_assessment_action_v01()`

The input is the selected `TeachingActionV01` and the actually loaded `AssessmentItemV02`; returning `None` means the structural check passed, and failure raises an exception:

```python
if selected_action not in ASSESSMENT_ACTIONS:
    raise ValueError("Numeric Assignment requires an assessment action.")

if not item.alignment_verified:
    raise ValueError("Assessment objective alignment is not verified.")

if (
    selected_action == TeachingActionV01.TRANSFER_ASSESSMENT
    and item.evidence_type != EvidenceType.TRANSFER_ATTEMPT
):
    raise ValueError(
        "Transfer assessment requires a transfer-tagged Assessment Item; "
        "an ordinary problem cannot be relabelled by a student request."
    )
```

The real code has two more type checks: a `TeachingActionV01` and an `AssessmentItemV02` must be passed, not arbitrary strings or objects. For ordinary Assessment Actions such as `DIAGNOSTIC_ASSESSMENT` and `INDEPENDENT_PRACTICE`, the structural guard does not require a Transfer tag. **This is a necessary structural condition, not a sufficient condition establishing that the item has knowledge-transfer validity.** [S01, T01]

### 3.3 At which step of the Session is this check?

In the last checkpoint, `RecoverableNumericSessionServiceV01.deliver_numeric_assessment()` runs in this order: recover the Session → confirm there is no Pending Assignment → check the Decision ID is unused → load the original Item Revision → check Course/Objective and Alignment → **call `_turn_orchestrator.run_turn()`** → verify an Assessment Action was returned → **check Action–Item** → **check the Transfer Delivery Gate** → build `AssessmentDeliveryV01` → `issue_assignment()`. [S08]

Note the bold positions: **the teaching Agent has already been called by the Orchestrator before the two Gates.** These Gates can stop an illegal Assignment from being persisted; they **do not guarantee the Agent never ran, nor that the frontend never saw the Agent's generated content**. This is not speculation; `docs/12` and `docs/14` state this limitation explicitly. To implement "all invalid actions are rejected before the Agent is called", Decision, Validate, and Execute would need to be split into three steps; changing only the current Gate's return value is not enough. [D12, D14, S08]

### 3.4 An important cross-limitation: the current Numeric Scorer cannot automatically produce Transfer success

In the last snapshot, `score_numeric_attempt()` explicitly requires `item.evidence_type == EvidenceType.PROBLEM_ATTEMPT` and outputs `transfer_distance="none"`; it copies the Attempt's `assistance_level` and `prior_solution_exposure` and does not infer independence from a correct answer. So even if some Transfer-tagged Item can eventually be delivered, **this Numeric Scorer still cannot automatically produce verified Transfer Performance Evidence from it**. A new Transfer Scorer, assessment-design validation, and assistance-condition rules are separate work. [S09]

---

## 4. 13D-1B: why must a Review Draft describe both the "new context" and the "non-transfer path"?

### 4.1 An item tag cannot prove the item really requires transfer

Writing `evidence_type` as `TRANSFER_ATTEMPT` is a structural declaration. A real Transfer question requires the student to apply previously learned knowledge to a new context. The historical Draft collects specific design reasons rather than an unexplained `is_transfer=True`. [D13]

| Draft field | The question it answers |
|---|---|
| `source_learning_context` | In what context did the student previously learn this knowledge? |
| `target_application_context` | In what new context is it now going to be tested? |
| `changed_context_factors` | Which background, presentation, or application conditions changed concretely? At least one |
| `invariant_knowledge` | What principle stays valid across contexts? |
| `required_transfer_reasoning` | What recognition, derivation, or application must the student do to complete the task? |
| `plausible_non_transfer_path` | Could the student get it right by chance through memory or mechanical pattern-matching, without understanding the transfer? |
| `review_questions` | What open points must the reviewer still confirm? At least one |

The last two fields are especially important: even if the item's story context changes, a student may still answer correctly by mechanically applying a remembered pattern. The Draft should write this possible path down so a future Reviewer can judge whether the item really distinguishes transfer from repeated practice. **Non-empty fields do not mean the review passed, and the Draft cannot automatically verify whether the student has transfer ability.** [S02, D13]

### 4.2 Deriving the full Item Fingerprint

`fingerprint_assessment_item_v01(item)` serializes `AssessmentItemV02.model_dump(mode="json")` as stably sorted JSON and computes SHA-256:

```python
serialized = json.dumps(
    item.model_dump(mode="json"),
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
item_content_sha256 = sha256(serialized.encode("utf-8")).hexdigest()
```

This binds the Draft to the Item's **complete model content at that time**. Compared with comparing only `assessment_item_id`, changes to the Prompt, Rubric, Evidence Tag, and other fields all change the digest of the serialized data. But `item_revision`, Course, Objective, and Item ID must also be stored and compared, because at this stage the Revision is passed in by the caller, and **the function itself does not query the database to prove the Revision corresponds to the authoritative item**. [S02, D13]

`require_current_transfer_review_binding_v01()` requires in order: correct Draft/Item types → matching ID/Revision/Course/Objective → matching content Fingerprint → the current Item still has the Transfer Tag and Verified Alignment. Passing means "this Draft is still bound to the currently supplied Item snapshot", **not approval, a signature, or a genuine source**. [S02]

### 4.3 What can a hash actually prove?

- **Can**: detect, under the same serialization protocol, that the Draft and the current Item model content disagree.
- **Cannot**: prove an Item really comes from a trusted Repository; prove the Reviewer's real identity; stop a caller who can change both the Draft and the Item from recomputing a matching hash; prove an item has educational measurement validity.

This is content-consistency checking (change detection), not an authorization mechanism, and not a digital signature. [S02, D13]

### 4.4 What do the historical tests prove?

`test_transfer_design_review_v01.py` checks that the same content gives the same digest, that changing the item content invalidates an old Draft, that changing the Revision/Item ID is rejected, that ordinary items and unconfirmed Alignment cannot create a Draft, that required text and timezone-aware times cannot be missing, and that the Draft has no Approval/Reviewer permission fields. **These are defensive design tests; the pack has no real production log of "the system once wrongly reused an old Draft after an item changed".** [T02]

---

## 5. 13D-1C1: why "refuse all Transfer delivery" was chosen at first

13D-1A could already reject ordinary items posing as Transfer, but a real Transfer Tag still does not prove the item has been reviewed. 13D-1B could produce Drafts, but there was no reliable real Reviewer Authorization and no trusted Approval Source. The `require_trusted_transfer_delivery_v01()` introduced here is very small, but its boundary is very clear:

```python
def require_trusted_transfer_delivery_v01(*, selected_action):
    if not isinstance(selected_action, TeachingActionV01):
        raise TypeError(...)
    if selected_action == TeachingActionV01.TRANSFER_ASSESSMENT:
        raise ValueError(
            "Transfer Assessment delivery requires a trusted "
            "Transfer Design Approval. No trusted approval source is configured."
        )
```

Ordinary Assessment Actions continue through the original flow. A Transfer Action **does not consult the Review table, does not accept an `approved=True` parameter, and is always refused**. This version has no code path of the form "pass as long as the database has one APPROVE". [S03, D14, T03]

### 5.1 What does each of the two Gates do?

```text
Item and Action do not match
    ↓ require_eligible_assessment_action_v01
    REJECT: an ordinary item cannot be tagged Transfer

Item and Action match structurally, and the Action is Transfer
    ↓ require_trusted_transfer_delivery_v01
    REJECT: no trusted Approval Source exists
```

A Transfer Item that passes the first Gate is still rejected at the second. **Structural validity and delivery authorization cannot be judged together.** [S01, S03, S08]

### 5.2 This Gate's scope is not "every possible entry point in URPP"

`docs/14` explains clearly that the Gate is wired into `RecoverableNumericSessionServiceV01`, **but does not claim to cover every historical legacy delivery path**. Also, the Agent is called before the Gate. When this chapter says "Transfer cannot be delivered", it refers specifically to this Recoverable Session Assignment path that the source connects, and makes no global safety promise about unreviewed other paths. [D14, S08]

---

## 6. 13D-1C2: an Identity Assertion, a Permission Provider, and real authentication are not the same thing

### 6.1 Division of labor: identity and permission are two separate queries

The interface `ReviewerIdentityProviderV01.current_reviewer()` returns a `ReviewerIdentityAssertionV01 | None` containing `reviewer_id`, `issuer`, and `verified_at`. `TransferReviewPermissionProviderV01.may_approve_transfer()` takes Reviewer, Issuer, Course, and Objective and returns a boolean. **"Knowing who someone is" is not "having the right to review this topic in this course".** [S04]

`ReviewerIdentityAssertionV01` is an ordinary Python dataclass; any code that can construct this object can write `reviewer_id="reviewer-001"`. A `Protocol` likewise only specifies the call interface and **does not automatically create a trusted identity source**. So this module is accurately named an Authorization Contract / Policy Prototype, not Production Authentication. [S04, D15]

### 6.2 The full check chain of `require_reviewer_for_draft()`

1. `as_of` must be a timezone-aware time.
2. `require_current_transfer_review_binding_v01()` must pass; **a stale Draft is rejected first, before querying the identity/permission Providers**.
3. Both Providers must be configured, otherwise fail closed.
4. The Identity Provider is called; exceptions, `None`, and wrong return types are all rejected.
5. The identity's Issuer must match the application configuration.
6. `identity_age = as_of - identity.verified_at` must be within `[0, 15 min]`; future or expired times are rejected. 15 minutes is a provisional prototype parameter, not a validated production session policy.
7. The Permission Provider is called with Reviewer ID, Issuer, Course, and Objective; exceptions and denials both fail closed.
8. The return value must be **exactly `True`**; the string `"true"` or the integer `1` does not count as authorization.
9. Returns `ReviewerAccessCheckV01`, containing the bound Item ID, Revision, Content Hash, Issuer, Reviewer, and check time. [S04, T04]

### 6.3 The most easily misunderstood part of this boundary

`ReviewerAccessCheckV01` is not an HMAC signature or a transferable authorization token; it is just the result of one check by **configured Providers**. If a student-facing API lets callers inject an arbitrary `FakeIdentityProvider` and `FakePermissionProvider`, that API has established no real authentication boundary. A real system must have the trusted application layer own the Provider configuration exclusively, restrict who may construct the Service, bind it to the logged-in user, and restrict direct write access to the Repository. [S04, D15]

**Historical test scope**: the test file uses stand-ins such as `TestIdentityProvider` / `TestPermissionProvider`. It tests missing Providers, Issuer mismatch, identities that are expired or from the future, permission denial, Providers raising, invalid Drafts, and wrong types; **it does not verify that a real identity system is live**. [T04]

---

## 7. 13D-1C3: the Decision contract and SQLite Repository store Claims, not Delivery Tokens

### 7.1 Fields of the Decision object

The actual fields of `TransferReviewDecisionV01`:

```text
decision_id
assessment_item_id, item_revision
course_id, objective_id
item_content_sha256, draft_content_sha256
reviewer_id, reviewer_identity_issuer
outcome: approve / reject / revoke (REVOKE added later in 13D-1C4)
rationale, decided_at
```

`draft_content_sha256` is stable JSON + SHA-256 over the **complete Review Draft**, and `item_content_sha256` refers to the complete Assessment Item. This way, later changes to the substantive reasons in a Review are not silently treated as the same Draft as the original Decision. The Reviewer ID and Issuer in the object are only **recorded declarations** and cannot prove their own source is trustworthy. [S05, S06]

Note the history: in the initial `8c83c51` version, `TransferReviewOutcomeV01` had only APPROVE/REJECT; REVOKE was added only afterwards in `bc79363`. When the website explains the final fields using the last snapshot, it still records this increment separately and does not write the new state back into the old commit. [P06]

### 7.2 The Repository's actual database design

`TransferReviewDecisionRow` has primary key `decision_id`, plus `assessment_item_id`, `item_revision`, and a JSON `payload`. The table declares a composite foreign key `(assessment_item_id, item_revision)` → the same column pair in `assessment_items_v02` (`ON DELETE RESTRICT`). The Repository's `save_decision()` checks within one database session: Decision ID unused → target Item Revision exists → Item type is Numeric → Course/Objective match → recomputed Item Fingerprint matches → add Row → commit. On failure, storage success must not be confused with Review approval. [S07]

`load_decision()` fetches by ID and validates as `TransferReviewDecisionV01`. `list_decisions_for_item()` lists the history for a specific Item Revision; the final sort by `(decided_at, decision_id)` **is only the order for browsing the returned history, not logic for obtaining current authorization**. [S07]

### 7.3 The real scope of "append-only"

The Repository provides no Update/Delete methods and forbids a duplicate Decision ID from overwriting the original record; this prevents "directly rewriting historical approvals" through normal calls to the Repository API. But administrators or other code with write access to the underlying database could still change rows, so it must not be described as a tamper-proof audit. Also, this is an SQLAlchemy ORM definition plus SQLite unit/integration tests; **this stage applied no migration of the new table to any existing production database, and the presence of `Base.metadata.create_all()` tests does not imply the production schema was upgraded.** [S07, D16, T05]

### 7.4 A counterexample that runs through the whole chapter

```text
The database has a record: outcome = approve
          ↓
Repository.load_decision() succeeds
          ↓
Lifecycle interpretation: APPROVE_RECORDED
          ↓
require_trusted_transfer_delivery_v01(TRANSFER_ASSESSMENT)
          ↓
still raises ValueError
```

The last step above is not a future guess; it is behavior that the historical tests check explicitly. The reason is that the Repository offers no `is_approved()` at all, and the Delivery Gate does not read this table at all. **There is no automatic connection between saving a decision and authorizing delivery.** [S03, S07, T05]

---

## 8. 13D-1C4: how the Review Lifecycle handles revocation, equal timestamps, and dirty history

`evaluate_transfer_review_lifecycle_v01(item, item_revision, decisions, as_of)` takes a specified item and a set of historical Decisions and returns `TransferReviewLifecycleResultV01(status, reason, current_decision_id, considered_decision_ids)`. **It does not query the database, does not verify whether a Reviewer is genuine, and never opens the Delivery Gate.** [S10]

### 8.1 Six return statuses

| Status | Exact meaning |
|---|---|
| `NO_DECISION` | The input history is empty |
| `APPROVE_RECORDED` | In a valid, conflict-free input history, the record with the latest unique timestamp has Outcome APPROVE; only a Claim |
| `REJECT_RECORDED` | The record with the latest unique timestamp is REJECT |
| `REVOKE_RECORDED` | The record with the latest unique timestamp is REVOKE |
| `AMBIGUOUS` | At least two different Decisions share the latest timestamp; even two APPROVEs count as ambiguous |
| `INVALID_HISTORY` | Duplicate Decision IDs, different Item/Revision/Scope/content, a record time later than `as_of`, etc. |

### 8.2 Actual execution rules

1. Validate `item`, a positive integer Revision, a timezone-aware `as_of`, and the Decision sequence and its member types.
2. Empty input returns `NO_DECISION`.
3. Any duplicate Decision ID → `INVALID_HISTORY`, even if the two records' fields are identical.
4. Compare each record with this Item ID, Revision, Course, Objective, and full Fingerprint; any mismatch → `INVALID_HISTORY`.
5. `decision.decided_at > as_of` → `INVALID_HISTORY`.
6. Sort by `(decided_at, decision_id)` to find the latest record, but **the Decision ID may not be used to break a tie on the latest timestamp**; if two records share the latest timestamp → `AMBIGUOUS`.
7. When there is exactly one latest record, interpret its Outcome as the matching `*_RECORDED` status for APPROVE/REJECT/REVOKE. [S10, D17]

Why are "two APPROVEs at the same time" still not treated as approval? Because they may be two independent concurrent review events; a Decision ID is an identifier, not a trustworthy time sequence of review order. Deciding approval outcomes by string ordering would mistake the accident of database sorting for the real review order. [S10]

### 8.3 REVOKE is only a historical record, not a deletion, and does not automatically withdraw items already delivered

`REVOKE` was added to the Outcome enum in `bc79363`. After a REVOKE is recorded, the latest Lifecycle can show `REVOKE_RECORDED`. If a later APPROVE then appears, the Lifecycle can become `APPROVE_RECORDED`; **but this proves neither that the revoker had the right to revoke nor that the later approver had the right to restore authorization**. The source explicitly refuses to treat it as Delivery Permission. [S06, S10, D17]

### 8.4 Remaining issues that must be recorded carefully

- Time is supplied by the application/call chain; the Lifecycle only checks whether a time is valid relative to `as_of` and cannot prove it came from an unforgeable server clock.
- It does not verify the real write source of approval records, approver/revoker permissions, or a multi-Reviewer quorum.
- The input sequence itself is supplied by the caller; if real historical records are missing, the function cannot detect on its own that "a REVOKE is missing here".
- The current Review Repository does not automatically run the Lifecycle Policy on each write; it is a descriptive interpretation applied after reading the history. [D17, S07, S10]

---

## 9. 13D-1C5: how the Application Service assembles the earlier components

**This is an internal Review write operation with a real code call order, not a deployed authentication system.** [S11, D18]

```text
submit_review(draft, outcome, rationale)
    ↓ check input types and non-empty rationale
AssessmentRecordRepositoryV02.load_item(id, revision)
    ↓ fetch the exact Item version stored in the database; do not trust an external temporary Item
Application clock() → decided_at
    ↓ check timezone and draft.created_at <= decided_at
TransferReviewerAuthorizationServiceV01.require_reviewer_for_draft(...)
    ↓ check Draft–Item, Providers, Issuer, Freshness, Course/Objective Permission
verify the ReviewerAccessCheck's Item/Revision/Hash/Time match this operation
    ↓
token_urlsafe(24) generates this decision_id
    ↓
create_transfer_review_decision_v01(...)
    ↓
TransferReviewDecisionRepositoryV01.save_decision(decision)
    ↓
return decision (a historical Claim, not a Delivery Token)
```

### 9.1 What does the method signature deliberately not expose?

The real `submit_review()` **accepts only** `draft`, `outcome`, and `rationale`; it does not accept a caller-specified `reviewer_id`, `issuer`, `decided_at`, or a previously built `ReviewerAccessCheck`. This design narrows the entry points for forging approval information **through this method**; but code that controls the Providers/Clock in the constructor, or that bypasses the Service and calls the Repository directly, can still produce Claims without real authorization. [S11, T07]

### 9.2 Why look up the stored item first, then check the Draft?

13D-1B's Draft creator uses only the `AssessmentItemV02` object passed in and does not query SQLite. The Application Service instead loads the historically saved Item through `AssessmentRecordRepositoryV02.load_item(..., revision=...)` and then hands it to the Authorization Service for the binding check. This can reject a Draft that points to a non-existent Item Revision or disagrees with the saved Item content. But **retrieving an Item from the Repository that matches the Fingerprint does not mean a professional Reviewer has confirmed the item is a genuine Transfer item**. [S02, S11, T07]

### 9.3 Why are Authorization and saving still not one atomic action?

The source comments state explicitly: the authorization Service is called first, then `save_decision()` runs in another Repository session; the two steps are not one transaction. If permission is revoked after the check and before the write, or another Review Decision is produced concurrently, the existing code has no transaction-level ruling on the current validity of the approval. Because the Delivery Gate is still closed, this prototype will not open Transfer Assignments directly because of such a historical Claim; but if the Gate is to be opened in the future, a verifiable approval source, revocation ordering, and re-checks at delivery time must be designed first. [S11, D18]

### 9.4 Test scope: the positive path with Fake Providers is not real authorization

`test_transfer_review_application_v01.py` uses FakeIdentityProvider / FakePermissionProvider, temporary SQLite, and an injectable Clock, and checks: normal writes and recovery after reopening the database; **no decision written** when a Provider is missing or permission is denied; Issuer mismatch; stale Drafts; non-existent Item Revisions; a Draft created after the Decision; an invalid Clock; the interface not letting requesters forge identity/time; and APPROVE still not opening the Delivery Gate. The tests do exist; **this pack does not include the total pytest pass counts from actually running them at the time, or a real end-to-end production authentication demo**. [T07]

---

## 10. Bug Casebook: which are real development history and which are only Guard Tests?

### CASE 13D-A · Early on, ordinary items were allowed to follow a Transfer Action (a fixed gap supported by design documents and code diffs)

**Historical basis**: `docs/12` states explicitly "Previously ... could persist an ordinary PROBLEM_ATTEMPT item under that Transfer Assessment action"; the diff of `e2ef14d` shows the added Action–Item Guard and its wiring into `RecoverableNumericSessionServiceV01`; the matching tests verify ordinary items are rejected. [D12, P01, T01]

**Problem → fix → test**: a Student Request can make the Personalized Decision select Transfer → the delivery side did not check the real item tag → `require_eligible_assessment_action_v01()` checks compatibility between the selected action and the stored item → unit tests reject ordinary items and accept structurally compliant Transfer-tagged Items. **This cannot be used to claim further that "a real student was once misjudged as having Transfer Mastery", because the pack has no such incident log.**

**Shortcoming found later**: a Transfer Tag is only a text/enum label, not a Review Approval. So `1e6ca98` added the Review Draft and `bbddaf38` further added the fail-closed Gate. This is a continuous engineering adjustment from "structural checking" toward "trusted delivery preconditions", not a story of one bug fixed in one line. [D12–D14, P01–P03]

### CASE 13D-B · The first structural check still let items "with only a Transfer Tag" through (a design boundary confirmed by tests)

`test_transfer_tag_satisfies_only_structural_requirement()` shows explicitly that passing the structural check does not include Design Approval; `docs/13` also admits there was no real delivery approval yet when the Draft was introduced. Then the diff of `bbddaf38` added the Gate wiring and tests that "unapproved items must not be issued". This is a **checkable historical design gap and its enhancement**, not production data corruption the pack can prove. [T01, D13, P03]

### GUARD 13D-01 · Wrong Alignment / ordinary item / non-Assessment Action

`alignment_verified=False`, an ordinary item requested as Transfer, a Professor Action entering a Numeric Assignment, and an illegal Item type each trigger ValueError/TypeError. The tests ensure a user request is never taken directly as a property of the item. [T01]

### GUARD 13D-02 · Review Draft content/version invalidated

After changing the Prompt or Rubric or the Revision/ID, `require_current_transfer_review_binding_v01()` rejects the no-longer-matching Draft. The tests also check timezone-aware times and required text; equal hashes alone do not constitute approval. [T02]

### GUARD 13D-03 · A caller tries to pass `approved=True` to bypass the Gate

The Gate has no such parameter; the test expects `TypeError`. This is not a real attack event but an interface design that forbids "deliver because the caller claims it is approved". [T03]

### GUARD 13D-04 · Simulated authentication/authorization errors

No Provider, a Provider returning `None` or a wrong type, wrong Issuer, an identity that is expired or from the future, Permission returning a string/integer, a Provider raising, a stale Draft — all must be rejected. The tests use Fake Providers and do not prove a real identity system exists. [T04]

### GUARD 13D-05 · Persisting forged or wrong-version Decisions

Duplicate Decision IDs, non-existent Item Revisions, a hash mismatch after the saved Item changes, a mismatched Draft, an empty rationale, or an invalid time are rejected by the tests; reopening SQLite restores the saved Claims. The Repository has no power to grant Delivery. [T05]

### GUARD 13D-06 · Conflicting order in Review history

Two Decisions at the same latest timestamp → `AMBIGUOUS`; duplicate IDs, content mismatch, or future records → `INVALID_HISTORY`; REVOKE can become the latest record but does not mean the revoker had the right to revoke. [T06]

### GUARD 13D-07 · The Application write path forged or invalidated

Missing identity, permission denied, wrong Issuer, non-existent Item Revision, stale Draft, invalid Clock, or trying to pass a Reviewer ID directly → no decision saved; the legitimate test-double path can save a Claim and restore it after reopening, but still cannot open the Transfer Gate. [T07]

### 10.1 What must never be invented in this round

- There is no original failing pytest output for these seven commits, so we cannot claim how many failures occurred or which fix followed the first failure, and cannot write tracebacks that do not exist.
- The original diffs show how code and tests changed; they are not the full discussion or troubleshooting order of the time. The "motivation at the time" can only be quoted from design documents; everything else is labeled after-the-fact technical explanation.
- There is no evidence of real account login for an authorized Reviewer, approval seals, trusted approval tokens, or enabled Transfer Delivery; the source actually says explicitly that these are not implemented yet. [M01, D15–D18]

---

## 11. Cross-module walkthrough: a Transfer Request that can really be checked

The following is an **explanatory scenario constructed from the cited source**, not a real student's original history log.

**Input**: the student requests `REQUEST_TRANSFER`, the Decision Engine returns `TRANSFER_ASSESSMENT`; the current Item is a `PROBLEM_ATTEMPT`.

```text
run_turn() → selected_action = TRANSFER_ASSESSMENT
      ↓ require_eligible_assessment_action_v01
item.evidence_type = PROBLEM_ATTEMPT
      ↓ ValueError
no AssessmentDeliveryV01
issue_assignment() not called
```

Changing the item tag to `TRANSFER_ATTEMPT` does not solve the problem:

```text
Action–Item Guard: passes (structural meaning only)
      ↓ require_trusted_transfer_delivery_v01
      ↓ ValueError: No trusted approval source
this Transfer Assignment is still not created or persisted
```

Then build a Draft bound to the Item Revision and use **test-only** Identity/Permission Providers to produce an APPROVE Decision:

```text
Review Application → saved APPROVE Claim
Review Lifecycle → APPROVE_RECORDED
Recoverable Session → Transfer Delivery Gate
      ↓ still ValueError
```

Even if trusted approval and a delivery chain are added later, the following must still be handled separately: the current Numeric Scorer's limitation on Transfer Tags, substantive review of whether an item measures transfer, the real source of Attempt assistance/prior solution exposure, and the State Estimator's eligibility judgment for Transfer Evidence. **None of these four can be obtained automatically by simply opening the delivery Gate.** [S01, S03, S08–S11]

---

## 12. Architecture Decision Records (ADR)

### ADR-13D-01 · Decision and content eligibility are independent

- **Context**: a student can request Transfer, but the request does not change the stored item's Rubric/Evidence Type.
- **Decision**: add an independent Action–Item Eligibility Guard, placed before Assignment issuance.
- **Benefit**: prevents ordinary items from being wrongly reclassified because of a teaching action.
- **Cost/limits**: the Gate only does a structural check and cannot assert measurement validity; the teaching Agent may run before the Gate.
- **Historical basis**: [S01, S08, D12, P01].

### ADR-13D-02 · Bind the Draft to the Item's content and Revision

- **Context**: the object under review may change during or after the review.
- **Decision**: store the serialized Fingerprint of the full Item plus Item ID/Revision/Course/Objective, and re-check them in the Review flow.
- **Benefit**: can detect when the current Item content disagrees with the Draft snapshot.
- **Cost/limits**: SHA-256 does not verify the source or the reviewer's permission; the Revision at Draft-creation time is itself supplied by the caller.
- **Historical basis**: [S02, D13].

### ADR-13D-03 · Stay fail-closed while there is no trusted approval source

- **Context**: structural tags and Drafts may still be generated by the caller.
- **Decision**: refuse `TRANSFER_ASSESSMENT` unconditionally, with no `approved=True` bypass.
- **Benefit**: stops this Session path from wrongly delivering Transfer Assignments while the approval mechanism is missing.
- **Cost/limits**: Transfer requests with a legitimate teaching need temporarily cannot be completed through this path; this is not an audit of all legacy paths in the system.
- **Historical basis**: [S03, D14, T03].

### ADR-13D-04 · Decouple Review History from current delivery authorization

- **Context**: the database can store historical Claims, but their source, revocation, and current validity have no trusted proof yet.
- **Decision**: the Repository offers only Save/Load/List; the Lifecycle offers only descriptive `*_RECORDED` states; the Application only writes historical Claims; the Delivery Gate does not consume these outputs.
- **Benefit**: avoids wrongly promoting a newly developed prototype review feature into a production security control.
- **Cost/limits**: real authorization, clock/transaction consistency, production migration, and independent Transfer Scoring remain future work.
- **Historical basis**: [S03–S11, D15–D18].

---

## 13. How to re-check, extend, and maintain this chapter later

Every source reference in this chapter gives the full module path; `evidence/reply8_chapter_source_index.json` contains the seven full commit hashes, the source file locations inside the ZIP, file SHA-256s, and the aliases in the table below. First look at the History Snapshot to see when a feature appeared; then look at the matching diff to see which lines were added or changed; finally look at the tests of the time to confirm which behavior was checked. **Do not read the latest version first and then write its behavior back onto earlier versions.**

| Source ID | Location (inside the historical pack) | Statements it can support |
|---|---|---|
| M01 | `SOURCE_MANIFEST.json` | The seven historical checkpoints, file sources, hashes, and version boundaries |
| P01–P07 | `diffs/*.patch`, numbered by checkpoint | The real increment of a given commit |
| S01 | `final_snapshot/backend/app/services/decision/assessment_action_eligibility_v01.py` | Structural checks and error text |
| S02 | `final_snapshot/backend/app/services/assessment/transfer_design_review_v01.py` | Draft fields, Item hash, binding checks |
| S03 | `final_snapshot/backend/app/services/decision/transfer_delivery_gate_v01.py` | Unconditional refusal of Transfer |
| S04 | `final_snapshot/backend/app/services/assessment/transfer_reviewer_authorization_v01.py` | Provider interfaces, identity freshness, permission checks |
| S05 | `final_snapshot/backend/app/services/assessment/transfer_review_decision_v01.py` | Decision contract, Draft hash, REVOKE added later |
| S06 | `history/review_decision_persistence_8c83c51ae6/.../transfer_review_decision_v01.py` | The initial Decision enum (without REVOKE) |
| S07 | `final_snapshot/backend/app/repositories/transfer_review_decisions_v01.py` | Database storage and source limits |
| S08 | `final_snapshot/backend/app/services/decision/recoverable_numeric_session_v01.py` | The order of the Agent, the two Gates, and Issue Assignment |
| S09 | `final_snapshot/backend/app/services/assessment/numeric_scoring_v02.py` | The Numeric Scorer's existing limitation on Transfer Tags |
| S10 | `final_snapshot/backend/app/services/assessment/transfer_review_lifecycle_v01.py` | `*_RECORDED`, conflicts, and invalid history |
| S11 | `final_snapshot/backend/app/services/assessment/transfer_review_application_v01.py` | The Review write call chain and its non-atomicity |
| D12–D18 | `docs/12...` to `docs/18...` for each stage under `history/` | The purpose, non-goals, and limits each stage stated at the time |
| T01–T07 | The matching tests under `history/` and `final_snapshot/backend/tests/` | Protective scenarios (do not automatically prove real failures) |

### 13.1 This chapter changes no production behavior

This chapter is an engineering document made from the uploaded historical material. Generating the HTML / Markdown and installing it into `engineering-archive/` does not change URPP's backend, SQLite, Git branches, Evidence Eligibility, or the Transfer Delivery Gate.

**Closing judgment (strictly limited to the current historical checkpoint)**: the 13D series completed the prototype boundaries "ordinary items cannot pose as Transfer, delivery on this Session path is refused while no trusted approval source is configured, and internal Review Claims can be recorded and checked"; **it did not complete "a Transfer Assessment can be delivered after approval by a really authorized Reviewer", and does not thereby prove that students achieved Transfer Learning.**

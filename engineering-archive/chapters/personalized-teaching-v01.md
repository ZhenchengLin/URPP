# URPP Engineering Archive · Reply 7 / 10

## Personalized Teaching: how Student Requests, Decisions, Agent Routing, and Persisted Assessment really connect

> **Document version**: Reply 7 / V0.1; **historical range**: 2026-09-19, `0e9b77b1` → `5aec0609` → `ad0f9a51` → `9ea307b7` → `e52095f`. The first four checkpoints in this chapter are based on the uploaded historical Git source, matching tests, and design documents; the real failure/fix record for `e52095f` is based on terminal output the user provided earlier. **This chapter did not run tests on the user's Mac, and it does not claim the internal system now has a production LLM, student identity authentication, or a formal evaluation of teaching effectiveness.**

[Back to site home](../index.html) · [Reply 5: Decision / Orchestration](decision-orchestration-v01.html) · [Reply 6: Persistence / Recovery](persistence-recovery-v01.html)

## 1. Why add Personalized Teaching instead of modifying the old Decision Engine directly?

Reply 5 introduced the original `DecisionEngineV01`: it builds a `DecisionContextV01` from an authoritative `ObjectiveStateV02`, `PedagogicalPolicyV01` gives the state-dependent candidate actions, the Controller makes a proposal, and finally a Policy Check runs. If the proposal is not in the allowed set, a deterministic fallback is used.

The original single-turn Orchestrator used this result to route between `ProfessorAgent` and `AssessmentAgent`. **That version could not express what the student explicitly asked for this time.** If a string such as `"Please explain"` were tucked into a corner of the old `DecisionContextV01`, the old logic might still select a Diagnostic based on the state, and the user's request would never enter the real decision.

Later the product goals added a requirement: even a student in the `STRONG` state can ask the professor to re-explain a basic concept; even without enough Mastery Evidence, a student can ask for more practice. This does not ask the system to believe the student has mastered the knowledge; it asks the system to **respect executable choices of learning activity while keeping the existing boundaries of Assessment, Evidence Eligibility, and Session Integrity**.

This creates two different questions:

1. **Action Selection**: what does the student want to do this time? Which of the activities the system supports can be chosen?
2. **Assessment Admission / Mastery**: does a delivered item really match the objective, Revision, and authorization conditions? Is the answer record enough to update Student State?

The first can be adjusted in response to an explicit request; the second must not be relaxed because of a request. This is the shared design motivation of 13B and 13C.

### Timeline of this chapter: what was added, and what it does not mean

| Historical commit | Stage in the code | Capability confirmed as introduced | Capability not finished at the time |
|---|---|---|---|
| `0e9b77b1` | Implementation 13B-1 | Structured request enum, request contract, separate Personalized Context | Executes no action, updates no mastery state, does not change the old Decision Engine |
| `5aec0609` | Implementation 13B-2 | Deterministic request-to-action mapping, decision source, and action-set expansion record | Calls no Agent, persists no decision, authenticates no student |
| `ad0f9a51` | Implementation 13C-1 | One Personalized Decision calls one matching Agent Port | Delivers no persisted Assignment, receives no answers, recovers no Session |
| `9ea307b7` | Implementation 13C-2A | Adapts personalized Assessment turns to the existing Recoverable Numeric Session | The Adapter itself stores no Assignment and does not keep the full personalized source |
| `e52095f` | Implementation 13C-2B | SQLite end-to-end integration tests verifying persistence, recovery, and student-request interaction | Tests use fake Agents and an isolated database; not a production student identity system |

**Numbering note**: these are the 13B/13C sub-stages actually labeled in the related source docstrings / design documents. They are not the same thing as file numbers such as `docs/07_...` or the Reply 7 number. The original full Implementation 0–13 roadmap still needs separate verification; do not infer other stages from these five checkpoints.

---

## 2. 13B-1: turning a student request into an explicit, checkable object

### 2.1 `StudentLearningRequestKindV01` is not free-text understanding

Historical file: `0e9b77b1/backend/app/services/decision/student_request_v01.py`, lines 24–30. The six requests are:

| Enum | Value | Learning intent expressed |
|---|---|---|
| `REQUEST_EXPLANATION` | `request_explanation` | Ask for a concept explanation |
| `TRY_INDEPENDENTLY` | `try_independently` | Ask to try practicing on one's own |
| `REQUEST_HINT` | `request_hint` | Ask for a hint |
| `REQUEST_DIAGNOSTIC` | `request_diagnostic` | Ask for a diagnostic assessment |
| `REQUEST_SELF_EXPLANATION` | `request_self_explanation` | Ask to explain it oneself |
| `REQUEST_TRANSFER` | `request_transfer` | Ask for a broader application/transfer assessment |

A "request" here is **structured input from the upper application layer**; this stage did not turn arbitrary student natural language into an enum. The source implements no real language understanding or user identity authentication. If LLM intent recognition is added in the future, it must not bypass these explicit Value/Scope/Time checks.

`StudentLearningRequestV01` (lines 33–60) contains `objective_id`, `request_kind`, and `requested_at`. It is configured `frozen=True, extra="forbid"`, and the time must have a timezone.

```python
class StudentLearningRequestV01(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    objective_id: str = Field(min_length=1)
    request_kind: StudentLearningRequestKindV01
    requested_at: datetime
```

**Why `objective_id`?** If the current teaching objective is Matrix Conditioning but a request from the previous Dot Product turn arrives, it must not be silently assigned to the current objective even if its time is valid. **Why must there be a timezone?** Local times without a timezone cannot reliably compare the order of different persisted records.

### 2.2 Composing the Context so the old decision interface cannot ignore the request

`PersonalizedDecisionContextV01` composes `decision_context: DecisionContextV01` and `student_request: StudentLearningRequestV01 | None` instead of inheriting from the old `DecisionContextV01`. See historical source lines 63–104; the design document `docs/07_personalized_decision_policy_v0.1.md` states this motivation explicitly.

```text
ObjectiveStateV02 ──> DecisionContextV01 ──┐
                                           ├──> PersonalizedDecisionContextV01
StudentLearningRequestV01 / None ─────────┘
```

Exact validation order: `request is None` → baseline execution allowed; non-empty request → its objective ID must equal the State's; `request.requested_at >= state.as_of`; `request.requested_at <= decision_context.requested_at`. So the time relation that holds is:

```text
Student State as_of <= Student Request requested_at <= Decision requested_at
```

This does not claim the application has verified the real student's identity; it specifies **time consistency among three structured records**. If the state snapshot is newer than the request, an old request cannot be treated as the user's intent under the current state.

### 2.3 What the tests at this stage actually cover

`backend/tests/test_student_request_v01.py` contains at least eight named tests: no-request baseline, original State preserved, wrong Objective, request earlier than State, request later than Decision, missing timezone, extra fields rejected, and the composed Context not inheriting the old Context. They confirm the expected behavior of this contract, **and do not mean real users ever historically submitted a wrong Objective or timestamp**.

**Stage acceptance conclusion**: 13B-1 introduced an explicit request vocabulary and Scope/Time contract; it did not change student State or the selection of existing Teaching Actions at this stage.

---

## 3. 13B-2: when to follow the baseline, and when to allow an explicit student request

Historical file: `5aec0609/backend/app/services/decision/personalized_engine_v01.py`, with `docs/08_personalized_decision_selection_v0.1.md` and `backend/tests/test_personalized_engine_v01.py`.

### 3.1 Exact mapping of the six requests to actions

Source lines 36–54 record:

| Request Kind | Selected Teaching Action |
|---|---|
| `REQUEST_EXPLANATION` | `CONCEPTUAL_REVIEW` |
| `TRY_INDEPENDENTLY` | `INDEPENDENT_PRACTICE` |
| `REQUEST_HINT` | `CONCEPTUAL_HINT` |
| `REQUEST_DIAGNOSTIC` | `DIAGNOSTIC_ASSESSMENT` |
| `REQUEST_SELF_EXPLANATION` | `SELF_EXPLANATION` |
| `REQUEST_TRANSFER` | `TRANSFER_ASSESSMENT` |

This is a deterministic engineering rule of URPP V0.1, **not a globally optimal teaching-action sequence proven by educational research**. For example, `REQUEST_TRANSFER` selecting `TRANSFER_ASSESSMENT` only means that teaching activity is planned; it can never directly conclude that the student has transfer ability.

### 3.2 No request: delegate directly to the old rule-based baseline

The key call is at source lines 131–147:

```python
if student_request is None:
    decision = self._baseline.decide(decision_context)
    # selection_source = BASELINE
    # selected_for_request = False
    # request_expanded_allowed_actions = False
```

Do not describe "introducing the Personalized Engine" as "replacing the old Decision Engine". **With no explicit request, it reuses the existing `DecisionEngineV01(RuleBasedControllerV01())`.** This way the new capability does not quietly change all ordinary teaching turns, and the baseline can later serve as a control condition in experiments.

### 3.3 With an explicit request: what expands is the state-dependent teaching list, not database or Evidence permissions

Source lines 159–184 first call the old Policy to get `baseline_allowed`. If the action the request maps to is not in it, they build:

```python
allowed = (*baseline_allowed, requested_action)
```

and then produce a `DecisionResultV01` with `selected_action=requested_action`. The result records explicitly in `request_expanded_allowed_actions` whether an expansion happened.

**Example:** the State is `STRONG` and the student asks for a concept explanation. The old state-dependent list may not include `CONCEPTUAL_REVIEW`, and the new personalized result can add this already-supported action so the request is selected. This example corresponds to `test_strong_student_can_request_conceptual_review`; it does not turn strong mastery into unknown, nor let users edit Mastery by request.

**Boundary:** only actions already defined in `TeachingActionV01` can be selected; a request cannot get a mismatched Assessment Item approved for delivery, cannot change an unknown `assistance_level` to independent, and cannot skip existing Session Registration and SQLite integrity checks.

### 3.4 What Decision Provenance is, and what it is not

The fields of `PersonalizedDecisionResultV01` include:

```text
DecisionResultV01 decision
DecisionSelectionSourceV01 selection_source
bool selected_for_request
bool request_expanded_allowed_actions
str selection_reason
```

`selection_source=explicit_student_request` means **this selection came from a structured request**, not "the system has confirmed the student's identity" or "the student has completed the requested action". `selection_reason` is a checkable human-readable explanation, not scoring evidence. At this point the data is only an in-memory function return value; it cannot be asserted to have been written to SQLite.

The source compares `objective_state.model_dump(mode="json")` before and after to prevent the decision function from accidentally modifying the passed State within the program. This check is not a process sandbox and carries no authentication meaning.

### 3.5 Test coverage

The original tests cover: baseline used with no request; the six request mappings; a strong-state request for explanation; actions already in the allowed set not expanded twice; State unchanged; the old Context not misusable; and the Decision Result not falsely reporting Agent execution. They prove the **contract of the action-selection layer**, and say nothing yet about the Agent really executing or the Assessment really being delivered.

---

## 4. 13C-1: from "an action was selected" to "one Agent call"

Historical file: `ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py`; design document: `docs/09_personalized_teaching_turn_v0.1.md`.

### 4.1 Why not call the Personalized Engine first and then the old Orchestrator?

The old `TeachingTurnOrchestratorV01` calls the original `DecisionEngineV01` again inside `run_turn()`. If we first select the user-requested action in the Personalized Engine and then hand the Context to the old Orchestrator, **we would likely get a second decision that does not include the student request**.

That would make `request_explanation → CONCEPTUAL_REVIEW` disagree with the action the Agent finally receives. So the new `PersonalizedTeachingTurnOrchestratorV01` **calls the personalized decision exactly once itself, then routes to a single Agent call**, rather than using the old Orchestrator after a personalized decision has been made. This restriction is written directly in source lines 98–105 and in the original design document.

```text
ObjectiveStateV02 + optional StudentLearningRequestV01
                          ↓
             DecisionContextBuilderV01
                          ↓
            PersonalizedDecisionContextV01
                          ↓
           PersonalizedDecisionEngineV01
                   one decision
                          ↓
                 _route_action()
                    ↙         ↘
             Professor      Assessment
               Agent          Agent
                    ↘         ↙
         PersonalizedTeachingTurnResultV01
```

### 4.2 An Agent Port is an interface, not a real LLM

This uses `PersonalizedTeachingAgentPortV01(Protocol)`:

```python
def produce(
    self,
    *,
    context: PersonalizedDecisionContextV01,
    decision: PersonalizedDecisionResultV01,
) -> str: ...
```

The Port receives both the original structured Student Request and the selected Decision, so the Agent knows which activity the student asked for and why the decision satisfies the request.

**However:** this interface provides no real model inference, HTTP authentication, or Learning Evidence update. 13C-1's tests use Recording Agent doubles; even when a content string is returned successfully, one cannot infer that the student read, understood, or mastered it.

### 4.3 How Agent routing works

Routing reuses the two constant sets `ASSESSMENT_ACTIONS` and `PROFESSOR_ACTIONS` from the old module; `_route_action` returns the matching Agent type only if one of the sets contains the selected action, and raises otherwise. Then only the selected Agent's `produce()` is called.

The Agent receives the full `PersonalizedDecisionContextV01` and `PersonalizedDecisionResultV01`, rather than having the request dropped and being asked to infer it.

Before the call, it checks that `decision_id` and the selected action are in that Decision's allowed list; it checks before and after the decision call, and before and after the Agent call, whether the JSON serialization of the original State changed; `content` must be a non-blank string. Exceptions raised by the Agent are not silently replaced with fake successful teaching output.

### 4.4 The real meaning of "completing a Turn"

`PersonalizedTeachingTurnResultV01` contains `decision`, `agent_kind`, and `content`. It only means **an internal teaching-content generation call returned content of the right shape**; it is not an Assessment Attempt, a persisted Assignment, information the student has seen, or an actual learning effect.

The original tests at this stage include: baseline Assessment routing with no request; a strong-state explanation request going to the Professor; an independent-attempt request going to Assessment; correct routing of supported requests; wrong Objective rejected; invalid Agent output rejected; Agent exceptions not hidden; the Agent unable to quietly modify State; teaching text not being Assessment Evidence.

---

## 5. 13C-2A: connecting the Personalized Turn to the existing Recoverable Numeric Session

Historical file: `9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py`; design document `docs/10_personalized_numeric_session_adapter_v0.1.md`.

### 5.1 Why an Adapter instead of copying a new Numeric Session?

The existing `RecoverableNumericSessionServiceV01` expects its internal Orchestrator to provide the old interface:

```python
run_turn(objective_state, *, decision_id, requested_at)
```

The new Personalized Orchestrator needs the extra `student_request` parameter, and its return structure contains `PersonalizedDecisionResultV01`, which is not the old `TeachingTurnResultV01`.

Copying the whole Recoverable Session to support requests would easily produce two sets of Assignment delivery logic, two sets of Assessment Item Scope/Revision checks, and two sets of atomic submission and recovery logic. Fixing an SQLite bug in one version later could leave the other behind.

So this round uses an adapter: **bind one Student Request to the adapter instance, call the personalized Orchestrator once, and convert the result into the return contract the old Session recognizes.** The authoritative boundary for actually delivering an Assignment stays in the existing Recoverable Session and Repository.

### 5.2 Exact adaptation flow

```text
Structured Student Request
           ↓  build a new Adapter
PersonalizedNumericSessionTurnAdapterV01
           ↓  hand to RecoverableNumericSessionServiceV01
Recoverable Service gets the State and the Assessment Item to deliver
           ↓  calls adapter.run_turn(...)
Adapter checks Objective / Time / one-shot Request
           ↓  Personalized Orchestrator makes one decision + calls the Agent
Adapter checks the result really points to an assessment-type action
           ↓  converts to the old TeachingTurnResultV01
Recoverable Service checks the stored Item and Scope / Revision
           ↓  creates the persisted Assignment by the original logic
```

Note: exactly which function path in `RecoverableNumericSessionServiceV01` checks the Item, whether delivery is allowed, and creates the Assignment should be taken from the corresponding historical source; this diagram shows responsibility boundaries and does not claim every check runs in exactly this fine-grained order.

### 5.3 Why can't Explanation / Hint enter the Numeric Assignment path?

When the adapter is built, it first maps the request to an action and requires the result to be in `ASSESSMENT_ACTIONS`. `REQUEST_EXPLANATION` and `REQUEST_HINT` do not qualify and are rejected; they should be executed through a teaching path that delivers no persisted Numeric Assignment.

Even if upstream gives the adapter a seemingly valid request, after running the adapter still checks `agent_kind == "assessment"` and `selected_action in ASSESSMENT_ACTIONS`, to avoid accidentally delivering a Professor Agent's explanation text as a numeric question.

**A teaching explanation and a persistable Assessment Item are not the same kind of data.** This does not mean the system forbids students from asking for explanations; it refuses to misuse such a request on the "deliver a Numeric Assignment" API path.

### 5.4 One-shot requests, time constraints, and the persistence boundary

`_explicit_request_used` prevents the same Adapter instance from being reused for multiple teaching decisions. This one-shot flag is **in-memory object state**, not an SQLite-backed global de-duplication credential, and not a rule that a real user can only make one request.

To match the State Snapshot time contract of Recoverable Service V0.1, the adapter requires:

```python
request.requested_at == requested_at
```

This is stricter than the time-interval relation of an ordinary 13B-1 Personalized Context. It is **a version constraint of this compatibility-adapter path** and should not be extrapolated into a rule that every teaching request must match the Decision to the exact second.

When the adapter returns the old `TeachingTurnResultV01`, it carries only Decision, Agent Kind, and Content. The original Personalized Decision's `selection_source`, `request_expanded_allowed_actions`, etc. stay only in the intermediate object; **this stage did not write the full personalized source into the Assignment schema**.

### 5.5 How do we judge "what 13C-2A achieved"?

The tests in `test_personalized_numeric_session_adapter_v01.py` cover: an independent-attempt request going to the Assessment Agent; a Transfer request not equaling Transfer success; the no-request baseline; Explanation/Hint not turning into a Numeric Assignment; Objective mismatch; time mismatch; reuse of the same Adapter's request; rejection of wrong routing to the Professor.

These are interface tests using Recording Agents. At this stage **these tests alone were not used to claim cross-process SQLite recovery of personalized teaching**. That belongs to the later 13C-2B integration work.

---

## 6. 13C-2B: real SQLite integration and one real Test Oracle bug

13C-2B's historical integration test file is `backend/tests/test_personalized_numeric_session_sqlite_v01.py`. The terminal log the user uploaded earlier records: the first focused run gave `1 failed, 25 passed`; after adjusting two new test assertions, `26 passed`; the full backend regression gave `324 passed`; the final commit was `e52095f` with the message `test: verify personalized numeric sessions across SQLite recovery`.

### 6.1 Why this failure should not be blamed on the Assignment Repository

Failing test name:

```python
test_explanation_request_cannot_issue_numeric_assignment
```

Test expectation: for a student who asks for a concept explanation, the Numeric Assessment Delivery path must not deliver an Assignment.

Original failing assertion:

```python
assert not stack.last_assessment_agent
```

But `stack.last_assessment_agent` held a `RecordingAgent` object. The object was created in the test fixture; **that is not the same thing as whether this Agent really called `produce()` and delivered an Assessment**.

So the observation:

```text
AssertionError: assert not <RecordingAgent object ...>
```

only shows "the object's existence made the assertion false"; it cannot prove the system wrongly delivered a Numeric Assignment.

### 6.2 Analysis: the test was observing the wrong thing

```text
Business requirement: must not deliver a Numeric Assignment
            ↓
The test tried to prove: the Assessment Agent does not exist
            ↓
The RecordingAgent was already created while preparing test objects
            ↓
Even with no question delivered, the assertion still fails
            ↓
Root cause: the Test Oracle checked the existence of the wrong object
```

This is a **Test Oracle Bug**: what the test really cares about is "was there an actual call, was there a database side effect", not "was a dependency object constructed in advance".

The log shows the fix changed the two wrong assertions in the new test file and explicitly did not change production code. Since this round's Decision Source Pack does not include the before/after test text of `e52095f`, **the exact source of the two fixed assertions is not invented here**; later, `git show e52095f:backend/tests/test_personalized_numeric_session_sqlite_v01.py` can be used to add the final test assertions to the website.

### 6.3 What the regression evidence can prove

| Evidence | Historical observation | Appropriate conclusion |
|---|---|---|
| First 13C-2B focused run | `1 failed, 25 passed` | One test assertion failed; not a production delivery error |
| Changed two new test assertions | Record shows only tests changed, no production files | The fix scope is the Test Oracle |
| Re-ran focused tests | `26 passed` | This SQLite integration test set passes |
| Full backend regression | `324 passed` | The branch's 324 backend tests passed at the time |
| Git commit | `e52095f` | This integration verification result was committed |

**Do not write** "all external services and the real user environment were verified", and do not pass off the 324 historical test results as production run results under the latest 479 tests.

---

## 7. End-to-end execution examples: do not turn one request into a piece of "independent mastery" evidence

The following are **teaching-workflow examples constructed from the component contracts above, not a real student's history**.

### Example A: a strong-state student actively asks for a re-explanation

```text
ObjectiveState = STRONG
Request = request_explanation
            ↓
Personalized Context checks Objective and time
            ↓
Personalized Engine maps to CONCEPTUAL_REVIEW
            ↓
State-dependent allowed actions expanded if needed
            ↓
Personalized Orchestrator routes to the Professor Agent
            ↓
A concept explanation text is returned
```

The reportable fact is "`CONCEPTUAL_REVIEW` was selected and the Agent's content generation ran". This cannot change the State, and it cannot establish that the generated text was seen or understood by the student. Since the Request is a Professor-type behavior, it should not be connected to the Numeric Assignment delivery adapter.

### Example B: a student asks to do problems independently

```text
Request = try_independently
            ↓
Selected Action = INDEPENDENT_PRACTICE
            ↓
Assessment routing
            ↓
Recoverable Session checks Assessment Item / Scope / Revision
            ↓
Pending Assignment saved
            ↓
Student later submits an Attempt
            ↓
Numeric Scorer judges whether the answer is correct
            ↓
Existing Eligibility decides whether it can be used for Mastery State
```

"Asking to work independently" is only an intent record, not verification that no outside help exists. Even if the numeric answer is correct, the real source and unknown status of fields such as `assistance_level` / `prior_solution_exposure` must be kept.

### Example C: a student asks for a Transfer Assessment

The selection `REQUEST_TRANSFER → TRANSFER_ASSESSMENT` **does not mean** the current Numeric Scorer already has a reliable Transfer Item, nor that the Transfer Gate is satisfied. Later delivery must still run checks that match the Item type, alignment, approval, and item revision. An ordinary numeric question with a changed label cannot be called Transfer Evidence. The later fix for this belongs to a later Transfer Assessment development checkpoint and should be written up separately in a later chapter.

---

## 8. Architectural invariants this chapter can prove

This is not an extra design vision but the constraints that the contracts and tests of the stages above revolve around together:

1. **A request is not Mastery Evidence**: `StudentLearningRequestV01` stores a learning-activity intent and does not write `ObjectiveStateV02`.
2. **The request and no-request branches differ**: with no request, the old `DecisionEngineV01` is reused; with a request, the state-dependent teaching list can be overridden within supported actions, but later Assessment Integrity cannot be bypassed.
3. **Making a Decision ≠ executing an Action**: `PersonalizedDecisionResultV01` and `PersonalizedTeachingTurnResultV01` represent different stages.
4. **Generating Agent text ≠ delivering a persisted item**: the version and scope of a recorded Assessment Item are still checked by the existing Session / Repository.
5. **One personalized request can drive only one decision in that Adapter instance**: this is not distributed global de-duplication or identity authentication.
6. **The old Orchestrator must not make a second decision after the personalized decision**: otherwise the selection semantics of the original Student Request are lost.
7. **State and time consistency**: the request time cannot be earlier than the State Snapshot or later than the Decision; the adapter path additionally requires it to equal the Assessment Decision time.
8. **Failure must not masquerade as success**: Agent exceptions, non-strings, and blank content are rejected; this does not prove end-to-end confirmation of student-visible delivery is implemented.
9. **The personalized source at this stage is not necessarily persisted**: Adapter V0.1 explicitly does not write the Request or `selection_source` into the old Assignment.

---

## 9. Guard Casebook: which items are only preventive tests?

The following behaviors are covered by historical tests, but this batch of original material has **no matching real production incident logs**, so they are marked `GUARD` rather than `BUG`.

| Guard ID | Failure scenario covered | Test file and function |
|---|---|---|
| `GUARD-13B-01` | Request Objective does not match the State | `test_student_request_v01.py::test_request_must_match_current_objective` |
| `GUARD-13B-02` | Request earlier than the State Snapshot or later than the Decision | `test_request_cannot_be_older_than_state_snapshot`, `test_request_cannot_occur_after_decision` |
| `GUARD-13B-03` | Time missing a timezone, or arbitrary extra fields | `test_request_timestamp_must_be_timezone_aware`, `test_request_contract_rejects_unstructured_extra_fields` |
| `GUARD-13B-04` | The old Decision Context silently ignores the student request | `test_personalized_context_does_not_inherit_old_context` |
| `GUARD-13B-05` | The old policy changes unexpectedly when there is no request | `test_no_request_uses_existing_baseline` |
| `GUARD-13B-06` | A Request wrongly claimed as Agent executed or Mastery updated | `test_decision_result_does_not_claim_agent_execution`, `test_request_does_not_modify_authoritative_student_state` |
| `GUARD-13C-01` | The old Orchestrator decides again after the Personalized Decision | The single-decision structure of the `ad0f9a51` Orchestrator and related routing tests |
| `GUARD-13C-02` | Agent returns blank or invalid content; failure silently hidden | `test_invalid_agent_output_is_rejected`, `test_agent_failure_is_not_silently_replaced` |
| `GUARD-13C-03` | Explanation / Hint delivered as a Numeric Assignment | `test_explanation_request_cannot_become_numeric_assignment`, `test_hint_request_cannot_become_numeric_assignment` |
| `GUARD-13C-04` | The same Adapter consumes a request twice, or times do not match | `test_explicit_request_cannot_be_reused_for_another_turn`, `test_request_timestamp_must_match_decision` |
| `GUARD-13C-05` | "Requesting Transfer" mistaken for "Transfer succeeded" | `test_transfer_request_does_not_claim_transfer_success` |

The only item written up as a **Historical Bug** in this chapter is 13C-2B's wrong test assertion, because we have the real failure, fix, and regression output the user provided.

---

## 10. Developer learning: what software-design principles does this code teach?

### 10.1 A Domain Contract is not a Transport Contract

`StudentLearningRequestV01` is a Domain Contract for teaching intent, while the API's login session, HTTP request origin, and Student Identity belong to the outer Transport / Authorization layer. The Domain Contract checks scope and time but does not automatically authenticate the HTTP caller. This lets the local CLI and a future web app reuse the core contract, provided the outer layer really takes on authentication.

### 10.2 Composition avoids silent loss of meaning

When a new Context has a key `student_request` that the old Context lacks, do not simply inherit or hide the field in a dict passed to the old function. Explicit composition lets the function signature say "this decision must consider the Student Request" and prevents misuse of the original `DecisionEngineV01`.

### 10.3 An Adapter converts protocols; it should not copy business rules

`PersonalizedNumericSessionTurnAdapterV01` makes the new Orchestrator satisfy the old Session's `run_turn` interface, converting the needed Decision / Agent Kind / Content; but Item Revision, Assignment INSERT, and Attempt submission remain the existing Service's job. Reuse means database fixes in the old system don't have to be copied into two delivery paths.

### 10.4 A Test Oracle must observe business outcomes

A dependency object existing does not mean a business call happened. A test forbidding delivery should observe the Recording Agent's call record and/or the Assignment Repository's database state, rather than requiring that the `RecordingAgent` object not exist in the fixture at all. This chapter's real error illustrates exactly that.

### 10.5 Keep three different kinds of "success"

- `decision selected`: the function returns a valid Teaching Action.
- `content produced`: the matching Agent Port returns a string that meets the content contract.
- `assessment completed`: a database-persisted Assignment receives an Attempt, which scoring and Evidence Eligibility process further.

These three levels cannot substitute for one another; "the student really learned it" further requires later evidence on new items, retention, and transfer.

---

## 11. What control baseline to keep for future research on Jev / a Small Decision Model?

**The following are future research suggestions derived from this historical analysis; they must not be written as system capabilities implemented in 13B/13C at the time.**

If Jev or another structured Decision Model is introduced, it can keep explicit input and output boundaries: input a de-identified Objective State Snapshot, the explicit Request, the supported actions and versions; output a single suggested action and its raw result. Keep the original Policy Constraints and the existing Student State / Assessment services so the model has no right to write Mastery directly.

Experiments must separately record: whether the model's output followed the rules, which Agent was actually called, whether delivery succeeded, and the student's performance on new items and delayed practice. Comparing only "the agreement rate between the model's and the old Policy's selected actions" measures imitation, not teaching effect. The existing deterministic 13B/13C decision flow must not be rewritten as an already-trained small model or real Jev calls.

---

## 12. Traceable sources, gaps, and re-check commands

**Historical source pack**: `decision_orchestration_history_source_pack.zip`. This chapter mainly cites these paths in the ZIP:

```text
0e9b77b1/backend/app/services/decision/student_request_v01.py
0e9b77b1/backend/tests/test_student_request_v01.py
0e9b77b1/docs/07_personalized_decision_policy_v0.1.md
5aec0609/backend/app/services/decision/personalized_engine_v01.py
5aec0609/backend/tests/test_personalized_engine_v01.py
5aec0609/docs/08_personalized_decision_selection_v0.1.md
ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py
ad0f9a51/backend/tests/test_personalized_turn_orchestrator_v01.py
ad0f9a51/docs/09_personalized_teaching_turn_v0.1.md
9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py
9ea307b7/backend/tests/test_personalized_numeric_session_adapter_v01.py
9ea307b7/docs/10_personalized_numeric_session_adapter_v0.1.md
```

**Real error log**: the 13C-2B terminal record the user provided earlier: `1 failed, 25 passed → two test assertions fixed → 26 passed → 324 passed → e52095f`. The committed version of this test is not included in this chapter's Decision Source Pack; the test text of `e52095f` and `docs/11_personalized_numeric_sqlite_integration_v0.1.md` are still needed to give the complete before/after assertion diff. **The confirmed original failing assertion can be cited; unknown final assertions cannot be made up.**

Read-only re-check examples:

```bash
# View historical files only; do not write any version back to the working tree
git show 0e9b77b1:backend/app/services/decision/student_request_v01.py
git show 5aec0609:backend/app/services/decision/personalized_engine_v01.py
git show ad0f9a51:backend/app/services/decision/personalized_turn_orchestrator_v01.py
git show 9ea307b7:backend/app/services/decision/personalized_numeric_session_adapter_v01.py
git show e52095f:backend/tests/test_personalized_numeric_session_sqlite_v01.py
```

**Conclusion**: 13B introduced student requests and deterministic action selection that do not change Mastery; 13C connected action selection to real Agent Ports and the existing Recoverable Numeric Session; 13C-2B's original integration log confirms one Test Oracle bug was fixed. The later Assistance Presentation, recoverable CLI, and Provenance Snapshot belong to later stages and should be examined separately in the next chapter.

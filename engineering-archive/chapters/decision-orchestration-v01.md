# URPP Engineering Archive · Reply 5 / 10
## Logical Decision Engine, Teaching Orchestration, and the Personalized Session Adapter

> **Archive nature: historical source reconstruction and after-the-fact technical analysis.** This chapter is based on the code, tests, and design documents of eight Git checkpoints in `decision_orchestration_history_source_pack.zip`, supplemented by the previously saved original 13C-2B test-failure and fix logs. Function names and fields are recorded as in the historical versions. **This chapter is not a complete audit of the current HEAD, and it does not describe defensive tests as production incidents that happened.**
>
> **Historical placement:** Design 01D, plus the later work explicitly labeled Implementation 13B-1, 13B-2, 13C-1, and 13C-2A. How these map onto the original overall Implementation 0–13 roadmap is still unverified. **The eight commits here are historical checkpoints, not eight complete Implementations.**

## Introduction: why this chapter must start from the difference between "selecting" and "executing"

The previous chapter covered `Student Response → Scoring → Evidence → ObjectiveStateV02`. This chapter covers the other half of the loop: `ObjectiveStateV02 → DecisionContext → TeachingAction → Agent → Content`. The two halves are not the same function: scoring an answer does not automatically make an Agent's explanation new learning evidence, and a model choosing `TRANSFER_ASSESSMENT` does not automatically prove the student completed a transfer.

This chapter strictly distinguishes six moments: **State produced, action allowed, action selected, Agent called, Assessment delivered, Attempt accepted and State re-estimated**. The historical implementation added these capabilities one at a time; early versions must not be described as the later complete recoverable teaching session.

**One thread:**

```text
Computed ObjectiveStateV02
   → DecisionContextV01 (time, decision_id)
   → PedagogicalPolicyV01.allowed_actions() (state-dependent candidate set)
   → RuleBasedControllerV01.propose() / replaceable Controller
   → DecisionEngineV01.decide() (checks the proposal, falls back if needed)
   → DecisionResultV01 (a selection, not an executed event)
   → TeachingTurnOrchestratorV01.run_turn()
   → route to the Professor or Assessment Agent by selected_action
   → TeachingTurnResultV01 (returned content, not learning evidence)
   → [later versions: stored item binding, pending question, Attempt, and state recomputation]
```

## 1. Eight Git checkpoints: when did each component appear?

| Commit prefix | Historical objects in the source pack | Confirmable change | Capability that still cannot be claimed |
|---|---|---|---|
| `1b26d215` | `models_v01.py`, `policy_v01.py`, `engine_v01.py`, matching tests, `docs/03d_logical_decision_engine.md` | Rule-based Controller, allowed-action list, Proposal/Result, and a restricted fallback | No real LLM, Agent execution, answer submission, or Session persistence |
| `9151b227` | `turn_orchestrator_v01.py`, tests | Dispatches a selected action to one of two Agent Ports (Professor/Assessment); returned content must not be treated as evidence | Cannot guarantee the student actually saw the content; no Attempt submission |
| `98f08802` | `numeric_teaching_session_v01.py`, tests | Records a Pending Numeric Assessment in memory; binds the stored item, Revision, Student/Session, and existing Attempt IDs | Pending is not database persistence; cannot be recovered after a process restart |
| `99c983b8` | Later version of the same Session file and new tests | Adds `AssessmentDeliveryV01`, a server-side Assignment ID, structured returns, keeping the old interaction entry point | The Assignment ID is not a login credential; Pending is still in memory in this version |
| `0e9b77b1` | `student_request_v01.py`, tests, `docs/07_*` | 13B-1: explicit structured learning requests and a separate `PersonalizedDecisionContextV01` | Defines requests only; does not select or execute personalized actions |
| `5aec0609` | `personalized_engine_v01.py`, tests, `docs/08_*` | 13B-2: baseline when there is no request; with a request, maps to an action, records the source, and expands the baseline action set if needed | Does not mean an item exists, does not deliver items, does not grant mastery |
| `ad0f9a51` | `personalized_turn_orchestrator_v01.py`, tests, `docs/09_*` | 13C-1: one personalized decision calls only the matching single Agent; the original request is passed to the Agent | No persisted Assignment, real LLM, learning evidence, or full session |
| `9ea307b7` | `personalized_numeric_session_adapter_v01.py`, tests, `docs/10_*` | 13C-2A: an Adapter connects personalized teaching turns to the existing Recoverable Numeric Session interface | The Adapter itself does not store the personalized decision source, and its unit tests are not a restart integration test |

**About historical scope:** these are historical versions recovered with `git show <commit>:<file>`. The `RecoverableNumericSessionServiceV01` referenced by `9ea307b7` is not in this round's source pack, so this chapter analyzes only the call contract directly visible in the Adapter and does not invent that Service's internal transaction implementation. The previously saved 13C-2B log proves that another SQLite integration test once had a wrong test assertion; it cannot replace the full development logs of these eight commits.

## 2. Decision Engine V0.1: the model "suggests" an action, the policy "allows" actions

### 2.1 How the six actions are divided

The historical `TeachingActionV01` enum defines six names:

| `TeachingActionV01` | Raw value | Early routing |
|---|---|---|
| `DIAGNOSTIC_ASSESSMENT` | `diagnostic_assessment` | Assessment Agent |
| `CONCEPTUAL_REVIEW` | `conceptual_review` | Professor Agent |
| `CONCEPTUAL_HINT` | `conceptual_hint` | Professor Agent |
| `INDEPENDENT_PRACTICE` | `independent_practice` | Assessment Agent |
| `SELF_EXPLANATION` | `self_explanation` | Professor Agent |
| `TRANSFER_ASSESSMENT` | `transfer_assessment` | Assessment Agent |

An action's **name is not a guarantee of execution**. For example, `INDEPENDENT_PRACTICE` is a type of teaching activity and cannot prove the student used no extra tools; `TRANSFER_ASSESSMENT` is an intended action and cannot prove a successful knowledge transfer happened. The early Orchestrator only dispatches these six actions and produces no Evidence usable directly for Mastery.

### 2.2 DecisionContextV01: who is responsible for student state?

`DecisionContextV01` holds `decision_id`, an existing `ObjectiveStateV02`, and `requested_at`. The file comment says explicitly: the Context is built by the application layer, and the Decision Model **must not build Student State on its own**. `requested_at` must be timezone-aware and satisfy:

```python
if self.requested_at < self.objective_state.as_of:
    raise ValueError(
        "Decision cannot precede its Student State snapshot."
    )
```

This is not about tidy timestamps; it fixes a causal-order constraint: **a teaching choice must not be labeled as happening before the state snapshot it is based on.** In a real error in the later CLI, a wrong recovery time and the next turn's Decision time violated this constraint; the root cause was not that this check should be removed, but that the call chain used contradictory times.

`model_config = ConfigDict(frozen=True, extra="forbid")` keeps these Pydantic contracts constrained against ordinary assignment and undeclared fields; but this by itself is not authentication or an isolation boundary against a malicious process. Referencing an `ObjectiveStateV02` also does not automatically prove the caller may read a real student's data.

### 2.3 PedagogicalPolicyV01: the early allowed-action sets

The **exact mapping** of the original `allowed_actions()` is:

| `state.state` | Original `allowed_actions()` return value (order preserved) |
|---|---|
| `UNKNOWN` | `DIAGNOSTIC_ASSESSMENT`, `CONCEPTUAL_REVIEW`, `INDEPENDENT_PRACTICE` |
| `EMERGING` or `DEVELOPING` | `CONCEPTUAL_REVIEW`, `CONCEPTUAL_HINT`, `INDEPENDENT_PRACTICE`, `SELF_EXPLANATION` |
| `COMPETENT` | `INDEPENDENT_PRACTICE`, `SELF_EXPLANATION`, `TRANSFER_ASSESSMENT` |
| `STRONG` | `SELF_EXPLANATION`, `TRANSFER_ASSESSMENT`, `INDEPENDENT_PRACTICE` |
| Other labels | `ValueError("Unsupported Student State. No teaching action allowed.")` |

This list is a **teaching-policy baseline**, not an optimal teaching order validated by randomized experiments. The comments in the original `policy_v01.py` say explicitly that these rules are engineering baselines. The order of `allowed_actions` also matters: when the Controller cannot provide an allowed action, the fallback uses its own preference and, if necessary, the first action in the set.

### 2.4 RuleBasedControllerV01: why can two UNKNOWN states choose different actions?

The core source branch is:

```python
if (
    state.state == ObjectiveStateLabel.UNKNOWN
    and state.distinct_assessment_count == 0
):
    preferred = TeachingActionV01.DIAGNOSTIC_ASSESSMENT
elif state.state == ObjectiveStateLabel.UNKNOWN:
    preferred = TeachingActionV01.INDEPENDENT_PRACTICE
elif state.state in {
    ObjectiveStateLabel.EMERGING,
    ObjectiveStateLabel.DEVELOPING,
}:
    preferred = TeachingActionV01.CONCEPTUAL_HINT
elif state.state in {
    ObjectiveStateLabel.COMPETENT,
    ObjectiveStateLabel.STRONG,
}:
    preferred = TeachingActionV01.TRANSFER_ASSESSMENT
else:
    preferred = allowed_actions[0]
```

So `UNKNOWN + distinct_assessment_count == 0` selects `DIAGNOSTIC_ASSESSMENT`, and `UNKNOWN + distinct_assessment_count > 0` selects `INDEPENDENT_PRACTICE`. This is based only on fields visible in the code and **does not mean the system has decided how much help the student needs**. For example, after an Attempt is excluded because its assistance is unknown, how the count changes depends on the State Estimator's evidence-counting semantics and cannot be inferred from this branch alone.

### 2.5 DecisionEngineV01 failure handling

```text
Existing DecisionContext
  → policy.allowed_actions(context)
  → controller.propose(context, allowed)
       ├─ proposal is not a DecisionProposalV01 → fallback
       ├─ proposed action not in allowed         → fallback
       ├─ controller raises TimeoutError         → fallback
       └─ proposal valid                         → keep proposal
  → check again that the fallback result is allowed
  → DecisionResultV01
       [decision_id, selected_action, allowed_actions,
        controller_version, fallback_used, policy_version]
```

The original code **catches only `TimeoutError`**. If the Controller raises any other exception, the fallback is not used automatically; the exception propagates. This avoids disguising every implementation error as "model temporarily unavailable". It does not implement a real timer: "timeout fallback" means handling a `TimeoutError` the Controller has already raised, not that the Engine can forcibly interrupt a slow call.

Historical tests give concrete regression points for this design: `test_disallowed_proposal_triggers_fallback`, `test_controller_timeout_triggers_fallback`, `test_unstructured_output_triggers_fallback`, `test_decision_cannot_precede_state_snapshot`, and `test_decision_does_not_modify_student_state`. These are **defensive tests**; the source pack does not show them really failing before the commit.

### 2.6 The Controller can be replaced later, but cannot quietly change the evidence system

The minimal entry point of `LogicalDecisionController(Protocol)` is:

```python
def propose(
    self,
    context: DecisionContextV01,
    allowed_actions: tuple[TeachingActionV01, ...],
) -> DecisionProposalV01:
    ...
```

The original `docs/03d_logical_decision_engine.md` explicitly proposes that it could later be replaced by a NanoJev Controller, but this historical checkpoint **did not train or connect NanoJev/Jev**. This is an interface designed for a replaceable Controller, not evidence that a model went live. Even if replaced later, the model can only return a candidate teaching action; it cannot create Evidence, modify State, or bypass assessment conditions.

## 3. Orchestrator V0.1: one selection is dispatched to exactly one Agent

### 3.1 Responsibilities of three objects

`DecisionContextBuilderV01.build()` combines an existing State, `decision_id`, and `requested_at` into a contract. It checks the types of the passed objects and that IDs are non-empty; **it does not authenticate or fetch State from a Repository** and relies on the upstream caller to supply trusted data.

`TeachingTurnOrchestratorV01.run_turn()` calls `DecisionEngineV01.decide()`, checks the returned result's ID and selected action, then dispatches by set:

```python
ASSESSMENT_ACTIONS = frozenset({
    TeachingActionV01.DIAGNOSTIC_ASSESSMENT,
    TeachingActionV01.INDEPENDENT_PRACTICE,
    TeachingActionV01.TRANSFER_ASSESSMENT,
})

PROFESSOR_ACTIONS = frozenset({
    TeachingActionV01.CONCEPTUAL_REVIEW,
    TeachingActionV01.CONCEPTUAL_HINT,
    TeachingActionV01.SELF_EXPLANATION,
})
```

`TeachingAgentPortV01.produce(context=..., decision=...) -> str` is a **Port / Protocol**. The tests at the time used test doubles such as `RecordingAgent`; there is no evidence of a connected production LLM. The returned `TeachingTurnResultV01` contains `decision`, `agent_kind`, and `content`, and a successful result is refused when the content is empty, not a string, or the Agent raises.

### 3.2 How the original tests prove routing does not cross wires

`test_unknown_state_routes_diagnostic_to_assessment_agent`: builds an UNKNOWN State with no evidence, expects `DIAGNOSTIC_ASSESSMENT`, and checks the Assessment Agent is called once and the Professor Agent zero times.

`test_conceptual_review_routes_to_professor_agent`: injects a Controller that always proposes `CONCEPTUAL_REVIEW` and checks the Professor Agent is called once and the Assessment Agent zero times.

`test_disallowed_controller_uses_policy_fallback`: an illegal Transfer proposal falls back to the Diagnostic allowed in the unknown state, still executed by the Assessment Agent.

`test_agent_failure_is_not_silently_replaced`: when the Assessment Agent explicitly raises, the Orchestrator does not invent other teaching content to claim the turn succeeded.

`test_teaching_turn_does_not_update_student_state`: compares `model_dump(mode="json")` before and after to verify the normal path did not change the passed State.

### 3.3 Do not overstate "cannot modify State"

The original implementation saves and compares JSON snapshots of the State before and after the Controller and Agent calls, raising an error if it changed; this is an **in-process check against accidental modification**. It is not authentication, non-repudiation, or database permission control, and cannot prevent other external side effects that already happened. Returned `content` means the Port produced content; it does not guarantee the browser displayed it, the student read it, or learning happened.

## 4. From single teaching turns to "selected item – pending question – stored Attempt" binding

### 4.1 The initial NumericTeachingSessionV01 in `98f08802`

This historical version maintains in memory:

```python
self._state = estimate_objective_state([], ...)
self._accepted_attempt_ids: list[str] = []
self._used_decision_ids: set[str] = set()
self._pending: PendingNumericAssessmentV01 | None = None
```

`start_numeric_turn()` receives the server-selected `assessment_item_id`, `item_revision`, `decision_id`, and `requested_at`, loads the specified Revision from the Repository, checks Course/Objective, Objective Alignment, and time, then runs the Orchestrator once. A Pending is recorded only if the action is an Assessment, it routes to the Assessment Agent, and `turn.content == item.prompt`.

**Why compare the exact prompt?** It is this historical version's temporary engineering constraint for matching free-text Agent output to the stored item. If the Agent were allowed to generate a different question on the fly while the Attempt was still scored against the existing Item's Rubric, the scoring target would be mismatched. The exact prompt is a very narrow compatibility measure, not complete delivery verification; it cannot prove the user actually saw the question and does not suit a future UI with rendering differences.

`accept_stored_attempt(attempt_id, as_of)` validates in order: a Pending must exist; the Attempt has not already been accepted; the Attempt is loaded from the Repository; Student/Course/Objective/Session match; Item ID and Revision equal the Pending's; `submitted_at >= pending.requested_at`; `as_of` is not earlier than this submission or the current State. It then re-estimates State from the accepted attempt IDs with the existing PersistedNumericAssessmentService; **only after re-estimation succeeds** does it update the in-memory accepted IDs and State and clear the Pending.

This shows that the Repository storing Attempts and the Session maintaining a Pending are different layers: in this historical version, "Persisted Numeric Assessment" does not mean the Session itself could recover after a restart. The original module docstring declares directly that it is `in-memory session coordination`.

### 4.2 Why `99c983b8` added a structured AssessmentDelivery

The historical diff clearly shows the addition:

```python
class AssessmentDeliveryV01(BaseModel):
    assignment_id: str
    decision_id: str
    assessment_item_id: str
    item_revision: int
    prompt: str
    selected_action: TeachingActionV01
    assigned_at: datetime
```

The new `start_structured_numeric_turn()` still calls the Agent, but the structured result's `prompt` comes from the stored `item.prompt`; **the Agent's free text does not replace the question**. It generates `token_urlsafe(24)` as the Assignment ID for this in-memory Pending. `accept_stored_attempt(..., assignment_id=...)` checks that ID on the structured path; the old path keeps its compatible behavior without an ID.

```text
Old path: Agent text == stored prompt → Pending (no Assignment ID)
New path: Agent called → Delivery.prompt = stored prompt
        → Pending (with Assignment ID)
        → submission must match the Assignment ID
```

In this version the Assignment ID is **a random identifier linked to this Pending**, not user authentication, a server-side persistence guarantee, or end-to-end anti-cheating proof. Historical tests cover `test_structured_delivery_uses_stored_prompt`, `test_structured_submission_requires_assignment_id`, `test_wrong_assignment_does_not_consume_pending_turn`, `test_previous_assignment_cannot_complete_new_turn`, and old-path compatibility.

### 4.3 Three different bindings; do not mix them up

1. **Item binding**: the submitted Attempt must correspond to the specified Assessment Item and its original Revision.
2. **Session binding**: Student, Course, Objective, and Session must match the task currently waiting.
3. **Assignment binding**: on the structured path, the correct current Assignment ID must also be submitted.

Missing any of these weakens protection against wrongly linked records, but none of them is real-world identity verification; the in-memory Pending variable also has no automatic transactional persistence.

## 5. 13B-1: a student's "request" is not learning state

`0e9b77b1` introduces six `StudentLearningRequestKindV01` values:

```text
request_explanation / try_independently / request_hint
request_diagnostic / request_self_explanation / request_transfer
```

`StudentLearningRequestV01` stores `objective_id`, an enum `request_kind`, and a timezone-aware `requested_at`. It does not hand free text to a model for arbitrary interpretation; it is a limited structured contract.

`PersonalizedDecisionContextV01` **composes** an existing `DecisionContextV01` and an optional request rather than inheriting from the old Context, so the old engine cannot silently receive "a new object that looks like the old Context" and ignore the student request. It rejects a mismatched Objective, and a request time earlier than the State or later than the Decision.

This historical stage only added contracts; it did not change the original Action Selection. The original `docs/07_*` states explicitly that student requests must not be interpreted as mastery evidence, and that cited research does not validate this project's specific thresholds and strategy effects.

## 6. 13B-2: why does the personalized engine allow expanding the baseline action set?

### 6.1 No-request branch

When `student_request is None`, `PersonalizedDecisionEngineV01` passes the `DecisionContextV01` to the original `DecisionEngineV01(RuleBasedControllerV01())` and records `selection_source=baseline`, `selected_for_request=False`, `request_expanded_allowed_actions=False`. The test `test_no_request_uses_existing_baseline` checks that the two complete DecisionResults are identical.

### 6.2 Request branch: this really does change how the early Policy is used

The request mapping is:

| Request | Action |
|---|---|
| `REQUEST_EXPLANATION` | `CONCEPTUAL_REVIEW` |
| `TRY_INDEPENDENTLY` | `INDEPENDENT_PRACTICE` |
| `REQUEST_HINT` | `CONCEPTUAL_HINT` |
| `REQUEST_DIAGNOSTIC` | `DIAGNOSTIC_ASSESSMENT` |
| `REQUEST_SELF_EXPLANATION` | `SELF_EXPLANATION` |
| `REQUEST_TRANSFER` | `TRANSFER_ASSESSMENT` |

If the requested action is not in the baseline `PedagogicalPolicyV01.allowed_actions`, the personalized engine **appends it to the personalized result's `allowed_actions`**, marks `request_expanded_allowed_actions=True`, and uses its own `policy_version=personalized-request-policy-v0.1`.

This is a real and important architectural change: **one can no longer say "no Controller can ever expand the allowed action set under any circumstances".** Strictly speaking, the Controller inside the original `DecisionEngineV01` cannot expand its Policy candidate set; `PersonalizedDecisionEngineV01` is a separate, deliberately designed policy path that, to respond to an explicit student request, can expand the **state-dependent list of teaching activities**. It cannot thereby change evidence admission, scoring, existing State, item alignment, Session registration, or database integrity. "Allowing a student to request a Transfer Assessment" must never be written as "the student has proven they can transfer independently".

**Source example:** a synthetic `STRONG` State requests `REQUEST_EXPLANATION`; the baseline `STRONG` action set has no `CONCEPTUAL_REVIEW`; the personalized result appends and selects it. The historical test `test_strong_student_can_request_conceptual_review` verifies this exact example. That State is a synthetic object built by the test, never a real student's mastery record.

### 6.3 Why record the source?

The result includes `selection_source`, `selected_for_request`, `request_expanded_allowed_actions`, and `selection_reason`. These fields only explain **why the action was selected**, and `selection_reason` states explicitly `Action execution has not yet occurred`. They are not proof that teaching content was delivered, and this component does not automatically write them to a persistent database.

## 7. 13C-1: the personalized Orchestrator must not call the old Orchestrator to decide again

`PersonalizedTeachingTurnOrchestratorV01` uses the existing `DecisionContextBuilderV01` to build the base Context, merges the request with `PersonalizedDecisionContextV01`, calls `PersonalizedDecisionEngineV01.decide()` **exactly once**, and then selects the matching Agent. The Agent receives the full personalized Context and the decision result with its source, not just `selected_action`.

Why not call the old `TeachingTurnOrchestratorV01`? Because the old Orchestrator would internally call the original DecisionEngine again, possibly dropping the student request in the second decision so that the selected action and the executed action disagree. This design reason is stated explicitly in `docs/09_personalized_teaching_turn_v0.1.md` and in the source comments.

The new and old Ports are not automatically compatible: the new `PersonalizedTeachingAgentPortV01.produce()` receives `PersonalizedDecisionContextV01` and `PersonalizedDecisionResultV01`; the old Port receives the original Context/DecisionResult.

Historical tests include: baseline Assessment routing kept when there is no request; a `STRONG` state requesting explanation routed to the Professor; an independent-practice request routed to Assessment; a wrong Objective rejected before calling the Agent; empty content and Agent exceptions not replaced; State not rewritten.

**Boundary:** this is still a single content call and produces no new Numeric Assignment, Attempt, or Evidence. Executing `REQUEST_HINT` does not automatically create a trusted Assistance Log; that was implemented separately in a later stage.

## 8. 13C-2A: how the Adapter reuses the existing Recoverable Numeric Session

The later system already had `RecoverableNumericSessionServiceV01`. Instead of copying another set of persistent delivery, submission, and state-estimation logic, the new Adapter implements the interface the old session expects:

```python
def run_turn(
    self,
    objective_state: ObjectiveStateV02,
    *,
    decision_id: str,
    requested_at: datetime,
) -> TeachingTurnResultV01:
    ...
```

An Adapter instance binds one optional `StudentLearningRequestV01`. If there is an explicit request, the action is derived from `REQUEST_ACTION_MAP` at initialization; if it is not in `ASSESSMENT_ACTIONS` (for example a request for a concept explanation or a hint), it is immediately rejected for **Numeric Assignment Delivery**. This does not mean the whole Professor system cannot give hints; it means **a hint path must not be disguised as an Assignment path that requires submitting a numeric answer**.

When a valid request comes in, the Adapter also checks that the Objective and request time exactly equal the current decision time, calls the personalized Orchestrator once, and requires the final action to be an Assessment actually routed to the Assessment Agent. It then narrows the new result to the old `TeachingTurnResultV01` and hands it back to the Recoverable Session's existing flow.

```text
Bound Student Request (optional)
  → PersonalizedNumericSessionTurnAdapterV01
  → PersonalizedTeachingTurnOrchestratorV01 (one Decision + one Agent)
  → PersonalizedTeachingTurnResultV01
  → Adapter verifies Assessment-only
  → TeachingTurnResultV01 (old interface shape)
  → RecoverableNumericSessionServiceV01 (later delivery, storage, answering)
```

**Real capabilities and limits:** the Adapter does not deliver items separately, does not persist the Session itself, does not modify Student State, and does not authenticate the student. When converting to the old result it loses personalized source fields such as `selection_source` and `request_expanded_allowed_actions`; the source states directly that this source information is kept only in the personalized turn's in-memory result, and the old Assignment schema does not gain persistent provenance from it.

An explicit request can be used only once by the same Adapter; trying to reuse it raises `RuntimeError`. `self._explicit_request_used=True` is set **before** the Orchestrator is called, which means that if a call fails downstream, the Adapter may still treat the request as used; the source docs recommend building a new Adapter/Service for a new request and having the upper layer reuse the existing persistent Repository and Session identity. This is a constraint visible in the code; it does not mean we observed a real user losing a request because of it.

## 9. Debugging Casebook: one real failure + several Guards that must not pose as incidents

### BUG-13C-2B-001: a wrong test assertion that treated an object's existence as the Agent actually running

**Source type: the previously saved original 13C-2B user terminal test log, not a test file in this round's ZIP.** Original output: `1 failed, 25 passed`. The failing test was `test_explanation_request_cannot_issue_numeric_assignment`; after the expected rejection of an explanation request, the test executed:

```python
assert not stack.last_assessment_agent
```

In fact `stack.last_assessment_agent` already referenced a `RecordingAgent`, so the assertion failed. **An object being constructed does not mean that Agent was called, let alone that a Numeric Assignment was issued.** The original follow-up fix record shows that only the two wrong assertions in the new test file were adjusted, with no production code change; re-running the focused tests gave `26 passed`, the full backend `324 passed`, and `e52095f` was committed. It is therefore classified as a **test-oracle bug (wrong choice of test assertion)** and must not be written as "the production system wrongly issued a Numeric Assignment".

Lesson: tests should check `agent.calls`, whether a real Assignment exists, and the actual execution path, rather than relying on whether `last_assessment_agent` is `None` to prove business behavior. The exact before/after diff of the two new assertions is not in this round's ZIP; it will be added once the original commit's historical code is found.

### GUARD-01D-001: an illegal Transfer proposal

`test_disallowed_proposal_triggers_fallback` builds an UNKNOWN State and has the Controller propose `TRANSFER_ASSESSMENT`. The original Engine uses the rule-based fallback and returns the allowed Diagnostic. **This is a defensive test, not a real teaching misjudgment incident.**

### GUARD-01D-002: model output not a contract; call timeout

`test_unstructured_output_triggers_fallback` and `test_controller_timeout_triggers_fallback` verify that when the input is a plain dict or the Controller raises `TimeoutError`, no illegal proposal is sent to the Agent. The source has no real external model call and measured no real timeout.

### GUARD-01D-003: free text replacing the stored item

The early `test_unmatched_agent_prompt_is_rejected` rejects a delivery whose Agent text differs from the stored prompt; the later `test_structured_delivery_uses_stored_prompt` verifies that the structured Delivery uses `item.prompt` directly. These two tests record a design upgrade but cannot prove an incident where "the student answered one question and the database graded another" ever happened.

### GUARD-13B-001: request before State / after Decision / wrong Objective

The related checks are in `test_student_request_v01.py`. They protect time semantics and prevent learning preferences for another Objective from being linked to the current decision; they are not real account authorization checks.

### GUARD-13C-001: a double decision losing the request

`docs/09_*` explains explicitly why the new Orchestrator does not call the old Orchestrator to decide again. This is a **preventive architectural reason** recorded in the design document, not a real incident caused by an observed double decision.

### GUARD-13C-002: a Professor request entering a Numeric Assignment

`test_explanation_request_cannot_become_numeric_assignment` and `test_hint_request_cannot_become_numeric_assignment` are covered directly by the 13C-2A Adapter tests. The real 13C-2B assertion bug is recorded separately as BUG-13C-2B-001; do not merge the two into a "production routing error".

## 10. Boundary table of interfaces and fields: read this before changing code

| Object / boundary | What it can do | What it must not be claimed to do |
|---|---|---|
| `ObjectiveStateV02` | Stores a state estimate and known evidence statistics | Not created by the Decision Model as a real student mastery conclusion |
| `DecisionContextV01` | Combines State, decision_id, and time | Does not authenticate the State or student identity |
| `PedagogicalPolicyV01` | Returns the baseline candidate set to the original Controller | Not a system-wide, permanently non-extensible action permission system |
| `DecisionProposalV01` | Proposes one teaching action | Does not prove the action was executed |
| `DecisionResultV01` | Records the final action, candidate set, fallback, policy version | Produces no Evidence and does not guarantee an Assignment exists |
| `TeachingTurnResultV01` | Says a Port returned content once | Does not prove the user saw, understood, or mastered the content |
| `PendingNumericAssessmentV01` | Binds the current pending question in memory | Not a permanently persisted Assignment or a login credential |
| `AssessmentDeliveryV01` | Structurally represents this delivery with the stored item and a random ID | Does not prove the browser displayed it or that the student personally answered |
| `StudentLearningRequestV01` | Expresses a structured student learning preference | Is not evidence of correctness, independence, or Mastery |
| `PersonalizedDecisionResultV01` | Marks whether the selection followed a request and whether the baseline set was expanded | Does not promise the Agent ran successfully or that teaching was effective |
| `PersonalizedNumericSessionTurnAdapterV01` | Adapts one personalized Assessment turn to the old session interface | Does not persist full request provenance or replace existing Session logic |

## 11. How to explain contradictions between old and new designs, without forcing them to agree

**Apparent contradiction A:** `1b26d215` says the Controller must not enlarge the allowed set; `5aec0609` adds the student-specified action to the allowed set. **Explanation:** the former describes **the replaceable Controller inside the old DecisionEngine**; the latter is a separately defined **personalized policy path**. The two Policy Versions must be clearly marked; if they are later unified into one Policy Gateway, "which teaching activities a student request may expand" and "which safety, assessment, and authorization conditions must never be expanded" should be written as different rules, rather than pretending nothing ever changed.

**Apparent contradiction B:** `INDEPENDENT_PRACTICE` can be selected, while the Assistance Level may still be unknown. **Explanation:** a TeachingAction is only the selected teaching activity and does not automatically produce verified independence conditions. The actual answer provenance is decided by the later Attempt, Assistance records, and Evidence Eligibility.

**Apparent contradiction C:** the Session is called Numeric *Teaching*, but early on it only supported Assessment turns. **Explanation:** this historical version of `start_numeric_turn()` requires a selected Assessment Action; Professor-only turns are explicitly out of scope. A later Professor Agent path does not mean it was already connected through the early Numeric Session.

**Apparent contradiction D:** 13C-2A connects to a "Recoverable Session", but this round's ZIP has no code for that Service. **Explanation:** the Adapter source can only confirm that it calls the referenced Service interface; the concrete persistence, recovery, and transaction implementation belongs to historical source files in other commits and must be checked separately in a later source pack.

## 12. Source index, reproducible checks, and unrecovered facts

The **primary source code** for this chapter comes from these exact paths in the uploaded source pack:

```text
1b26d215/backend/app/services/decision/{models_v01,policy_v01,engine_v01}.py
1b26d215/backend/tests/test_decision_engine_v01.py
1b26d215/docs/03d_logical_decision_engine.md
9151b227/backend/app/services/decision/turn_orchestrator_v01.py
9151b227/backend/tests/test_turn_orchestrator_v01.py
98f08802/backend/app/services/decision/numeric_teaching_session_v01.py
98f08802/backend/tests/test_numeric_teaching_session_v01.py
99c983b8/backend/app/services/decision/numeric_teaching_session_v01.py
99c983b8/backend/tests/test_numeric_teaching_session_v01.py
0e9b77b1/backend/app/services/decision/student_request_v01.py
0e9b77b1/docs/07_personalized_decision_policy_v0.1.md
5aec0609/backend/app/services/decision/personalized_engine_v01.py
5aec0609/docs/08_personalized_decision_selection_v0.1.md
ad0f9a51/backend/app/services/decision/personalized_turn_orchestrator_v01.py
ad0f9a51/docs/09_personalized_teaching_turn_v0.1.md
9ea307b7/backend/app/services/decision/personalized_numeric_session_adapter_v01.py
9ea307b7/docs/10_personalized_numeric_session_adapter_v0.1.md
```

To restore code, use `git show <full-hash>:<file>`; when checking historical versions, do not substitute the same-named module at the current HEAD for the past implementation. A commit prefix can be resolved to the full hash in the local repository with `git rev-parse --verify <prefix>^{commit}`.

**Still missing and must be marked honestly:** whether more tests failed at these eight checkpoints during real development, the original failing commands, and complete fix steps; the exact before/after diff of the two 13C-2B assertion changes; the full historical implementations of `RecoverableNumericSessionServiceV01` and the SQLite Assignment Repository; how these stages map onto the original overall Implementation 0–13 roadmap; and real experiments on the use and effect of external Jev/NanoJev. These gaps must not be filled in automatically as "what happened at the time".

## 13. Five conclusions to remember before the next chapters

1. **The State Estimator decides what existing evidence supports; the Decision Engine decides the next teaching action.** Neither can replace the other.
2. **"Action selected" is not "action executed", let alone "the student has learned it".** Distinguish layer by layer along Agent, Delivery, Attempt, and Scoring.
3. **The early baseline restricts the Controller's action proposals; 13B's explicit student requests introduced an auditable personalized expansion.** This change did not authorize modifying Mastery evidence.
4. **13C's Adapter reuses the old session's persistence boundary instead of quietly copying another set of database logic.** But it does not keep the full personalized source when narrowing the result, a limitation the source admits explicitly.
5. **The archive must faithfully separate historical failures from preventive Guards.** The only real failure reconstructed in this chapter, with the help of earlier original terminal logs, is 13C-2B's wrong test assertion; the other defensive items listed must not be written as system incidents that happened.

---

**Chapter delivery status:** the Decision/Orchestration technical chapter and version-difference analysis for the eight historical checkpoints are complete; coverage of historical bugs is limited by the availability of original failure logs. The next chapter continues recovering the persistent Session, Assignment, and end-to-end recovery mechanisms, without assigning them in advance to Implementation numbers that have not been confirmed.

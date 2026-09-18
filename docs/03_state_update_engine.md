# Design 01B — Student State Update Engine

Status: **V0.1 Design Candidate**

Branch:

```text
design/state-update-engine
```

---

# 1. Purpose

The State Update Engine converts accumulated learning evidence into a
current estimate of a student's ability on one Learning Objective.

The core transformation is:

```text
EvidenceEvent[]
      ↓
Validate + Filter
      ↓
Weight Evidence
      ↓
Aggregate Evidence
      ↓
Estimate Confidence
      ↓
Apply State Gates
      ↓
ObjectiveState
```

The engine does **not** decide how to teach.

It only answers:

> Given all valid evidence for this Learning Objective,
> what can URPP currently justify believing about the student's state?

---

# 2. Design Principle

The fundamental record is:

```text
Evidence History
```

The derived estimate is:

```text
ObjectiveState
```

Therefore:

```text
Evidence History
      ↓
State Estimator
      ↓
ObjectiveState
```

and never:

```text
LLM opinion
      ↓
ObjectiveState
```

---

# 3. Core Invariants

The V0 State Update Engine MUST satisfy the following.

## 3.1 Deterministic

The same valid evidence set and the same policy version must always
produce the same ObjectiveState.

```text
same evidence
+
same policy
=
same state
```

## 3.2 Order independent

Evidence ordering must not change the result.

```text
[E1, E2, E3]
```

and

```text
[E3, E1, E2]
```

must produce the same state.

## 3.3 Duplicate safe

The same `evidence_id` must never be counted twice.

## 3.4 Evidence traceable

Every state estimate must be explainable through evidence IDs.

## 3.5 Unknown is valid

Insufficient evidence must return:

```text
UNKNOWN
```

rather than manufacturing confidence.

## 3.6 State may move in both directions

Valid transitions include:

```text
DEVELOPING
    ↓
COMPETENT
```

and:

```text
STRONG
    ↓
COMPETENT
```

when new evidence supports that update.

## 3.7 Absence of evidence is not negative evidence

URPP must not assume that a student forgot something merely because
the concept has not been observed recently.

Recency reduces certainty.

It does not create a failure event.

---

# 4. Inputs

The engine consumes all EvidenceEvents associated with:

```text
student_id
course_id
objective_id
```

Each event already contains normalized information such as:

```text
evidence_strength

model_confidence

evidence_type

assistance_level

novelty

transfer_distance

created_at
```

The State Update Engine does NOT reinterpret the raw conversation.

That belongs to the Evidence Extraction / Evidence Scoring layer.

---

# 5. Evidence Eligibility

Not every EvidenceEvent should modify mastery.

V0 divides evidence into three groups.

---

## 5.1 Performance Evidence

These events MAY affect ObjectiveState.

```text
problem_attempt

self_explanation

definition_recall

transfer_attempt

retrieval_attempt

error_correction
```

---

## 5.2 Context Evidence

These events are stored but do NOT directly change mastery.

```text
student_question

student_self_report

teacher_observation
```

They may influence:

```text
teaching planning

diagnostic decisions

misconception detection

future assessment selection
```

but not ObjectiveState directly.

Example:

```text
Student:
"I understand eigenvectors."
```

This is useful context.

It is not performance evidence.

---

## 5.3 Model-Correction Evidence

```text
student_dispute
```

does not directly change mastery.

It may reduce confidence in:

```text
misconceptions

learning insights

URPP-generated interpretations
```

---

# 6. Effective Evidence

Each performance EvidenceEvent contains:

```text
evidence_strength ∈ [-1, 1]
```

where:

```text
-1 = strongest negative evidence
 0 = neutral
+1 = strongest positive evidence
```

The State Update Engine converts it into:

```text
effective_strength
```

using:

\[
e_i
=
s_i
\cdot
c_i
\cdot
r_i
\cdot
t_i
\]

where:

```text
s_i = evidence_strength

c_i = model confidence

r_i = recency weight

t_i = evidence-type weight
```

The value is clamped to:

```text
[-1, 1]
```

---

# 7. Evidence-Type Weights

V0 uses transparent heuristic weights.

These are engineering defaults, not scientific claims.

```text
problem_attempt      1.00

self_explanation     0.85

definition_recall    0.65

transfer_attempt     1.00

retrieval_attempt    1.00

error_correction     0.75
```

Why?

A successful definition recall is evidence of recall.

It is not equivalent to successful independent application.

A transfer attempt is high-value performance evidence.

---

# 8. Recency Weight

New evidence should describe the current state more strongly than
very old evidence.

However:

> Old evidence becoming old does not automatically mean the student
> became worse.

V0 uses recency weighting during aggregation:

```text
Age of evidence      Weight

0–7 days             1.00

8–21 days            0.90

22–42 days           0.75

43–84 days           0.60

85+ days              0.45
```

If all evidence becomes older together, the estimated score should
remain approximately stable.

Confidence may decrease because current evidence is limited.

---

# 9. Positive and Negative Evidence Mass

For all eligible events:

```text
positive_mass =
    Σ max(effective_strength, 0)

negative_mass =
    Σ max(-effective_strength, 0)
```

Then:

```text
total_mass =
    positive_mass + negative_mass
```

---

# 10. Internal State Score

If:

```text
total_mass == 0
```

then:

```text
state_score = None
```

Otherwise:

\[
state\_score
=
\frac{positive\_mass}
     {positive\_mass + negative\_mass}
\]

Therefore:

```text
0.0
≈ evidence strongly favors failure

0.5
≈ evidence is mixed

1.0
≈ evidence strongly favors success
```

Important:

A high numerical score with very little evidence does NOT imply a
high student-facing state.

Confidence and state gates must still be applied.

---

# 11. Why Score and Confidence Are Separate

Example A:

```text
1 independent correct answer
```

could produce:

```text
state_score ≈ 1.0
```

but:

```text
confidence = low
```

because there is too little evidence.

Example B:

```text
8 independent successes
across multiple sessions
including transfer
```

may also produce:

```text
state_score ≈ 1.0
```

but now:

```text
confidence = high
```

These are fundamentally different situations.

---

# 12. Confidence Model

V0 confidence has four components.

```text
Evidence Quantity

Session Diversity

Recency Coverage

Consistency
```

---

## 12.1 Quantity Score

```text
quantity_score =
    min(total_mass / 3.0, 1.0)
```

This means approximately three strong evidence units are enough to
saturate the quantity component.

---

## 12.2 Session Diversity Score

```text
session_diversity_score =
    min(unique_session_count / 3.0, 1.0)
```

Evidence from multiple sessions is more reliable than many observations
from one short interaction.

---

## 12.3 Recency Coverage

Define recent evidence as evidence from the last:

```text
21 days
```

Then:

```text
recent_mass =
    total absolute effective evidence
    from the last 21 days
```

and:

```text
recency_score =
    min(recent_mass / 1.5, 1.0)
```

---

## 12.4 Consistency

Let:

```text
P = positive_mass
N = negative_mass
```

If:

```text
P + N > 0
```

then:

\[
consistency
=
\frac{|P-N|}
     {P+N}
\]

Interpretation:

```text
1.0 = evidence strongly agrees

0.0 = positive and negative evidence are balanced
```

Contradictory evidence should lower confidence in a single simple
state estimate.

---

# 13. Confidence Formula

V0:

\[
confidence
=
0.40Q
+
0.25D
+
0.20R
+
0.15C
\]

where:

```text
Q = quantity score

D = session diversity

R = recency score

C = consistency
```

Clamp:

```text
confidence ∈ [0, 1]
```

This formula is deliberately transparent and versioned.

It is a V0 heuristic.

It is expected to change after evaluation.

---

# 14. Minimum Evidence Gate

URPP should remain conservative.

An ObjectiveState remains:

```text
UNKNOWN
```

unless BOTH conditions are satisfied:

```text
eligible evidence count >= 2
```

and:

```text
total_mass >= 0.75
```

This prevents one weak interaction from becoming a student label.

---

# 15. Base State Mapping

After the minimum evidence gate:

```text
state_score < 0.35

→ EMERGING
```

```text
0.35 <= state_score < 0.65

→ DEVELOPING
```

```text
0.65 <= state_score < 0.82

→ COMPETENT
```

```text
state_score >= 0.82

→ STRONG candidate
```

These thresholds are policy parameters.

They are not claims about universal learning science.

---

# 16. Competent Gate

A student cannot be labeled:

```text
COMPETENT
```

only because the aggregate score is high.

V0 additionally requires:

```text
confidence >= 0.55
```

and:

```text
independent_success_count >= 1
```

If the score suggests Competent but the gate is not satisfied:

```text
cap state at DEVELOPING
```

---

# 17. Strong Gate

A student cannot be labeled:

```text
STRONG
```

without evidence of persistence and independence.

V0 requires:

```text
state_score >= 0.82

confidence >= 0.75

independent_success_count >= 2

unique_session_count >= 2
```

and at least one:

```text
successful transfer attempt
```

OR:

```text
successful delayed retrieval attempt
```

If these gates are not satisfied:

```text
cap state at COMPETENT
```

This prevents:

```text
one easy correct answer
```

from producing:

```text
STRONG
```

---

# 18. Independent Success

An event counts as an independent success when:

```text
outcome == success
```

and:

```text
assistance_level == 0
```

and the evidence event is eligible performance evidence.

---

# 19. Transfer Success

A transfer success requires:

```text
evidence_type == transfer_attempt
```

and:

```text
outcome == success
```

and:

```text
assistance_level <= 1
```

Preferred high-quality transfer evidence:

```text
novelty == novel
```

---

# 20. Retrieval Success

A retrieval success requires:

```text
evidence_type == retrieval_attempt
```

and:

```text
outcome == success
```

and:

```text
assistance_level <= 1
```

Delayed retrieval evidence should be treated as particularly useful
evidence of persistence.

---

# 21. Conflicting Evidence

Conflicting evidence is expected.

Example:

```text
Session 1
independent success

Session 2
independent failure

Session 3
success with hints
```

URPP must not delete inconvenient evidence.

Instead:

```text
all valid evidence remains
```

and:

```text
confidence decreases
```

until additional evidence resolves the uncertainty.

---

# 22. Recent Evidence vs Historical Evidence

Recent evidence should have stronger influence over current state.

Historical evidence must remain available for:

```text
learning history

progress analysis

regression detection

evaluation
```

URPP does not overwrite history when state changes.

---

# 23. State Regression

A state may decline when newer performance evidence contradicts the
previous estimate.

Example:

```text
Previous:
STRONG

New:
two recent independent retrieval failures
```

Possible new estimate:

```text
COMPETENT
```

This is valid.

However:

```text
time passing alone
```

must not create regression.

---

# 24. Status Reason

Every ObjectiveState must include a concise machine-generated reason.

Example:

```text
Recent evidence includes two independent application successes
across two sessions and one successful transfer attempt.
```

or:

```text
Evidence is mixed and limited to one session; more independent
performance evidence is needed.
```

The status reason must be generated from structured state features.

It must not be free-form LLM speculation.

---

# 25. Misconception Engine Is Separate

ObjectiveState and misconception status are related but separate.

Example:

```text
ObjectiveState:
COMPETENT
```

may coexist with:

```text
Misconception:
ACTIVE
```

if the misconception is narrow and specific.

Do not collapse misconception state into mastery state.

---

# 26. Misconception Lifecycle

V0:

```text
SUSPECTED
    ↓
ACTIVE
    ↓
IMPROVING
    ↓
RESOLVED
```

If a resolved misconception appears again:

```text
RESOLVED
    ↓
RECURRING
```

---

# 27. Suspected Misconception

One plausible misconception observation may create:

```text
SUSPECTED
```

when:

```text
model_confidence >= 0.60
```

but one event is insufficient for:

```text
ACTIVE
```

---

# 28. Active Misconception

A misconception becomes:

```text
ACTIVE
```

when at least:

```text
2 supporting evidence events
```

exist and:

```text
support comes from
at least 2 distinct student responses
```

with combined interpretation confidence sufficient to justify the claim.

V0 candidate rule:

```text
sum(model_confidence) >= 1.20
```

---

# 29. Improving Misconception

An ACTIVE misconception may move to:

```text
IMPROVING
```

after:

```text
2 counter-evidence events
```

showing correct behavior related to the misconception.

At least one should be:

```text
independent
```

---

# 30. Resolved Misconception

A misconception may move to:

```text
RESOLVED
```

when:

```text
2 independent counter-evidence events
```

exist across:

```text
at least 2 sessions
```

and at least one is:

```text
transfer
```

or:

```text
delayed retrieval
```

with no newer supporting misconception evidence.

---

# 31. Recurring Misconception

If valid supporting evidence appears after RESOLVED:

```text
status = RECURRING
```

URPP should preserve the full historical lifecycle.

---

# 32. Student Dispute

If the student disputes a misconception or learning insight:

```text
student_dispute
```

must be stored.

The dispute:

```text
does not automatically erase prior evidence
```

but should:

```text
lower model confidence
```

and trigger:

```text
future diagnostic verification
```

when appropriate.

---

# 33. State Snapshot

Every state recomputation should eventually support an immutable snapshot:

```text
snapshot_id

student_id

objective_id

policy_version

state

state_score

confidence

supporting_evidence_ids

created_at
```

Example:

```text
Snapshot 17
    ↓
new learning session
    ↓
new evidence
    ↓
Snapshot 18
```

This allows:

```text
diff(snapshot_17, snapshot_18)
```

---

# 34. Policy Versioning

Every state calculation must include:

```text
policy_version
```

V0 begins with:

```text
state-policy-v0.1
```

If thresholds or formulas change:

```text
state-policy-v0.2
```

Old experiments must remain reproducible.

---

# 35. Idempotency

Running the State Update Engine twice on the same evidence set must
produce the same result.

```text
update(E)
=
update(E)
```

Duplicate processing must not create additional learning progress.

---

# 36. Failure Cases

The engine must safely handle:

## No evidence

```text
UNKNOWN
confidence = 0
```

## Only self-report

```text
UNKNOWN
```

## Only student questions

```text
UNKNOWN
```

## One correct answer

Usually:

```text
UNKNOWN
```

because evidence is insufficient.

## Many assisted successes

May become:

```text
DEVELOPING
```

but should not automatically become Strong.

## High score but no independent success

Maximum:

```text
DEVELOPING
```

until independent evidence exists.

## High score but no transfer / retrieval evidence

Maximum:

```text
COMPETENT
```

not Strong.

## Strong contradictory evidence

Reduce confidence.

Do not hide disagreement.

---

# 37. V0 Test Matrix

The implementation must include tests for at least:

### Test A — No Evidence

Expected:

```text
UNKNOWN
```

### Test B — Self Report Only

Expected:

```text
UNKNOWN
```

### Test C — One Independent Success

Expected:

```text
UNKNOWN
```

or low-confidence early state depending on final gate tuning.

### Test D — Repeated Assisted Success

Expected:

```text
DEVELOPING
```

not Strong.

### Test E — Multiple Independent Successes

Expected:

```text
COMPETENT
```

when confidence gate is satisfied.

### Test F — Independent Transfer Across Sessions

Expected:

```text
STRONG
```

when all Strong gates are satisfied.

### Test G — Conflicting Evidence

Expected:

```text
lower confidence
```

and no unsupported Strong state.

### Test H — Recent Regression

New independent failures should be able to move:

```text
STRONG
→
COMPETENT
```

### Test I — Duplicate Evidence

Duplicate evidence IDs must not change the state.

### Test J — Ordering

Evidence ordering must not change the state.

---

# 38. Separation of Responsibilities

The V0 learning pipeline should eventually be:

```text
Student Interaction
        ↓
Evidence Extractor
        ↓
Evidence Scorer
        ↓
EvidenceEvent
        ↓
State Update Engine
        ↓
ObjectiveState
```

This design intentionally separates:

```text
What happened?
```

from:

```text
How strong is the evidence?
```

from:

```text
What do all accumulated observations imply?
```

---

# 39. What Design 01B Does NOT Solve

This specification does not yet define:

```text
raw conversation → EvidenceEvent
```

That belongs to the Evidence Extraction design.

It also does not define:

```text
ObjectiveState → Teaching Action
```

That belongs to the Pedagogy Policy design.

Design 01B only owns:

```text
EvidenceEvent[]
      ↓
ObjectiveState
```

---

# 40. Implementation Target

After this design is approved, V0 implementation should create:

```text
backend/app/services/student_model/
    state_update.py

backend/app/services/student_model/
    policy.py
```

and tests:

```text
backend/tests/student_model/
    test_state_update.py
```

The first implementation must remain:

```text
deterministic

pure where possible

provider-independent

LLM-independent

fully unit-testable
```

---

# 41. V0 Architecture Result

With Design 01A + 01B:

```text
Learning Objective
        ↓
Student Interaction
        ↓
Evidence Event
        ↓
Evidence History
        ↓
State Update Engine
        ↓
Objective State
```

URPP now has the first formal definition of:

> What does it mean for URPP to believe that a student currently knows something?

That definition is based on evidence rather than chat memory or model intuition.

---

# 42. Next Design Step

After Design 01B is reviewed and frozen:

```text
Design 01C
Evidence Scoring and Extraction
```

will define:

```text
Student Response
      ↓
Structured Observation
      ↓
Evidence Strength
      ↓
EvidenceEvent
```

Then implementation of the Student State Engine can begin.

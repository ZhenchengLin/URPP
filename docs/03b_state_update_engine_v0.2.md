# URPP Design 01B — State Update Engine V0.2

Status: **Implementation Candidate**

Supersedes: `03_state_update_engine.md` V0.1

Policy ID: `state-policy-v0.2`

---

## 1. Purpose

The State Update Engine estimates the current observed performance
of one student on one Learning Objective.

It consumes validated performance evidence and produces a derived
ObjectiveState.

```text
EvidenceEvent[]
       ↓
Validate and Deduplicate
       ↓
Check Objective Alignment
       ↓
Control Correlated Evidence
       ↓
Calculate Diagnostic Weight
       ↓
Estimate Observed Performance
       ↓
Evaluate Evidence Sufficiency
       ↓
Apply State Gates
       ↓
ObjectiveState
```

The engine must be deterministic, reproducible, auditable,
and independent of the LLM provider.

---

## 2. Terminology

### Learning Objective

An observable capability the student is expected to demonstrate.

Example:

Determine whether a given vector is an eigenvector of a matrix.

### Performance Score

An assessment-specific measurement of the student's observed
performance.

```text
p_i ∈ [0, 1]
```

Examples:

```text
0.0 = incorrect
0.5 = partially correct
1.0 = correct
```

Partial credit must be determined by the assessment rubric.

### Diagnostic Weight

The amount of evidence this assessment contributes toward estimating
the student's current independent performance.

```text
w_i ∈ [0, 1]
```

Diagnostic weight is NOT the same as correctness.

### Performance Estimate

The weighted estimate derived from valid performance evidence.

It is not a scientifically calibrated mastery probability.

### Evidence Support

How much relevant, sufficiently independent evidence exists.

It is not a probability that the student knows the material.

### Performance Stability

Whether repeated assessments show a reasonably consistent pattern.

### Evidence Freshness

Whether the current estimate is supported by recent direct assessment.

Freshness is not itself evidence of success or failure.

---

## 3. Fundamental Invariants

1. Evidence history is the source of truth.
2. ObjectiveState is derived, not directly written by an LLM.
3. The same input, policy, and as_of timestamp produce the same output.
4. Evidence order must not change the result.
5. Duplicate evidence IDs must not increase evidence mass.
6. Conflicting records with the same ID must raise a validation error.
7. Evidence from other students or objectives must not be mixed.
8. Unknown is a valid result.
9. Unsupported claims about learning ability are prohibited.
10. Time passing alone must not change the performance estimate.
11. Corrections preserve an auditable evidence history.
12. Policy changes must be versioned.

---

## 4. Required Inputs

The estimator accepts:

```text
student_id

course_id

objective_id

evidence_events

policy_version

as_of
```

`as_of` is an explicit timezone-aware timestamp.

Do not read the current clock implicitly inside the pure estimator.

All eligible events must satisfy:

```text
event.student_id == student_id

event.course_id == course_id

event.objective_id == objective_id
```

Future-dated evidence relative to `as_of` must be rejected
or explicitly excluded according to a documented ingestion policy.

The estimator must not silently mix different students,
courses, or objectives.

---

## 5. Schema Changes Required Before Implementation

The existing EvidenceEvent schema is a V0.1 placeholder.

V0.2 needs additional assessment metadata:

```text
assessment_item_id

response_group_id

objective_alignment

assessment_validity

prior_solution_exposure

scoring_policy_version
```

### assessment_item_id

Identifies the assessment question or task.

### response_group_id

Groups correlated responses to the same task.

### objective_alignment

Records whether the task directly assesses the target
Learning Objective.

V0 may use:

```text
direct

indirect

not_aligned

unknown
```

Only directly aligned evidence contributes to the
objective's performance estimate.

### assessment_validity

Records whether the response can meaningfully be assessed.

Possible values:

```text
valid

invalid

uncertain
```

Only valid events enter the performance estimator.

### prior_solution_exposure

Indicates whether the student has already seen the solution
to the same or an equivalent task.

Independent performance cannot be established merely because
assistance_level == 0 after solution exposure.

### scoring_policy_version

Identifies the scoring rubric/policy that generated the
performance score and diagnostic weight inputs.

---

## 6. Evidence Eligibility

Only directly aligned, valid performance evidence can modify
the performance estimate.

Potential performance evidence types:

```text
problem_attempt

self_explanation

definition_recall

transfer_attempt

retrieval_attempt

error_correction
```

Evidence type alone does not establish objective alignment.

The following events are context by default:

```text
student_question

student_self_report

teacher_observation

student_dispute
```

They do not directly modify the performance estimate.

A teacher-confirmed assessment can contribute performance evidence
only through an explicitly recorded assessment event.

---

## 7. Correctness and Performance Score

V0.2 uses:

```text
p_i = correctness
```

where:

```text
0 <= correctness <= 1
```

Correctness must be evaluated against the specific
assessment rubric and target Learning Objective.

For a math application objective, repeating a definition is
not a substitute for solving an application problem.

Missing correctness cannot silently become zero.

If correctness is unavailable:

```text
the event does not enter performance aggregation
```

and URPP may request another diagnostic assessment.

---

## 8. Diagnostic Weight

For an eligible performance event:

```text
w_i =
    assistance_weight
    × novelty_weight
    × evidence_type_weight
    × interpretation_weight
```

The result is clamped to:

```text
[0, 1]
```

These weights are candidate V0 engineering heuristics.

They are not scientific measurements of student ability.

---

## 9. Assistance Weight

Candidate V0 values:

```text
Assistance Level    Weight

0                   1.00

1                   0.80

2                   0.60

3                   0.45

4                   0.30

5                   0.15

6                   0.00
```

Correctness after substantial assistance provides weaker
evidence about independent performance.

A full walkthrough is teaching context, not an
independent performance assessment.

Assistance affects diagnostic weight, not correctness.

Both successful and unsuccessful highly assisted attempts
should be interpreted cautiously.

---

## 10. Novelty Weight

Candidate V0 values:

```text
Novelty             Weight

novel               1.00

similar             0.75

repeated            0.35

unknown             0.50
```

Repeated exposure to the same answer must not generate
unlimited independent performance evidence.

Novelty describes the assessment task, not the student's
personal learning style.

---

## 11. Evidence-Type Weight

Candidate V0 values:

```text
problem_attempt     1.00

self_explanation    0.90

definition_recall   0.80

transfer_attempt    1.00

retrieval_attempt   1.00

error_correction    0.65
```

These values are applied only after direct objective alignment
has been established.

A definition-recall event cannot raise an unrelated
application objective merely because it is recorded.

---

## 12. Interpretation Weight

`model_confidence` describes confidence in the interpretation
of the observed response.

It is not the student's confidence or mastery.

For V0.2:

```text
model_confidence < 0.65

→ exclude from automatic performance aggregation
```

Otherwise:

```text
interpretation_weight = model_confidence
```

This threshold is a provisional policy parameter.

Low-confidence interpretations remain in evidence history
and may trigger additional assessment.

Do not multiply by model_confidence again if a future scoring
policy has already incorporated it into a stored weight.

---

## 13. Correlated Evidence Control

Multiple answers to the same problem are not automatically
multiple independent assessments.

V0.2 aggregation uses:

```text
student_id

objective_id

session_id

assessment_item_id
```

as the assessment grouping key.

For the same task within the same session:

```text
initial valid performance attempt
```

is the default event used for independent-performance aggregation.

Later guided corrections remain in history but do not
create additional independent-success counts for that task.

To establish a new independent performance observation,
URPP should use a different assessment item.

An event without a trustworthy assessment_item_id cannot
satisfy the distinct-item requirements for Competent or Strong.

---

## 14. Same-Session Evidence Cap

V0.2 limits excessive evidence accumulation from one session.

Candidate policy:

```text
max_effective_mass_per_session = 1.5
```

If the sum of eligible diagnostic weights for a session
exceeds the cap, scale those weights proportionally.

The scaling must be deterministic and independent of event order.

This prevents a large number of nearly equivalent interactions
from overwhelming evidence across multiple sessions.

The cap is provisional and must be evaluated.

---

## 15. Performance Estimate

For valid, deduplicated, aligned performance events:

\[
\hat{p}
=
\frac{\sum_i w_i p_i}
     {\sum_i w_i}
\]

where:

```text
p_i = performance score

w_i = final diagnostic weight
```

If:

```text
Σ w_i == 0
```

then:

```text
performance_estimate = None

state = UNKNOWN
```

A performance estimate of 1.0 does not automatically
produce Competent or Strong.

All state gates must be evaluated separately.

---

## 16. Evidence Support

V0.2 measures evidence support using:

```text
effective_evidence_mass

distinct_assessment_items

distinct_sessions

independent_success_count

interpretation_quality
```

The initial implementation may calculate:

```text
quantity_support =
    min(effective_evidence_mass / 3.0, 1.0)
```

and:

```text
item_diversity_support =
    min(distinct_assessment_items / 3.0, 1.0)
```

Candidate internal support score:

```text
evidence_support_score =
    quantity_support × item_diversity_support
```

This is an engineering sufficiency indicator.

It must NOT be presented to the student as a calibrated
probability of mastery.

The public interface should prefer:

```text
insufficient

limited

moderate

substantial
```

until empirical calibration exists.

---

## 17. Performance Stability

Performance stability is stored separately from
evidence sufficiency.

Candidate V0 labels:

```text
insufficient_data

consistent

mixed
```

Mixed evidence should not be hidden or deleted.

A student may have substantial evidence and still
show mixed performance.

The exact stability classification threshold must be
finalized in the implementation policy and evaluated.

---

## 18. Evidence Freshness

Recency does not change the performance estimate in V0.2.

Instead, the engine computes:

```text
last_direct_assessment_at

last_independent_assessment_at

evidence_freshness
```

Candidate labels:

```text
recent

stale

unknown
```

Initial review trigger:

```text
last independent aligned assessment > 21 days ago
```

This is a provisional scheduling heuristic.

It does not imply that the student has forgotten the material.

The Teaching Policy may select:

```text
RETRIEVAL_CHECK
```

when evidence is stale.

---

## 19. Minimum Evidence Gate

The student-facing state remains:

```text
UNKNOWN
```

unless there are:

```text
at least 2 distinct valid assessment items
```

and:

```text
effective_evidence_mass >= 0.75
```

The assessment items must directly target the objective.

One correct response cannot establish competence.

One incorrect response cannot establish persistent weakness.

---

## 20. Candidate State Mapping

After the minimum evidence gate:

```text
performance_estimate < 0.40

→ EMERGING
```

```text
0.40 <= performance_estimate < 0.75

→ DEVELOPING
```

```text
0.75 <= performance_estimate < 0.90

→ COMPETENT candidate
```

```text
performance_estimate >= 0.90

→ STRONG candidate
```

These are initial heuristic thresholds.

The final state is determined only after all gates.

---

## 21. Competent Gate

COMPETENT requires:

```text
performance_estimate >= 0.75
```

and:

```text
at least 2 independent successful assessments
```

on:

```text
at least 2 distinct assessment items
```

At least one successful assessment must be:

```text
similar or novel
```

rather than a direct repetition of a previously
revealed solution.

If a candidate fails this gate:

```text
final state <= DEVELOPING
```

---

## 22. Strong Gate

STRONG requires:

```text
performance_estimate >= 0.90
```

and:

```text
at least 3 independent successful assessments
```

on:

```text
at least 3 distinct assessment items
```

across:

```text
at least 2 sessions
```

Additionally, there must be an objective-aligned:

```text
successful transfer assessment
```

or:

```text
successful delayed retrieval assessment
```

The assessment must meaningfully test the target objective.

A recall question cannot establish Strong performance
for an application objective.

If the Strong gate fails but the Competent gate passes:

```text
final state = COMPETENT
```

---

## 23. Independent Success Definition

An independent success requires:

```text
outcome == success

assistance_level == 0

prior_solution_exposure == false

assessment_validity == valid

objective_alignment == direct
```

The event must also have a trustworthy assessment_item_id.

An answer copied after a walkthrough is not independent
merely because the current message contains no new hint.

---

## 24. State Regression

State regression requires new valid performance evidence.

Example:

```text
Previous:
STRONG

New:
Multiple independent application failures
```

Possible result:

```text
COMPETENT
```

or:

```text
DEVELOPING
```

depending on the full evidence set and state gates.

Time passing alone does not cause state regression.

Evidence history must never be overwritten to force
a preferred state transition.

---

## 25. Misconceptions Are a Separate Model

Misconception status must not be derived directly
from the aggregate performance estimate.

A misconception requires a specific, observable
incorrect reasoning pattern.

For V0, retain the lifecycle:

```text
SUSPECTED
    ↓
ACTIVE
    ↓
IMPROVING
    ↓
RESOLVED
```

and:

```text
RESOLVED
    ↓
RECURRING
```

Detailed activation and resolution rules belong
to a separate Misconception Engine specification.

Do not implement misconception transitions inside
the performance aggregation function.

---

## 26. Existing Schema Migration

The current ObjectiveState schema contains:

```text
state_score

confidence
```

V0.2 proposes that the implementation expose:

```text
performance_estimate

evidence_support_score

performance_stability

evidence_freshness

effective_evidence_mass

distinct_assessment_count
```

The existing numeric confidence field must not
silently change meaning.

Use an explicit schema migration and versioned
state snapshots when the implementation begins.

The existing signed evidence_strength field is
not used as the performance-estimate numerator
under this revised policy.

Its future meaning or removal must be resolved
in Design 01C before production implementation.

---

## 27. Reproducibility

Every derived state must identify:

```text
student_id

course_id

objective_id

policy_version

scoring_policy_version

as_of

included_evidence_ids

excluded_evidence_ids

exclusion_reasons
```

Deterministic processing must produce the same output
for the same validated inputs.

Correction of a historical observation must preserve
a revision trail rather than silently rewriting history.

---

## 28. Required Tests

Before the estimator is considered ready:

```text
T01: No evidence → UNKNOWN

T02: Self-report only → UNKNOWN

T03: One independent success → UNKNOWN

T04: Two independent successes on distinct items
     → COMPETENT when all gates pass

T05: Assisted successes alone → not COMPETENT

T06: Three independent successes with appropriate
     transfer/retrieval across two sessions
     → STRONG when all gates pass

T07: Duplicate evidence IDs do not increase mastery

T08: Conflicting duplicate IDs raise an error

T09: Evidence order does not affect the result

T10: Irrelevant objective evidence is excluded

T11: Repeated attempts on one assessment item
     do not create multiple independent successes

T12: Time passing without new evidence does not
     change performance_estimate

T13: Stale evidence triggers a freshness signal

T14: New valid failures can lower the state

T15: Low-confidence interpretations do not
     silently update the Student Model

T16: Previously exposed solutions do not
     count as independent successes

T17: Two assessments in one session do not
     automatically satisfy the Strong session gate

T18: Score 1.0 with insufficient evidence
     does not produce Strong
```

---

## 29. Implementation Boundary

Design 01B owns:

```text
Validated EvidenceEvent[]
          ↓
State Update Engine
          ↓
ObjectiveState
```

Design 01C owns:

```text
Student Response
          ↓
Evidence Extraction
          ↓
Assessment Rubric
          ↓
Evidence Scoring
          ↓
EvidenceEvent
```

Pedagogy Policy owns:

```text
ObjectiveState
+
Course State
+
Student Request
          ↓
Next Teaching Action
```

Do not merge all three responsibilities into one LLM prompt.

---

## 30. Next Engineering Step

Before implementing state_update.py:

1. Update EvidenceEvent and ObjectiveState schemas.
2. Define the policy configuration object.
3. Add assessment identity and validity fields.
4. Define the exact event-grouping rule.
5. Define pure aggregation and state-gating functions.
6. Build synthetic test fixtures.
7. Validate the estimator against the required tests.

V0.2 is a design candidate, not a scientifically validated
student-ability model.

Its parameters must remain transparent and replaceable.

# URPP — Personalized Pedagogical Decision Policy

Status: Implementation 13B-1, student-request contract only.

## Mission

URPP aims to provide each student with a personal AI teaching team
that adapts to their learning goals, demonstrated knowledge, and
explicit requests.

A student's learning request must not be interpreted as proof of mastery.

## Current implementation baseline

The existing DecisionEngineV01, RuleBasedControllerV01, and
PedagogicalPolicyV01 remain unchanged.

Implementation 13B-1 introduces:

- StudentLearningRequestKindV01
- StudentLearningRequestV01
- PersonalizedDecisionContextV01

The personalized context uses composition rather than inheriting
DecisionContextV01, preventing the old decision interface from silently
accepting and ignoring a student request.

This stage does not yet alter the selected teaching action.

## Research foundations

Black and Wiliam (2009), Developing the Theory of Formative Assessment.
DOI: 10.1007/s11092-008-9068-5

Relevant principle: learning evidence can inform subsequent teaching.

Kalyuga et al. (2003), The Expertise Reversal Effect.
DOI: 10.1207/S15326985EP3801_4

Relevant principle: the usefulness of instructional guidance depends
on the learner's existing knowledge.

Koedinger and Aleven (2007), Exploring the Assistance Dilemma
in Experiments with Cognitive Tutors.
DOI: 10.1007/s10648-007-9049-0

Relevant question: when should a tutoring system provide assistance,
and when should it allow the learner to attempt a problem independently?

These papers do not establish URPP-specific decision thresholds,
the optimal ordering of teaching actions, or the effectiveness
of this particular personalized decision algorithm.

## Future decision design

Implementation 13B-2 will determine how explicit student requests
interact with authoritative Student State and teaching-action policy.

The design must distinguish:

1. The student's preferred learning activity.
2. The evidence required for a mastery claim.
3. Whether an action is permitted by the current policy.
4. Why a particular permitted action was selected.

Do not silently replace a student's requested activity with another
action merely because that action appears first in an allowed-action tuple.

If a request cannot be fulfilled, the future decision result should
make that limitation explicit rather than claiming it was satisfied.

## Explicitly out of scope for 13B-1

- Changes to DecisionEngineV01 or its fallback
- Changes to Numeric Session or Assignment persistence
- Free-text request interpretation by an LLM
- Authentication or authorization of student requests
- Changes to Objective State or Evidence
- Empirical validation of a personalized teaching strategy

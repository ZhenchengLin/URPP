# URPP — Personalized Teaching Action Selection V0.1

Status: Implementation 13B-2.

## Purpose

Allow an explicit, structured student learning request to influence
the next selected teaching action without changing the authoritative
Student State or the existing Decision Engine V0.1 baseline.

## Existing baseline

DecisionEngineV01 and PedagogicalPolicyV01 remain unchanged.

With no student request, PersonalizedDecisionEngineV01 delegates
selection to the existing RuleBasedControllerV01 baseline.

## Explicit student request

The request-to-action mapping uses existing TeachingActionV01 values.

A student may request an existing supported teaching activity,
including an explanation when their State is STRONG.

For explicit requests, the corresponding action is included in the
personalized decision's allowed-action set when necessary.

This expansion applies to the baseline state-dependent teaching-action
list only. It does not change evidence validity, scoring, mastery,
assessment alignment, Session registration, or database constraints.

No unsupported TeachingAction is introduced.

## Selection provenance

PersonalizedDecisionResultV01 records:

- the underlying DecisionResultV01;
- whether selection used the baseline or an explicit request;
- whether the requested action was selected;
- whether the baseline allowed-action set required expansion;
- a brief, inspectable selection reason.

A selected action is not the same as an executed action.

## Research interpretation

Supporting student agency is a product and pedagogical design goal.
The exact request-to-action mapping implemented here is an URPP
engineering hypothesis, not a teaching strategy proven optimal by
existing education research.

Student State remains an evidence-derived estimate.

A student's request to attempt advanced work does not itself
establish mastery or successful transfer.

## Limitations

This stage is pure decision selection.

It does not connect the personalized result to the existing
TeachingTurnOrchestratorV01 or Recoverable Session.

It does not authenticate the student, interpret free-text requests,
guarantee Agent execution, or persist decision explanations.

Request validity remains subject to StudentLearningRequestV01 and
PersonalizedDecisionContextV01 validation.

The current selection policy does not yet model recent hints,
task-specific difficulty, available Assessment Items, or conflicts
between multiple simultaneous student requests.

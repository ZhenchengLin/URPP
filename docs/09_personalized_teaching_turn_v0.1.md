# URPP — Personalized Teaching Turn V0.1

Status: Implementation 13C-1.

## Purpose

Connect the structured student request and personalized
teaching decision to one internal Teaching Agent call.

The student's explicit request and authoritative Student
State remain separate inputs.

## Architecture

Student Request + Objective State
→ Personalized Decision Context
→ Personalized Decision Engine
→ Policy-checked Teaching Action
→ Professor or Assessment Agent
→ Teaching Content

## Compatibility boundary

The existing DecisionEngineV01 and
TeachingTurnOrchestratorV01 remain unchanged.

The new orchestrator must not call the legacy orchestrator
after making a personalized decision, because that would
trigger a second decision that ignores the student request.

The new PersonalizedTeachingAgentPortV01 receives both:

- PersonalizedDecisionContextV01, including the request;
- PersonalizedDecisionResultV01, including the selected
  action and its decision provenance.

This is a distinct Agent port. Existing legacy Agent
adapters are not automatically compatible with it.

Routing reuses the existing Assessment/Professor action
groupings.

## Student State and evidence boundary

Student requests do not change Objective State.

Generated teaching content is not assessment evidence.

Requesting independent or transfer practice does not
constitute successful independent work or transfer.

The orchestrator checks for accidental in-place changes
to the supplied Objective State before and after the Agent
call. This is an engineering check, not an authorization
or sandbox security boundary.

## Explicit limitations

This implementation is a single-turn coordinator.

Tests use recording Agent doubles, not real LLM Agents.

It does not authenticate a student, interpret free-text
requests, issue a persisted Numeric Assignment, submit an
Attempt, update Evidence, or resume a persisted Session.

A transfer-assessment request selects the corresponding
action but does not establish whether a suitable aligned
assessment item exists. That must be checked by the later
assessment-delivery integration.

The personalized V0.1 policy can expand the legacy
state-dependent action list for explicit requests.
This must not be treated as permission to bypass
assessment validity, session registration, authorization,
or database integrity requirements.

## Next integration

A later stage must connect the personalized teaching turn
to the existing Recoverable Numeric Session through an
explicit interface and verify the complete persisted
assignment and answer-submission workflow.

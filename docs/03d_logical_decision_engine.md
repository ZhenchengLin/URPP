# Design 01D — Logical Decision Engine

Status: V0.1 engineering prototype.

## Purpose

Select the next teaching action from an authoritative
Student State without allowing a Decision Model to
change learning evidence or mastery estimates.

## Architecture

Student State
→ Decision Context
→ Pedagogical Policy
→ Allowed Teaching Actions
→ Logical Decision Controller
→ Final Policy Check
→ Teaching Action

## Core contracts

`DecisionContextV01` contains a Student State snapshot.

`TeachingActionV01` defines supported action names.

`DecisionProposalV01` represents a controller proposal.

`DecisionResultV01` contains the final selected action,
allowed-action set, controller version, and fallback status.

## Controller design

`RuleBasedControllerV01` is the initial deterministic baseline.

A future NanoJev adapter can implement the same controller
interface and receive the same decision context and action set.

A Decision Model cannot add actions to the allowed set.

An invalid proposal or timeout activates the deterministic fallback.

## Current limitations

The policy is a development baseline, not a validated teaching strategy.

No NanoJev model has been integrated or trained for URPP.

No Professor Agent, Assessment Agent, or session orchestrator
is connected to this Decision Engine yet.

Before sending context to an external model, minimize or remove
student identifiers and unnecessary learning-history details.

The current Decision Engine does not authenticate callers,
execute teaching actions, or modify Student State.

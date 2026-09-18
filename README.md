# URPP — Personal Professor

URPP is a persistent AI Personal Professor for university STEM students.

It follows an evolving university course, maintains an evidence-based
model of the student, and uses explicit pedagogical policy to decide
what to teach next and how to teach it.

## North Star

> Given the course requirement and current student evidence,
> what is the next best teaching action?

## V0 Scope

URPP V0 focuses on:

- one student
- one active university STEM course
- course materials arriving over time
- explicit learning objectives
- evidence-based student modeling
- adaptive teaching
- formative assessment
- persistent student state
- controlled evaluation

## Core Loop

```text
Course Material
      ↓
Course Model
      ↓
Learning Objectives
      ↓
Required Student State
      │
Current Student State
      ↑
Evidence History
      │
      └──────────────┐
                     ↓
                Learning Gap
                     ↓
             Pedagogical Policy
                     ↓
              Teaching Action
                     ↓
                  Student
                     ↓
          Formative Assessment
                     ↓
              Evidence Event
                     ↓
          Student State Update
                     ↓
          Next Teaching Action
```

## Current Development Status

Completed design direction:

```text
Learning Objective
        ↓
Evidence Event
        ↓
Objective State
```

Next:

```text
Design 01B
State Update Engine
```

## Core Principle

Evidence history is the source of truth.

Student state is a derived estimate.

LLMs may propose structured observations, but LLMs do not directly
modify student state.

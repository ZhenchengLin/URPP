# URPP: research brief

**Zhencheng Lin** · M.S. Electrical and Computer Engineering, UC Santa Cruz · [github.com/ZhenchengLin/URPP](https://github.com/ZhenchengLin/URPP)

## The problem

Course chatbots answer questions well, but they cannot say what a student has learned. They treat "correct after a hint" the same as mastery, and the same model that writes an explanation also decides what the student does next. A student using one gets answers, not a teacher who tracks their progress through a course.

## Research question

> **Can an AI tutor that adapts to a student's *demonstrated* understanding help them learn more effectively and study more independently than a standard course chatbot?**

## Approach

URPP separates three jobs that a chatbot mixes together:

| Role | Responsibility | Decided by |
|---|---|---|
| Learning analyst | Turn answers into evidence; track what the student has shown, per topic | Deterministic rules over an append-only record |
| Teaching policy | Choose the next step (study, practice, hint, review, move on) with a stated reason | Explicit, versioned rules |
| Professor | Explain, using only the student's course materials | A local language model, which cannot change the student's record |

Two rules run through the design:
- **"Unknown" is a valid answer.** A correct answer after a hint is recorded as assisted, and leads to an unassisted follow-up rather than "mastered".
- **Generated content is labelled.** Model-written course paths, lessons, and answer keys are checked for consistency, and marked as not human-verified.

## What exists today (open source, runs locally)

- **Course workspace.** Upload course notes. The system builds a course path with prerequisites, and writes a lesson and worked example per topic from its own sources.
- **Adaptive next step.** Check questions keep only answer keys that survive an independent re-solve. The next step and its reason follow from observed practice.
- **Course-grounded Professor chat.** Answers cite the material or decline. Equations are shown from human-verified records instead of being re-typed by the model.
- **Engineering.** About 1,400 automated tests, a design record for each stage, and a local model chosen by the computer's memory (2B to 27B).

## Preliminary results (small, developer-run; no learners yet)

| Measure | Result |
|---|---|
| Equation fidelity, 8 frozen questions on a CT-reconstruction paper | Plain model re-typing equations: 4 structural failures. URPP's verified-equation route: 0 |
| Critical math errors in model explanations (same 8 questions) | 4B: 3 (e.g. a factor placed in the numerator, a method misnamed, min/max reversed). 9B: 0. Checked against the source with an AI assistant; a human expert review is pending |
| Wrong answer keys in generated check questions (6 topics, every kept key checked against a worked solution) | 4B: 1 of 11. 9B: 0 of 12 (one 9B item had two correct choices). The 4B error passed the self-consistency check, which shows that check's limit |
| Running on a laptop | Model chosen by memory (4B on 8 GB, 9B on 16 GB). On a busy 16 GB machine, 9B can slow down enough to time out |

## Proposed study

A small within-course comparison of three conditions on the same materials:
1. A standard course chatbot.
2. A single tutor with a student model.
3. URPP's separated roles.

**Measures:** post-test, delayed retention, transfer to new problems, and how often students solve problems without help.

**Start small:** a pilot with a few volunteer students on one topic sequence, with outcome measures and analysis planned before any data is collected.

## What I'm looking for

Guidance on study design, and the chance to contribute to related research, through prototype development, evaluation, or joining an existing project.

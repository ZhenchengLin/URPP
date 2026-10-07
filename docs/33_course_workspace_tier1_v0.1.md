# URPP 33 — Course Workspace (Tier 1) v0.1

**Status:** implemented and verified on the local website 2026-10-06.
**User stories:** #1 course from my materials, #3 course path, #7 lessons and practice, #11 adapts to my performance (also #9 decision reasons, #17 one website).

## 1. Goal

On the local website, a student can:

1. create a course;
2. add several documents to it;
3. see a course path of topics with prerequisites and sources;
4. open a topic and study a grounded lesson;
5. answer check questions, optionally after asking for a hint;
6. see URPP's next step for them and why.

## 2. Scope and boundaries

- **New package `app/services/course_workspace/`, new page `/course`.** The existing chat page, Course Packs, and evidence/mastery engine are unchanged.
- **Documents reuse the existing importers** (`build_local_material_pack_v01`, `build_local_pdf_pack_v01`). Each document keeps its own digest-pinned Course Pack.
- **Two evidence paths, following `docs/27` decision 1.** Practice attempts are *observations made by URPP*: correctness plus whether URPP showed a hint or solution first. They drive the next teaching step. They are **not** mastery evidence, and the strict mastery path (`state_v02`) is not changed. The UI labels progress as "practice observed in URPP — not verified mastery".
- **Model output is labelled.**
  - Topics: `model_proposed`, or `heading_derived` for the fallback.
  - Lessons: `generated_unverified`.
  - Answer keys: `dual_solve_agreed`, meaning the model generated the question and key, then solved the question again without seeing the key. Only items where the two agree are kept. This is a consistency check, not human verification.

## 3. Components

| Component | Responsibility |
|---|---|
| `store_v01` | SQLite (`course-workspace.sqlite3` in the data root): courses, documents, outline revisions, lessons, items, hint/solution events, append-only attempts |
| `llm_json_v01` | Schema-constrained JSON calls to local Ollama (fixed 127.0.0.1 endpoint, no proxies), with repair of invalid backslash escapes and LaTeX control-character damage |
| `outline_v01` | Proposes 2–12 ordered topics with summary, key concepts, source references, and earlier-topic prerequisites. Validated deterministically; falls back to one topic per source excerpt |
| `lesson_v01` | Explanation plus worked example grounded in the topic's own sources; cited sources must belong to the topic |
| `practice_v01` | Numeric and multiple-choice check questions, filtered by dual-solve agreement, scored deterministically |
| `progress_policy_v01` | Deterministic next step per topic with a reason code (table below) |
| `service_v01` | Orchestration and persistence; the only entry point for the API |

## 4. Next-step policy (v0.1)

| Situation | Next step | Reason code |
|---|---|---|
| A prerequisite topic is not yet practiced | Go to that topic | `prerequisite_not_practiced` |
| Lesson not opened yet | Study the lesson | `topic_not_started` |
| No attempts | Answer a check question | `no_practice_evidence` |
| Two consecutive incorrect attempts, lesson not reopened since | Re-study the lesson | `repeated_errors` |
| Latest attempt incorrect | Try another question; a hint is available | `recent_error` |
| Latest correct attempt came after a hint/solution | Try a new question without help | `assisted_success_needs_unassisted_check` |
| One unassisted correct answer | One more new question | `single_success_needs_confirmation` |
| ≥2 unassisted correct answers on distinct items | Topic practiced; move to next topic | `ready_for_next_topic` |

These thresholds are engineering defaults, not validated learning science.

## 5. Acceptance checks

1. **Course from several documents.** On `/course`, create a course and add two documents; both are listed with their excerpt counts.
2. **Course path.** "Build course path" shows ordered topics. Each topic shows its prerequisites and source excerpts, plus a label saying how it was produced.
3. **Lesson.** Opening a topic shows an explanation and a worked example with cited sources and a "generated, not verified" label.
4. **Check questions.** Only dual-solve-agreed items are shown. Hint and solution requests are recorded before scoring.
5. **Adaptive next step.**
   - A correct answer after a hint leads to `assisted_success_needs_unassisted_check`.
   - Two unassisted correct answers lead to `ready_for_next_topic`.
   - The reason is shown in the UI.
6. **Persistence.** After a server restart, the course, path, lessons, items, attempts, and next step are restored.
7. **Real run.** All of the above are demonstrated on the real website with the local model, not only in tests.

## 6. Known limits

- Rebuilding the course path creates new topic IDs; practice history stays attached to the earlier revision.
- Single user, local only, no authentication.
- Dual-solve agreement can still accept an item where the model is consistently wrong.
- The strict mastery state is still `UNKNOWN` for all web practice, by design.

## 7. Verification (2026-10-06)

**Automated:** 24 new tests (JSON repair, outline validation and fallback, dual-solve filter, scoring, the full policy table, end-to-end service with restart, HTTP layer). Full backend suite passes.

**Real run** on the local website with `qwen3.5:4b`, a course of two synthetic linear-algebra notes:

| Check | Result |
|---|---|
| 1. Course from two documents | ✅ both listed with excerpt counts |
| 2. Course path | ✅ 6 model-proposed topics, each with prerequisites, key concepts, and sources |
| 3. Lesson | ✅ explanation plus worked example; worked example correct (m = 3, U = [[2,1],[0,5]], L = [[1,0],[3,1]]); labelled not verified. It does overclaim that *any* square matrix has an LU factorization |
| 4. Check questions | ✅ 3 of 3 kept for topic 1; all keys checked by hand and correct |
| 5. Adaptive next step | ✅ correct after hint → `assisted_success_needs_unassisted_check`; one unassisted → `single_success_needs_confirmation`; two unassisted → topic practiced, `ready_for_next_topic` → topic 2; opening topic 4 → `prerequisite_not_practiced` → topic 3 |
| 6. Persistence | ✅ after a server restart, documents, path, lesson, questions, progress, and next step were restored |
| 7. On the real website | ✅ all of the above through `/course` |

## 8. What the real run taught us (fixed before release)

1. **Schema drift.** The model returned correct topics under its own key names (`source_excerpts`, `earlier_topics`), even though Ollama was given a JSON schema. Prompts now spell out the exact JSON form, and parsing accepts common variants.
2. **Code fences.** The model wrapped JSON in ```` ```json ```` fences. The decoder strips fences and surrounding text.
3. **The re-solve check was unfair.** Without the course excerpts and with no room to reason, the checker rejected three questions whose keys were in fact correct. The checker now sees the same excerpts (never the key) and writes brief working first. Measured keep rates across three topics: 3/3, 1/3, 1/3.
4. **Fallback granularity.** One topic per excerpt was too coarse for short notes. The fallback now splits on `##` sections and keeps titles unique.
5. **Inline math artifact.** Inline formulas showed a scrollbar track; fixed in CSS (affects the chat page too).

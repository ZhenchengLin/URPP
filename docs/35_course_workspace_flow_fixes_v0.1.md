# URPP 35 — Course Workspace: Study/Practice Modes, Visible Waits, Content Prepared Ahead v0.1

**Status:** implemented and checked by the developer, 2026-10-08.
**Origin:** problems found while using the course workspace from docs/33 with the 9B model.

## 1. Problems reported

1. Markdown and math broke at the end of the notes, and in questions and answers.
2. The notes stayed on screen next to the check questions, so a student could read the answer off the lesson.
3. Building the path or writing a lesson took minutes with no sign of progress. The page looked frozen.
4. After the path was built, the lesson and the first questions were only written when the student asked for them, so every step meant another wait.

## 2. Causes and changes

| # | Cause | Change |
|---|---|---|
| 1a | The inline-math pattern did not allow a newline inside `$…$`, so a matrix written across lines showed as raw TeX. | `markdown_v01.js`: inline math may span lines. |
| 1b | `math_v01.js` typeset at most 160 formulas **per page, for the whole visit**. The workspace re-renders often, so after a few clicks every new formula stayed raw TeX, usually at the end of a lesson. | The page-wide counter is gone. The limit is now 160 formulas per rendered message, reset on each render. |
| 1c | Heading-derived path summaries dropped `$$` and kept the TeX inside, which showed as `\frac{c}{a}`. | `outline_v01._plain` keeps formulas as inline math and never cuts one in half. The page renders summaries with the Markdown renderer. |
| 2 | One screen showed the lesson and all questions together. | **Study** and **Practice** tabs. Practice shows one question at a time and hides the notes. |
| 3 | Status was one line of text. | Every action runs with a spinner bar that shows the step, the elapsed seconds and the expected wait. Background work shows a "Preparing…" box that updates itself. |
| 4 | Lessons and questions were generated on request. | `PreparationWorkerV01` writes the lesson and first questions for the recommended topic and the topic after it, as soon as the path exists. |

## 3. Notes during practice count as help

Practice observations already separate correct-with-help from correct-without-help (docs/33). Opening the notes during a question is now help too, recorded like a hint:

- **"Peek at the notes"** on a question records a `lesson_opened` event with that question's ID. The attempt then stores `notes_shown = 1`.
- **Switching to Study while a question is open** first asks: "This question is still open. Opening the notes now counts as help for it." The student can open the notes (recorded as help) or keep practicing.
- Studying **before** a question (an event with no question ID) is not help for that question.
- The next-step policy treats `notes_shown` like `hint_shown`. A correct answer after peeking leads to `assisted_success_needs_unassisted_check`, not to "practiced".
- Feedback names the help used: "Correct, with help (notes)."

Existing databases gain the `notes_shown` column on start (`ALTER TABLE … DEFAULT 0`). Old attempts read as "no notes".

## 4. Preparing ahead

- **When:** after the path is built, after the student opens a lesson, and after every answer. Each time, the worker queues what is missing for the recommended topic and the next unpracticed topic.
- **One model call at a time:** the worker shares the service's generation lock. If the student asks for something while a job is running, their request starts when the current step finishes, and the page says so.
- **No duplicates:** the first-set job only writes questions if the topic has none. The check happens inside the lock. "Write check questions now" sends `more: false` with the same rule; "Write more questions" sends `more: true`.
- **Rebuilt path:** a job for an older path revision does nothing.
- **Status:** each topic reports `lesson` and `questions` states:
  - `ready`, `queued`, `working` (with seconds), `failed` (with the exception type), `empty` (the job ran but no question passed the re-solve check), or `not_started`.
  - The path shows "Preparing…", "Queued" or "Ready" chips.
  - The page polls every 3 s while anything is preparing. It refreshes only the parts that were waiting, so a half-typed answer is never cleared.
- **Measured waits:** the worker records how long the last lesson and question job took. The page shows "Last time on this computer: about N min" instead of a fixed guess.
- **Status is in memory.** After a restart, generated content is still in the database, and anything missing is queued again on the next trigger.

## 5. Live check (9B, 16 GB MacBook, 2026-10-08)

Demo materials: `demo_materials/lu_decomposition_notes.md` and `solving_systems_with_lu.md`, on a test server with a temporary data folder.

| Step | Result |
|---|---|
| Build path | 41 s. The path appeared with "Preparing…" on topic 1 and "Queued" on topic 2. |
| Topic 1 lesson (background) | Ready about 60 s after the path. Opening the topic showed it at once in Study. All formulas rendered, including the closing verification matrices. |
| Topic 1 questions (background) | About 18 min, because the computer was out of memory: swap 6.6 of 7 GB used. 2 questions passed the re-solve check. |
| Practice | One question; notes hidden; Peek opened the notes inside the question. The answer was recorded as "Correct, with help (notes)". The next step became `assisted_success_needs_unassisted_check`. "Next question" moved to question 2. Clicking Study mid-question asked first. |

**Findings outside this change:**

- With two short documents, the 9B path proposal failed validation ("No proposed topic survived validation"), so the path fell back to 8 heading-derived topics. This needs its own investigation.
- On a 16 GB laptop with other apps open, the 9B model is slow enough that preparing ahead is necessary rather than just nice to have. Closing other apps, or using `--model qwen3.5:4b`, shortens the waits.

## 6. Follow-up: repeated questions (found in use, 2026-10-08)

The Practice tab said "6 questions" for a topic that had only 2 different ones, each saved three times.

- **Cause:** the model runs at temperature 0 and was never told which questions already existed, so "Write more questions" produced the same set again.
- **Worse effect:** answering a copy counted as a new question answered without help, even though the student had already seen the original's solution. That inflated "correct without help" and could mark a topic practiced.
- **Fix:**
  - New sets are written with the list of questions the student has seen (latest 12) and an instruction not to repeat or reword them.
  - Any question whose text matches one already saved in the topic (ignoring case, spacing and punctuation) is dropped and counted as `duplicate`.
- **Existing data:** copies saved earlier are merged into the first question with the same text:
  - Copies are hidden from Practice.
  - Their attempts count as repeat attempts on the original, which are assisted because the solution is shown after every answer.
  - On the developer's own course, topic 1 went from 6 questions and "practiced" to 2 questions and "learning". Its next step is now a new question without help.
- **Limit:** reworded near-copies with different text are not detected. The prompt asks the model to avoid them.

## 7. Acceptance checks (automated)

`tests/test_course_workspace_v01.py`, `tests/test_local_learning_web_v01.py`:

- Inline math across lines renders. The formula budget is per message: 3 renders × 100 formulas → 300 typeset; 1 render × 200 → 160.
- After the path is built, both topics' lessons and questions are `ready`. Opening the lesson makes no further model calls (inline mode).
- `more: false` on a prepared topic returns `skipped: already_prepared`.
- Background mode fills everything once, not twice, and reports measured seconds.
- A failing lesson job reports `failed` / `RuntimeError`. A question job that keeps nothing reports `empty`.
- A job for an old revision makes no model calls.
- Notes peek → `assisted: true`, `help_used: ["notes"]`, `notes_shown = 1`, no unassisted credit. Studying before a question is not help.
- An old database without `notes_shown` opens and reads 0.
- The HTTP help endpoint accepts `notes` and rejects unknown kinds.
- Fallback summaries keep whole formulas and never leave an unmatched `$`.
- "More questions" sends the questions already seen and drops exact repeats (`duplicate`).
- Saved copies of a question are hidden, and answering one after the original's solution counts as help.

# URPP Implementations 0–14 — Review and Analysis v0.1

**Date:** 2026-10-06
**Repository state:** `design/logical-decision-engine` at `faa025d` + uncommitted 14F revision (`docs/URPP_14F_revision_record_v01.md`)
**Size:** 137 commits (2026-09-18 → 2026-10-01), ~32k lines of non-test Python, 1395 passing backend tests

**Numbering caveat:** the original Implementation 0–13 roadmap was never recovered; `engineering-archive/` says so explicitly. Below, work up to 13A is grouped by what the Git history shows, not by original implementation numbers. The labels 13B–13E and 14C–14F appear in the source and docs themselves.

---

## 1. What URPP is trying to be

URPP is a **learning-control loop** for one university STEM student in one course, not a chatbot:

> Given the course requirement and current student evidence, what is the next best teaching action?

Three rules run through every phase:

1. **Evidence history is the source of truth.** Student state is always recomputed from stored evidence, never edited directly.
2. **LLMs propose, deterministic code decides.** A model may produce text or suggestions; it can never change student state, eligibility, or approval.
3. **Unknown is a valid answer.** Missing or ambiguous evidence stays `UNKNOWN`; the system must not invent certainty (fail closed).

---

## 2. Phase-by-phase history

### Phase A — Foundation and the student model (Sept 18–19)
Docs `00`–`03b`; `domain/learning/state_v02.py`, `services/student_model/`

- Product spec: twelve things V0 must demonstrate (`docs/00`).
- **Student State V0.2:** an `EvidenceEvent` records one observation about one learning objective. `estimate_objective_state()` filters events through an **eligibility policy** (alignment, validity, freshness, independence) and produces a per-objective state with explicit support levels (`insufficient`, `limited`, ...).
- Key idea: "answered correctly" does not mean "competent". Eligibility, stability, and freshness all count.

### Phase B — Assessment and scoring (Sept 19)
Docs `03c`; `services/assessment/`

- Numeric items: a restricted answer parser, deterministic scoring, and conversion into evidence events.
- Open-response items: rubric preview → human review → **HMAC-signed approval** before a score can become evidence.
- Versioned assessment-record repository; stored numeric attempts feed the student state.

### Phase C — Decision engine and orchestration (Sept 19)
Docs `03d`; `services/decision/engine_v01`, `turn_orchestrator_v01`

- Six teaching actions: diagnostic assessment, conceptual review, conceptual hint, independent practice, self-explanation, transfer assessment.
- A rule-based controller picks from the actions the policy allows and records a reason code. The orchestrator sends one decision to exactly one agent port.

### Phase D — Persistence and recovery (Sept 19)
`repositories/`, numeric session/assignment modules (about 20 commits)

- SQLite numeric assignments with atomic submit, registered sessions, foreign-key migrations, readiness audits, and a guarded engine.
- **Recoverable sessions:** after a crash, the database (not memory) decides where the lesson resumes.

### Implementation 13B–13C — Personalized teaching (Sept 19)
Docs `07_personalized…` through `11`

- 13B: a student's explicit request ("give me a hint") becomes a validated object, not free text, and maps deterministically to an allowed action. The request is **not** evidence of learning.
- 13C: personalized turns run through agent ports and recoverable SQLite sessions.

### Implementation 13D — Transfer assessment and review (Sept 19–20)
Docs `12`–`18`

- An ordinary item cannot be relabeled as "transfer" by a request.
- A transfer item needs a content-bound review draft that states both the new context and the non-transfer path.
- Delivery fails closed until approved. The phase covers reviewer authorization (identity ≠ permission ≠ authentication), version-bound review decisions, lifecycle, and application.

### Implementation 13E — Evidence-driven loop and provenance (Sept 20–22)
Docs `19`–`26`, `27`

- 13E-1/2: decisions driven by stored evidence are wired into teaching turns; a real answer changes the next action without raising mastery.
- 13E-3: assistance log (hints and solutions shown), presentation and logging boundary, and the **local numeric teaching CLI** (first thing a person can actually run).
- 13E-4: read-only provenance snapshots and review candidates. A fingerprint detects change but grants no permission.
- Follow-up: read-only "learning observations" and **shadow policies** that are evaluated next to the real decision but never act.
- `docs/27`: architecture v0.2 roadmap. Two evidence paths (teaching observations vs. mastery-eligible evidence), Canvas as a sourced input, no training on course data by default.

### Implementation 14 — The Professor (Sept 22 – Oct 6)
`services/course_knowledge/` (37 modules), `llm/`, local web

- **14C (course knowledge):** course packs with source hashes, a knowledge fetch contract, a SQLite knowledge store, a course-grounded teaching harness with traces, retry-safe turns, and a real-course pilot.
- **LU pilot:** 2×2 LU math verification gate, a policy-bounded Python computation pilot, and **NanoJev** shadow evaluation (`docs/28`–`30`: a local model proposes actions on 10 synthetic cases; developer-only, no authority).
- **LLM gateways:** a provider-neutral structured Professor adapter, plus OpenAI and local Ollama (`qwen3.5:4b`) gateways.
- **Local learning product:** text/Markdown/PDF import → course pack → durable chat sessions → guarded local web UI and CLIs; bilingual source selection; explicit "insufficient evidence" answers; MathJax rendering.
- **14D (math fidelity):** discovery that the model mangles equations from PDF text. This led to the source-verified equation records, a registry, request resolution, and a math-fidelity protocol on the LTRI CT paper (Eqs. 7, 10, 15, 16).
- **14E (benchmark):** 8 frozen cases, a runner with per-case scoped packs, L1 deterministic checks, and L2 human-review bundles. First run: `PASS=60, FAIL=4`.
- **14F (fix):** deterministic display of verified equations. It first shipped unreachable; the 2026-10-06 revision fixed it (`PASS=63, FAIL=0`, L1 v0.2).

---

## 3. What is strong

1. **Principles hold in code, not only in docs.** Evidence-first state, fail-closed gates, and "LLM cannot write state" are enforced by types and tests (1395 tests).
2. **Provenance everywhere.** Source hashes, record revisions, run manifests, and immutable benchmark runs. You can always ask "where did this come from?"
3. **Honest evaluation culture.** Frozen cases, preserved bad runs, L1 separated from L2, explicit "not a semantic verdict" wording, and NanoJev kept shadow-only.
4. **Something real exists.** A local Professor that answers from your own PDFs, refuses when evidence is missing, and now shows exact verified equations.

## 4. Main problems and risks

1. **The two halves are not connected.** Phases A–13E built a student-model and decision loop around *numeric assignments*. Implementation 14 built a *chat Professor* over course PDFs. The Professor runs on an **empty, synthetic student state** (`estimate_objective_state([])`; "No Chat message is treated as assessment evidence"). So the North Star loop (teach → assess → evidence → adapt) does not yet run on real course material. This is the biggest gap.
2. **The course model has not been built.** `docs/04` (course model), `05` (pedagogy policy), and `06` (session state machine) are still "Planned". Learning objectives are not derived from course materials; the local upload uses a single generic objective (`uploaded-material`). Implementation 15 starts on this.
3. **Infrastructure has outrun use.** Transfer review alone has six sub-stages (HMAC approvals, reviewer authorization, lifecycle) for a single-user local app with no second reviewer and no real student data yet. These are well built, but they cost review attention and are unproven by use.
4. **Math fidelity does not scale yet.** The verified-equation registry is written by hand per paper (4 equations for one paper). Explanations from the 4B model are still mathematically wrong (e.g. it says `|sin α|` is in the numerator). The benchmark has 8 cases from one paper, one model, and **no L2 review done**.
5. **The L1 metric can mislead.** Since 14F, verified blocks satisfy the equation markers, so L1 no longer measures model understanding. L1 v0.3 should score the generated part separately.
6. **Process hygiene:**
   - All 136 commits sit on `design/logical-decision-engine`; `main` only has the initial commit.
   - Doc numbers collide (`07`, `08`, `09` each used twice).
   - The original 0–13 boundaries are lost.
   - README still says "Next: Design 01B".
   - Empty packages remain (`advisor/`, `pedagogy/`, `teacher/`, `course/`).
   - 137 commits in two weeks, mostly assistant-generated, is more than one person can review deeply.

## 5. Recommendations (in order)

1. **Finish 14:** commit the 14F revision, do the L2 review of the r2 run (~30 min of your time), and add L1 v0.3 that scores the explanation separately.
2. **Try a stronger model before more scaffolding:** run the same 8 cases on `qwen3.5:9b` locally and a larger model on the planned remote PC. This tests whether explanation errors are a model-size problem.
3. **Connect the loops (proposed "14G" or early 15):** let the Professor end a topic with a short numeric/self-check item from the existing assessment pipeline, so chat produces real evidence and the decision engine chooses the next action. This is the North Star demo.
4. **Then Implementation 15** (document classification → requirements → timeline → objective dependencies), so objectives come from the syllabus instead of `uploaded-material`.
5. **Scale equation verification:** extract math with a PDF math OCR tool, then have a human confirm it, instead of writing records by hand.
6. **Hygiene:** merge or PR the design branch into `main`, renumber or index the docs, update README, remove empty packages.

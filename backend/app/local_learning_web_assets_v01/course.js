"use strict";

// Client of the Course Workspace API (docs/33, docs/35). Untrusted model text is
// turned into DOM nodes or rendered by the bounded Markdown renderer, never
// parsed as HTML.
const $ = (id) => document.getElementById(id);
const LAST_COURSE = "urpp-course-workspace-v01:last-course";
const STATUS_LABELS = {
  not_started: "Not started", learning: "Learning",
  struggling: "Needs review", practiced: "Practiced"
};
const STEP_LABELS = {
  study_lesson: "Study the notes", answer_check: "Answer a check question",
  go_to_topic: "Go to topic", review_course: "Review the course"
};
// Expected waits, shown next to the elapsed time so a long model call never
// looks like a frozen page. Measured times on this computer replace the
// defaults once a job has finished: a laptop low on memory can be 10x slower.
const TYPICAL = {
  path: "Usually under 2 minutes; longer when the computer is low on memory.",
  lesson: "Usually 1–2 minutes; longer when the computer is low on memory.",
  questions: "Several minutes: the model writes the questions, then re-solves each one."
};
function duration(seconds) {
  return seconds < 90 ? seconds + " s" : Math.round(seconds / 60) + " min";
}
function typical(kind) {
  const measured = course && course.measured_seconds && course.measured_seconds[kind];
  return measured ? "Last time on this computer: about " + duration(measured) + "." : TYPICAL[kind];
}
const POLL_MS = 3000;

let course = null;          // course view
let topic = null;           // topic view
let busy = false;
let mode = "study";         // "study" | "practice"
let currentItem = null;     // question shown in Practice
let feedback = null;        // feedback for the last submitted question
let confirmLeave = false;   // asking before the notes are opened mid-question
let studyRecorded = false;  // lesson_opened sent for this visit to Study
const peeked = new Set();   // questions during which the notes were opened
const hints = new Map();    // item_id -> hint text already shown
let pollTimer = null;
let activityTimer = null;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
}
function button(text, onClick, className) {
  const element = node("button", text, className);
  element.type = "button";
  element.addEventListener("click", onClick);
  return element;
}
function markdown(text, className) {
  const box = node("div", undefined, className);
  if (window.URPPMarkdownV01) window.URPPMarkdownV01.renderInto(box, text || "");
  else box.textContent = text || "";
  return box;
}
function setStatus(text) { $("status").textContent = text; }
function save(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* optional */ } }
function load(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }
function pending(state) { return state === "queued" || state === "working"; }

async function api(path, payload) {
  const config = {
    cache: "no-store", credentials: "omit", redirect: "error",
    headers: { "X-URPP-Local-Request": "1" }
  };
  if (payload !== undefined) {
    config.method = "POST";
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(payload);
  }
  const response = await fetch(path, config);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
  return data;
}
function courseUrl() { return "/api/courses/" + encodeURIComponent(course.course.course_id); }
function topicUrl(topicId) {
  return courseUrl() + "/topics/" + encodeURIComponent(topicId || topic.topic.topic_id);
}

// ---------------------------------------------------------------- activity

// Every user action runs here: buttons are disabled and, for anything slower
// than a moment, a spinner shows what is happening and for how long.
async function run(label, work, typical) {
  if (busy) return;
  busy = true; updateButtons(); setStatus("");
  startActivity(label, typical);
  try { await work(); }
  catch (error) { setStatus(error.message); }
  finally { stopActivity(); busy = false; updateButtons(); schedulePoll(); }
}

function startActivity(label, typical) {
  const started = Date.now();
  const queued = course && course.preparing
    ? " URPP is also preparing topics in the background; your request starts when the current step finishes."
    : "";
  $("activity-label").textContent = label;
  const tick = () => {
    const elapsed = Date.now() - started;
    $("activity-detail").textContent = Math.round(elapsed / 1000) + " s elapsed" +
      (typical ? " · " + typical : "") + queued;
    // Quick requests finish before the indicator would only flash.
    if (typical || elapsed > 600) $("activity").hidden = false;
  };
  tick();
  activityTimer = setInterval(tick, 500);
}
function stopActivity() {
  clearInterval(activityTimer);
  $("activity").hidden = true;
}

function updateButtons() {
  const hasCourse = course !== null;
  $("create-course").disabled = busy;
  $("add-document").disabled = busy || !hasCourse;
  $("build-path").disabled = busy || !hasCourse || !course.documents.length;
  for (const element of document.querySelectorAll("#topic button, #path button")) {
    element.disabled = busy || element.dataset.off === "1";
  }
}

// Background preparation (docs/35): poll while the server is still writing
// lessons or questions, and refresh only the parts that were waiting, so a
// half-typed answer is never wiped.
function schedulePoll() {
  clearTimeout(pollTimer);
  if (course && course.preparing) pollTimer = setTimeout(poll, POLL_MS);
}

async function poll() {
  if (busy || !course) { schedulePoll(); return; }
  const courseId = course.course.course_id;
  const topicId = topic ? topic.topic.topic_id : null;
  try {
    const freshCourse = await api(courseUrl());
    const freshTopic = topicId ? await api(topicUrl(topicId)) : null;
    if (busy || !course || course.course.course_id !== courseId) return;
    course = freshCourse;
    renderCourse();
    if (freshTopic && topic && topic.topic.topic_id === topicId) {
      const studyWaiting = !topic.lesson;
      const practiceWaiting = !topic.items.length;
      // Feedback being read lives outside the view, so it survives this swap.
      topic = freshTopic;
      renderProgress();
      renderNextStep();
      renderTabs();
      if (mode === "study" && studyWaiting) renderStudy();
      if (mode === "practice" && practiceWaiting) renderPractice();
      updateButtons();
    }
  } catch (_) {
    // A failed poll is retried; the student's own actions report errors.
  } finally {
    schedulePoll();
  }
}

// ---------------------------------------------------------------- courses

async function refreshCourseList(selectId) {
  const data = await api("/api/courses");
  const select = $("course-select");
  select.replaceChildren(node("option", "— Choose a course —"));
  select.firstChild.value = "";
  for (const entry of data.courses) {
    const option = node("option", entry.title);
    option.value = entry.course_id;
    select.append(option);
  }
  if (selectId) select.value = selectId;
}

async function openCourse(courseId, topicId) {
  course = await api("/api/courses/" + encodeURIComponent(courseId));
  save(LAST_COURSE, courseId);
  $("course-select").value = courseId;
  renderCourse();
  const wanted = topicId || course.recommended_topic_id;
  if (wanted && course.outline) await openTopic(wanted);
  else { topic = null; $("topic").hidden = true; }
  updateButtons();
}

async function refreshCourseOnly() {
  course = await api(courseUrl());
  renderCourse();
}

function preparationPill(entry) {
  if (entry.progress.status === "practiced") return null;
  const states = [entry.preparation.lesson.state, entry.preparation.questions.state];
  if (states.includes("working")) return node("span", "Preparing…", "pill pill-prep");
  if (states.includes("queued")) return node("span", "Queued", "pill pill-prep");
  if (states.every((state) => state === "ready")) return node("span", "Ready", "pill pill-ready");
  return null;
}

function renderCourse() {
  const docs = $("documents");
  docs.replaceChildren();
  if (!course.documents.length) docs.append(node("p", "No materials yet.", "hint"));
  for (const doc of course.documents) {
    const row = node("div", undefined, "doc-row");
    row.append(node("strong", doc.filename),
      node("span", doc.source_count + " excerpt" + (doc.source_count === 1 ? "" : "s"), "hint"));
    docs.append(row);
  }
  const path = $("path");
  path.replaceChildren();
  const outline = course.outline;
  if (!outline) {
    path.append(node("p", course.documents.length
      ? "Materials added. Build the course path to see the topics."
      : "Add materials, then build the course path.", "hint"));
    updateButtons();
    return;
  }
  const origin = outline.generator === "model_proposed"
    ? "Topics proposed by the local model (" + (outline.model || "model") + ") and checked against the sources."
    : "Topics derived from document headings (the model proposal was not usable).";
  path.append(node("p", "Revision " + outline.revision + " · " + outline.topics.length +
    " topics · " + origin, "hint"));
  if (course.preparing) {
    path.append(node("p", "Preparing notes and first questions in the background, so they are ready when you get there.", "hint"));
  }
  const list = node("ol", undefined, "path-list");
  const titles = Object.fromEntries(outline.topics.map((t) => [t.topic_id, t.title]));
  for (const entry of outline.topics) {
    const item = node("li", undefined, "path-topic status-" + entry.progress.status);
    if (topic && topic.topic.topic_id === entry.topic_id) item.classList.add("active");
    const head = node("div", undefined, "path-head");
    head.append(
      button(entry.title, () => run("Opening topic…", () => openTopic(entry.topic_id)), "link-button"),
      node("span", STATUS_LABELS[entry.progress.status], "pill pill-" + entry.progress.status));
    if (entry.topic_id === course.recommended_topic_id) head.append(node("span", "Recommended next", "pill pill-next"));
    const prep = preparationPill(entry);
    if (prep) head.append(prep);
    item.append(head);
    if (entry.summary) item.append(markdown(entry.summary, "md-body path-summary"));
    if (entry.prerequisite_topic_ids.length) {
      item.append(node("p", "Builds on: " + entry.prerequisite_topic_ids.map((id) => titles[id]).join(", "), "hint"));
    }
    if (entry.key_concepts.length) {
      const chips = node("div", undefined, "chips");
      for (const concept of entry.key_concepts) chips.append(node("span", concept, "chip"));
      item.append(chips);
    }
    item.append(node("p", "Sources: " + entry.source_labels.join(" · "), "hint"));
    list.append(item);
  }
  path.append(list);
  if (outline.unassigned_source_labels && outline.unassigned_source_labels.length) {
    path.append(node("p", "Not covered by any topic: " + outline.unassigned_source_labels.join(" · "), "hint"));
  }
  for (const warning of outline.warnings || []) path.append(node("p", warning, "hint"));
  updateButtons();
}

// ---------------------------------------------------------------- topics

// Opening a topic picks the mode from the next step: notes first for a new
// topic, a question once the notes have been studied.
async function openTopic(topicId) {
  topic = await api(topicUrl(topicId));
  const step = topic.next_step;
  const practice = step.topic_id === topicId && step.step === "answer_check";
  mode = practice ? "practice" : "study";
  currentItem = practice ? step.item_id || null : null;
  feedback = null;
  confirmLeave = false;
  studyRecorded = false;
  renderTopic();
  renderCourse();
  const url = new URL(location.href);
  url.searchParams.set("course", course.course.course_id);
  url.searchParams.set("topic", topicId);
  history.replaceState(null, "", url);
}

async function topicAction(path, payload) {
  topic = await api(topicUrl() + path, payload || {});
  await refreshCourseOnly();
  renderTopic();
  if (topic.generation) {
    const g = topic.generation;
    if (g.skipped) setStatus("The first questions were already prepared.");
    else setStatus("Added " + g.added + " question(s); rejected " + g.rejected.disagreed +
      " that failed the re-solve check and " + g.rejected.invalid + " malformed.");
  }
}

function renderTopic() {
  $("topic").hidden = false;
  const t = topic.topic;
  $("topic-eyebrow").textContent = "Topic " + t.order + " of " + course.outline.topics.length;
  $("topic-title").textContent = t.title;
  $("topic-meta").textContent = (t.prerequisite_titles.length
    ? "Builds on: " + t.prerequisite_titles.join(", ") + " · " : "") +
    "Sources: " + t.source_labels.join(" · ");
  renderProgress();
  renderNextStep();
  renderMode();
}

function renderProgress() {
  const p = topic.progress;
  $("topic-progress").replaceChildren(
    node("span", STATUS_LABELS[p.status], "pill pill-" + p.status),
    node("p", p.correct_unassisted_items + " correct without help · " +
      p.correct_assisted + " correct with help · " + p.incorrect + " incorrect"),
    node("p", "Practice observed in URPP, not verified mastery.", "hint"));
}

function renderNextStep() {
  const step = topic.next_step;
  const box = $("next-step");
  box.replaceChildren();
  box.append(
    node("strong", "Next step: " + (STEP_LABELS[step.step] || step.step) +
      (step.topic_id !== topic.topic.topic_id ? " — " + step.topic_title : "")),
    node("p", step.reason),
    node("p", "Teaching action: " + step.teaching_action.replaceAll("_", " ") +
      " · reason code: " + step.reason_code + " · " + step.policy_version, "hint"));
  if (step.step === "review_course") return;
  box.append(button("Do this now", () => {
    if (step.step === "go_to_topic") run("Opening topic…", () => openTopic(step.topic_id));
    else if (step.step === "study_lesson") setMode("study");
    else if (step.needs_more_questions) writeQuestions(true);
    else {
      if (step.item_id) currentItem = step.item_id;
      setMode("practice");
      if (mode === "practice") renderPractice();
    }
  }));
  updateButtons();
}

// ---------------------------------------------------------------- modes

function renderTabs() {
  const count = topic.items.length;
  $("tab-practice").textContent = "Practice" +
    (count ? " (" + count + " question" + (count === 1 ? "" : "s") + ")" : "");
}

function renderMode() {
  renderTabs();
  $("tab-study").setAttribute("aria-selected", String(mode === "study"));
  $("tab-practice").setAttribute("aria-selected", String(mode === "practice"));
  $("study-pane").hidden = mode !== "study";
  $("practice-pane").hidden = mode !== "practice";
  if (mode === "study") renderStudy(); else renderPractice();
  updateButtons();
}

// A question is "in progress" when it is on screen, unanswered, and the notes
// have not been opened for it yet. Leaving it for the notes counts as help.
function questionInProgress() {
  return mode === "practice" && currentItem !== null && topic.lesson !== null &&
    !(feedback && feedback.item_id === currentItem) && !peeked.has(currentItem) &&
    topic.items.some((item) => item.item_id === currentItem);
}

function setMode(next) {
  if (next === "study" && questionInProgress()) {
    confirmLeave = true;
    renderPractice();
    updateButtons();
    return;
  }
  if (next !== mode) studyRecorded = false;
  mode = next;
  confirmLeave = false;
  renderMode();
}

// Seeing the notes is the "lesson opened" observation the next-step policy uses.
async function recordStudy() {
  if (studyRecorded || !topic.lesson) return;
  studyRecorded = true;
  const topicId = topic.topic.topic_id;
  try {
    const view = await api(topicUrl(topicId) + "/lesson", {});
    if (!topic || topic.topic.topic_id !== topicId) return;
    topic.progress = view.progress;
    topic.next_step = view.next_step;
    renderProgress();
    renderNextStep();
    await refreshCourseOnly();
  } catch (error) { setStatus(error.message); }
}

function waiting(title, status, typical) {
  const box = node("div", undefined, "waiting");
  const text = node("div");
  text.append(node("strong", title),
    node("p", (status.state === "working"
      ? "Working for " + duration(status.seconds || 0) + ". "
      : "Waiting for the local model. ") + typical + " This page updates by itself.", "hint"));
  box.append(node("span", undefined, "spinner"), text);
  return box;
}

function lessonNodes(lesson) {
  const parts = [
    node("p", "Generated by " + lesson.model + " from the course sources · not verified · cites: " +
      lesson.source_labels.join(" · "), "label-generated"),
    markdown(lesson.explanation_markdown, "md-body lesson-text")
  ];
  if (lesson.worked_example_markdown) {
    parts.push(node("h4", "Worked example"), markdown(lesson.worked_example_markdown, "md-body lesson-text"));
  }
  return parts;
}

function renderStudy() {
  const box = $("study-pane");
  box.replaceChildren();
  const lesson = topic.lesson;
  const prep = topic.preparation.lesson;
  if (lesson) {
    const row = node("div", undefined, "row");
    row.append(button("Start practice", () => setMode("practice")));
    box.append(...lessonNodes(lesson), row);
    recordStudy();
    return;
  }
  if (pending(prep.state)) {
    box.append(waiting("Preparing the notes for this topic…", prep, typical("lesson")));
    return;
  }
  box.append(node("p", prep.state === "failed"
    ? "Preparing the notes in the background did not work. You can try again now."
    : "The notes are written from this topic's sources.", "hint"));
  box.append(button("Write the notes now", () =>
    run("Writing the notes with the local model…", async () => {
      studyRecorded = true;  // the lesson endpoint records this visit itself
      await topicAction("/lesson");
    }, typical("lesson"))));
}

function writeQuestions(more) {
  run("Writing and re-solving check questions…", async () => {
    await topicAction("/questions", { more });
    currentItem = null;
    feedback = null;
    mode = "practice";
    renderMode();
  }, typical("questions"));
}

// The next question: the one the policy chose, else an unanswered one.
function pickItem(exclude) {
  const step = topic.next_step;
  if (step.item_id && step.item_id !== exclude &&
      topic.items.some((item) => item.item_id === step.item_id)) return step.item_id;
  const open = topic.items.filter((item) => !item.answered_correctly && item.item_id !== exclude);
  const fresh = open.filter((item) => item.attempts === 0);
  return (fresh[0] || open[0] || { item_id: null }).item_id;
}

function renderPractice() {
  const area = $("question-area");
  area.replaceChildren();
  const prep = topic.preparation.questions;
  if (!topic.items.length) {
    if (pending(prep.state)) {
      area.append(waiting("Preparing the first check questions…", prep, typical("questions")));
      return;
    }
    area.append(node("p", prep.state === "empty"
      ? "No question passed the re-solve check last time. Try writing a new set."
      : prep.state === "failed"
        ? "Preparing questions in the background did not work. You can try again now."
        : "No check questions yet.", "hint"),
    button("Write check questions now", () => writeQuestions(false)));
    return;
  }
  if (!topic.items.some((item) => item.item_id === currentItem)) currentItem = pickItem(null);
  if (currentItem === null) {
    area.append(node("p", "You have answered every question in this set correctly.", "hint"),
      button("Write more questions", () => writeQuestions(true)));
    return;
  }
  area.append(questionCard(currentItem));
}

function questionCard(itemId) {
  const index = topic.items.findIndex((item) => item.item_id === itemId);
  const item = topic.items[index];
  const answered = feedback !== null && feedback.item_id === itemId;
  const card = node("div", undefined, "question");
  card.dataset.item = item.item_id;
  const head = node("div", undefined, "practice-head");
  head.append(node("strong", "Question " + (index + 1) + " of " + topic.items.length),
    node("span", item.answered_correctly ? "answered correctly before"
      : item.attempts ? item.attempts + " attempt(s) so far" : "new"));
  card.append(head, markdown(item.question, "md-body"));

  const input = node("input");
  input.type = "text";
  input.maxLength = 64;
  input.placeholder = item.kind === "multiple_choice" ? "A, B, C, or D" : "One number";
  if (item.kind === "multiple_choice") {
    const choices = node("ol", undefined, "choices");
    item.choices.forEach((choice, i) => {
      const li = node("li");
      const pick = button("ABCD"[i], () => { input.value = "ABCD"[i]; }, "choice-letter");
      if (answered) pick.dataset.off = "1";
      li.append(pick, markdown(choice, "md-body"));
      choices.append(li);
    });
    card.append(choices);
  }

  if (!answered) {
    const submit = () => run("Checking your answer…", async () => {
      topic = await api("/api/questions/" + encodeURIComponent(item.item_id) + "/answer", { answer: input.value });
      feedback = topic.feedback;
      await refreshCourseOnly();
      renderTopic();
    });
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") submit(); });
    const form = node("div", undefined, "answer-row");
    form.append(input, button("Submit", submit));
    const help = node("div", undefined, "row");
    help.append(button("Hint", () => run("Showing hint…", async () => {
      const shown = await api("/api/questions/" + encodeURIComponent(item.item_id) + "/help", { kind: "hint" });
      hints.set(item.item_id, shown.text);
      renderPractice();
    }), "secondary"));
    if (topic.lesson && !peeked.has(item.item_id)) {
      help.append(button("Peek at the notes (counts as help)", () => peekNotes(item.item_id, false), "secondary"));
    }
    card.append(form, help);
  }
  if (hints.has(item.item_id)) card.append(markdown("**Hint:** " + hints.get(item.item_id), "md-body help-box"));
  if (answered) card.append(feedbackBox(feedback));
  card.append(node("p", "Sources: " + item.source_labels.join(" · ") + " · key check: re-solve agreed", "hint"));

  if (confirmLeave && !answered) {
    const confirm = node("div", undefined, "confirm-box");
    const row = node("div", undefined, "row");
    row.append(
      button("Open the notes (counts as help)", () => peekNotes(item.item_id, true)),
      button("Keep practicing", () => { confirmLeave = false; renderPractice(); updateButtons(); }, "secondary"));
    confirm.append(node("p", "This question is still open. Opening the notes now counts as help for it, like a hint."), row);
    card.append(confirm);
  }
  if (peeked.has(item.item_id) && topic.lesson && !answered) {
    const notes = node("div", undefined, "notes-peek");
    notes.append(node("strong", "Notes (opened during this question: counts as help)"), ...lessonNodes(topic.lesson));
    card.append(notes);
  }
  return card;
}

function peekNotes(itemId, thenStudy) {
  run("Opening the notes…", async () => {
    await api("/api/questions/" + encodeURIComponent(itemId) + "/help", { kind: "notes" });
    peeked.add(itemId);
    confirmLeave = false;
    if (thenStudy) setMode("study");
    else renderPractice();
  });
}

function feedbackBox(result) {
  const box = node("div", undefined, "feedback " + (result.correct ? "correct" : "incorrect"));
  const help = result.help_used && result.help_used.length
    ? " (" + result.help_used.join(", ") + ")" : "";
  box.append(node("strong", result.correct
    ? (result.assisted ? "Correct, with help" + help + "." : "Correct, without help.")
    : "Not correct. Expected: " + result.expected_answer));
  if (result.solution) box.append(markdown("**Solution:** " + result.solution, "md-body"));
  const row = node("div", undefined, "row");
  const next = pickItem(result.item_id);
  if (next) {
    row.append(button("Next question", () => {
      currentItem = next;
      feedback = null;
      renderPractice();
      updateButtons();
      const input = document.querySelector("#question-area input");
      if (input) input.focus();
    }));
  } else {
    row.append(button("Write more questions", () => writeQuestions(true)));
  }
  if (topic.lesson) row.append(button("Review the notes", () => setMode("study"), "secondary"));
  box.append(row);
  return box;
}

// ---------------------------------------------------------------- wiring

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(new Error("Could not read the selected file."));
    reader.readAsDataURL(file);
  });
}

$("create-course").addEventListener("click", () => run("Creating course…", async () => {
  const created = await api("/api/courses", { title: $("course-title").value });
  $("course-title").value = "";
  await refreshCourseList(created.course_id);
  await openCourse(created.course_id);
}));
$("course-select").addEventListener("change", () => {
  const id = $("course-select").value;
  if (id) run("Opening course…", () => openCourse(id));
});
$("add-document").addEventListener("click", () => run("Importing material…", async () => {
  const file = $("material").files[0];
  if (!file) throw new Error("Choose a file first.");
  if (!$("permission").checked) throw new Error("Confirm you may use this material locally.");
  course = await api(courseUrl() + "/documents", {
    filename: file.name, file_base64: await readFile(file), allow_local_teaching: true
  });
  $("material").value = "";
  renderCourse();
}));
$("build-path").addEventListener("click", () => run("Building the course path with the local model…", async () => {
  course = await api(courseUrl() + "/outline", {});
  topic = null;
  renderCourse();
  if (course.recommended_topic_id) await openTopic(course.recommended_topic_id);
}, TYPICAL.path));
$("tab-study").addEventListener("click", () => setMode("study"));
$("tab-practice").addEventListener("click", () => setMode("practice"));

(async () => {
  updateButtons();
  const params = new URL(location.href).searchParams;
  const courseId = params.get("course") || load(LAST_COURSE);
  try {
    await refreshCourseList(courseId);
    if (courseId && $("course-select").value === courseId) await openCourse(courseId, params.get("topic"));
  } catch (error) { setStatus(error.message); }
  schedulePoll();
})();

"use strict";

// Client of the Course Workspace API (docs/33). Untrusted model text is turned
// into DOM nodes or rendered by the bounded Markdown renderer, never parsed as HTML.
const $ = (id) => document.getElementById(id);
const LAST_COURSE = "urpp-course-workspace-v01:last-course";
const STATUS_LABELS = {
  not_started: "Not started", learning: "Learning",
  struggling: "Needs review", practiced: "Practiced"
};
const STEP_LABELS = {
  study_lesson: "Open the lesson", answer_check: "Answer a check question",
  go_to_topic: "Go to topic", review_course: "Review the course"
};
let course = null;     // course view
let topic = null;      // topic view
let busy = false;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
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

async function run(label, work) {
  if (busy) return;
  busy = true; updateButtons(); setStatus(label);
  try { await work(); }
  catch (error) { setStatus(error.message); return; }
  finally { busy = false; updateButtons(); }
  if ($("status").textContent === label) setStatus("Done.");
}

function updateButtons() {
  const hasCourse = course !== null;
  $("create-course").disabled = busy;
  $("add-document").disabled = busy || !hasCourse;
  $("build-path").disabled = busy || !hasCourse || !course.documents.length;
  $("more-questions").disabled = busy || topic === null;
  for (const button of document.querySelectorAll("#topic button, #path button")) {
    if (button.id !== "more-questions") button.disabled = busy;
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
    return;
  }
  const origin = outline.generator === "model_proposed"
    ? "Topics proposed by the local model (" + (outline.model || "model") + ") and checked against the sources."
    : "Topics derived from document headings (the model proposal was not usable).";
  path.append(node("p", "Revision " + outline.revision + " · " + outline.topics.length +
    " topics · " + origin, "hint"));
  const list = node("ol", undefined, "path-list");
  const titles = Object.fromEntries(outline.topics.map((t) => [t.topic_id, t.title]));
  for (const entry of outline.topics) {
    const item = node("li", undefined, "path-topic status-" + entry.progress.status);
    if (topic && topic.topic.topic_id === entry.topic_id) item.classList.add("active");
    const head = node("div", undefined, "path-head");
    const button = node("button", entry.title, "link-button");
    button.type = "button";
    button.addEventListener("click", () => run("Opening topic…", () => openTopic(entry.topic_id)));
    head.append(button, node("span", STATUS_LABELS[entry.progress.status], "pill pill-" + entry.progress.status));
    if (entry.topic_id === course.recommended_topic_id) head.append(node("span", "Recommended next", "pill pill-next"));
    item.append(head);
    if (entry.summary) item.append(node("p", entry.summary, "path-summary"));
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
}

// ---------------------------------------------------------------- topics

async function openTopic(topicId) {
  topic = await api("/api/courses/" + encodeURIComponent(course.course.course_id) +
    "/topics/" + encodeURIComponent(topicId));
  renderTopic();
  renderCourse();
  const url = new URL(location.href);
  url.searchParams.set("course", course.course.course_id);
  url.searchParams.set("topic", topicId);
  history.replaceState(null, "", url);
}

async function topicAction(path) {
  const base = "/api/courses/" + encodeURIComponent(course.course.course_id) +
    "/topics/" + encodeURIComponent(topic.topic.topic_id);
  topic = await api(base + path, {});
  await refreshCourseOnly();
  renderTopic();
  if (topic.generation) {
    const g = topic.generation;
    setStatus("Added " + g.added + " question(s); rejected " + g.rejected.disagreed +
      " that failed the re-solve check and " + g.rejected.invalid + " malformed.");
  }
}

async function refreshCourseOnly() {
  course = await api("/api/courses/" + encodeURIComponent(course.course.course_id));
  renderCourse();
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
  renderLesson();
  renderQuestions();
  updateButtons();
}

function renderProgress() {
  const p = topic.progress;
  const box = $("topic-progress");
  box.replaceChildren(
    node("span", STATUS_LABELS[p.status], "pill pill-" + p.status),
    node("p", p.correct_unassisted_items + " correct without help · " +
      p.correct_assisted + " correct with help · " + p.incorrect + " incorrect"),
    node("p", "Practice observed in URPP, not verified mastery.", "hint"));
}

function renderNextStep() {
  const step = topic.next_step;
  const box = $("next-step");
  box.replaceChildren();
  const label = node("strong", "Next step: " + (STEP_LABELS[step.step] || step.step) +
    (step.topic_id !== topic.topic.topic_id ? " — " + step.topic_title : ""));
  box.append(label, node("p", step.reason),
    node("p", "Teaching action: " + step.teaching_action.replaceAll("_", " ") +
      " · reason code: " + step.reason_code + " · " + step.policy_version, "hint"));
  const go = node("button", "Do this now");
  go.type = "button";
  go.addEventListener("click", () => {
    if (step.step === "go_to_topic") run("Opening topic…", () => openTopic(step.topic_id));
    else if (step.step === "study_lesson") run("Writing the lesson with the local model…", () => topicAction("/lesson"));
    else if (step.step === "answer_check") {
      if (step.needs_more_questions) run("Writing and re-solving check questions…", () => topicAction("/questions"));
      else {
        const card = document.querySelector('[data-item="' + step.item_id + '"]');
        if (card) { card.scrollIntoView({ block: "center" }); const input = card.querySelector("input"); if (input) input.focus(); }
      }
    }
  });
  if (step.step !== "review_course") box.append(go);
}

function renderLesson() {
  const box = $("lesson");
  box.replaceChildren();
  const lesson = topic.lesson;
  if (!lesson) {
    const open = node("button", "Open the lesson");
    open.type = "button";
    open.addEventListener("click", () => run("Writing the lesson with the local model…", () => topicAction("/lesson")));
    box.append(node("p", "The lesson is written from this topic's sources the first time you open it.", "hint"), open);
    return;
  }
  box.append(node("p", "Generated by " + lesson.model + " from the course sources · not verified · cites: " +
    lesson.source_labels.join(" · "), "label-generated"));
  box.append(markdown(lesson.explanation_markdown, "md-body lesson-text"));
  if (lesson.worked_example_markdown) {
    box.append(node("h4", "Worked example"), markdown(lesson.worked_example_markdown, "md-body lesson-text"));
  }
}

function renderQuestions() {
  const box = $("questions");
  box.replaceChildren();
  if (!topic.items.length) box.append(node("p", "No check questions yet.", "hint"));
  topic.items.forEach((item, index) => box.append(questionCard(item, index + 1)));
  $("more-questions").textContent = topic.items.length ? "Generate more check questions" : "Generate check questions";
}

function questionCard(item, number) {
  const card = node("div", undefined, "question");
  card.dataset.item = item.item_id;
  const state = item.answered_correctly ? " · answered correctly" : item.attempts ? " · " + item.attempts + " attempt(s)" : "";
  card.append(node("strong", "Question " + number + state));
  card.append(markdown(item.question, "md-body"));
  const form = node("div", undefined, "answer-row");
  const input = node("input");
  input.type = "text";
  input.maxLength = 64;
  if (item.kind === "multiple_choice") {
    const choices = node("ol", undefined, "choices");
    item.choices.forEach((choice, i) => {
      const li = node("li");
      const pick = node("button", "ABCD"[i], "choice-letter");
      pick.type = "button";
      pick.addEventListener("click", () => { input.value = "ABCD"[i]; });
      li.append(pick, markdown(choice, "md-body"));
      choices.append(li);
    });
    card.append(choices);
    input.placeholder = "A, B, C, or D";
  } else {
    input.placeholder = "One number";
  }
  const submit = node("button", "Submit");
  submit.type = "button";
  submit.addEventListener("click", () => run("Checking your answer…", async () => {
    topic = await api("/api/questions/" + encodeURIComponent(item.item_id) + "/answer", { answer: input.value });
    const feedback = topic.feedback;
    await refreshCourseOnly();
    renderTopic();
    const fresh = document.querySelector('[data-item="' + item.item_id + '"]');
    if (fresh) showFeedback(fresh, feedback);
  }));
  const hint = node("button", "Hint", "secondary");
  hint.type = "button";
  hint.addEventListener("click", () => run("Showing hint…", async () => {
    const help = await api("/api/questions/" + encodeURIComponent(item.item_id) + "/help", { kind: "hint" });
    card.append(markdown("**Hint:** " + help.text, "md-body help-box"));
  }));
  form.append(input, submit, hint);
  card.append(form, node("p", "Sources: " + item.source_labels.join(" · ") + " · key check: re-solve agreed", "hint"));
  return card;
}

function showFeedback(card, feedback) {
  const box = node("div", undefined, "feedback " + (feedback.correct ? "correct" : "incorrect"));
  box.append(node("strong", feedback.correct
    ? (feedback.assisted ? "Correct, with help." : "Correct, without help.")
    : "Not correct. Expected: " + feedback.expected_answer));
  if (feedback.solution) box.append(markdown("**Solution:** " + feedback.solution, "md-body"));
  card.append(box);
  card.scrollIntoView({ block: "center" });
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
  course = await api("/api/courses/" + encodeURIComponent(course.course.course_id) + "/documents", {
    filename: file.name, file_base64: await readFile(file), allow_local_teaching: true
  });
  $("material").value = "";
  renderCourse();
}));
$("build-path").addEventListener("click", () => run("Building the course path with the local model…", async () => {
  course = await api("/api/courses/" + encodeURIComponent(course.course.course_id) + "/outline", {});
  topic = null;
  renderCourse();
  if (course.recommended_topic_id) await openTopic(course.recommended_topic_id);
}));
$("more-questions").addEventListener("click", () =>
  run("Writing and re-solving check questions…", () => topicAction("/questions")));

(async () => {
  updateButtons();
  const params = new URL(location.href).searchParams;
  const courseId = params.get("course") || load(LAST_COURSE);
  try {
    await refreshCourseList(courseId);
    if (courseId && $("course-select").value === courseId) await openCourse(courseId, params.get("topic"));
  } catch (error) { setStatus(error.message); }
})();

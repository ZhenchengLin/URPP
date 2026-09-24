"use strict";

// This UI is only a client of the existing API; it never writes data directly.
const el = (id) => document.getElementById(id);
const lastKey = "urpp-local-learning-v01:last-session";
let active = null;
let messageCount = 0;
let busy = false;

function setStatus(value) { el("status").textContent = value; }
function updateButtons() {
  el("send").disabled = busy || active === null;
  el("refresh").disabled = busy || active === null;
  el("upload").disabled = busy;
  el("resume").disabled = busy;
  el("inspect").disabled = busy || active === null;
}
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
function render(snapshot) {
  messageCount = snapshot.message_count;
  const log = el("history");
  log.replaceChildren();
  if (!snapshot.messages.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "Session 已创建，可以开始提问。";
    log.append(empty);
  }
  for (const entry of snapshot.messages) {
    const box = document.createElement("div");
    box.className = "message " + (entry.role === "student" ? "student" : "professor");
    const label = document.createElement("strong");
    const names = {
      course_grounded: "资料回答",
      insufficient_evidence: "资料不足",
      general_knowledge: "一般知识",
      legacy_unclassified: "旧记录 · 来源未分类"
    };
    label.textContent = entry.role === "student" ? "You" :
      "Professor · " + (names[entry.answer_status] || "来源未分类");
    const body = document.createElement("div");
    // Untrusted model text is converted to safe DOM nodes, never parsed as HTML.
    if (entry.role === "professor" && entry.answer_status !== "insufficient_evidence") {
      window.URPPMarkdownV01.renderInto(body, entry.text);
    } else {
      body.textContent = entry.text;
    }
    box.append(label, body);
    log.append(box);
  }
  log.scrollTop = log.scrollHeight;
  el("session").textContent = "Session ID: " + snapshot.session_id +
    "\nSaved turns: " + snapshot.turn_count +
    "\nPack SHA-256: " + snapshot.pack_sha256;
  renderGenerated(snapshot.messages);
}
function node(tag, value, className) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  item.textContent = value;
  return item;
}
function renderGenerated(messages) {
  const output = el("generated-view");
  output.replaceChildren();
  const generated = messages.filter((message) => message.role === "professor");
  if (!generated.length) {
    output.append(node("p", "这段 Session 尚无模型回答。", "hint"));
    return;
  }
  generated.forEach((message, index) => {
    const item = node("article", "", "model-output");
    const label = message.answer_status === "insufficient_evidence" ?
      "系统资料不足提示" : message.answer_status === "legacy_unclassified" ?
      "旧回复 · 生成来源未分类" : "模型回答 · " +
      (message.answer_status || "来源未分类");
    item.append(node("strong", "回复 " + (index + 1) + " · " + label));
    const detail = node("div", "");
    if (message.answer_status === "insufficient_evidence") {
      detail.textContent = message.text;
    } else {
      window.URPPMarkdownV01.renderInto(detail, message.text);
    }
    item.append(detail);
    output.append(item);
  });
}
function renderCoursePack(pack) {
  const view = el("pack-view");
  view.replaceChildren();
  const flow = node("div", "", "pack-flow");
  const steps = [
    ["1 · 保存原件", "上传文件以 SHA-256 标识"],
    ["2 · 提取原文", pack.sources.length + " 段带出处摘录"],
    ["3 · 建立资料包", "目标 + 摘录引用；版本固定"],
    ["4 · 教授对话", "回答见下方，生成后持久保存"]
  ];
  for (const [title, description] of steps) {
    const item = node("div", "", "pack-step");
    item.append(node("strong", title), node("span", description));
    flow.append(item);
  }
  view.append(flow);
  const info = node("dl", "", "pack-meta");
  for (const [label, value] of [
    ["资料包", pack.pack_id], ["Pack SHA-256", pack.pack_sha256],
    ["学习目标来源", "你在上传时填写"], ["学习目标", pack.objective.description],
    ["课程路径", "尚未由模型生成；当前只有一个学习目标"]
  ]) {
    info.append(node("dt", label), node("dd", value));
  }
  view.append(info, node("h3", "资料包里的原文摘录（点击展开）"));
  for (const [index, source] of pack.sources.entries()) {
    const detail = node("details", "", "excerpt");
    const where = source.pages ? " · 第 " + source.pages + " 页" : "";
    detail.append(node("summary", "摘录 " + (index + 1) + " · " + source.filename + where));
    detail.append(node("p", "Source ID: " + source.source_id +
      " · 原文内容 SHA-256: " + source.content_sha256, "hint"));
    detail.append(node("pre", source.excerpt_text));
    view.append(detail);
  }
}
async function loadCoursePack() {
  if (!active) throw new Error("No active Session.");
  const query = new URLSearchParams({ pack_sha256: active.pack_sha256 });
  const pack = await api("/api/session/" + encodeURIComponent(active.session_id) +
    "/course-pack?" + query);
  renderCoursePack(pack);
}
function remember(snapshot) {
  active = { session_id: snapshot.session_id, pack_sha256: snapshot.pack_sha256 };
  // A Session ID is sensitive local state; do not sync or share this browser profile.
  localStorage.setItem(lastKey, JSON.stringify(active));
  render(snapshot);
  updateButtons();
}
async function refresh() {
  if (!active) throw new Error("No active Session.");
  const query = new URLSearchParams({ pack_sha256: active.pack_sha256 });
  const snapshot = await api("/api/session/" + encodeURIComponent(active.session_id) + "?" + query);
  render(snapshot);
  return snapshot;
}
function fileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取选择的资料。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.readAsDataURL(file);
  });
}
async function run(fn) {
  if (busy) return;
  busy = true;
  updateButtons();
  try { await fn(); }
  catch (error) { setStatus(error instanceof Error ? error.message : "Operation failed."); }
  finally { busy = false; updateButtons(); }
}
el("upload").addEventListener("click", () => run(async () => {
  const file = el("material").files[0];
  if (!file) throw new Error("请选择资料文件。");
  if (!el("permission").checked) throw new Error("请先确认本地教学使用权限。");
  const ext = file.name.toLowerCase().split(".").pop();
  const limit = ext === "pdf" ? 8 * 1024 * 1024 : 128 * 1024;
  if (!["txt", "md", "markdown", "pdf"].includes(ext) || file.size === 0 || file.size > limit) {
    throw new Error("文件类型或大小不受支持。");
  }
  setStatus("正在导入资料……");
  const snapshot = await api("/api/upload", {
    filename: file.name, file_base64: await fileBase64(file),
    objective_description: el("objective").value.trim(), allow_local_teaching: true
  });
  remember(snapshot);
  await loadCoursePack();
  setStatus("资料已导入，Session 已保存在本地。");
}));
el("resume").addEventListener("click", () => run(async () => {
  const saved = JSON.parse(localStorage.getItem(lastKey) || "null");
  if (!saved || typeof saved.session_id !== "string" || typeof saved.pack_sha256 !== "string") {
    throw new Error("浏览器中没有可恢复的最近 Session。");
  }
  active = saved;
  await refresh();
  await loadCoursePack();
  setStatus("已从 SQLite 恢复对话。");
}));
el("refresh").addEventListener("click", () => run(async () => {
  await refresh();
  await loadCoursePack();
  setStatus("已重新加载对话历史。");
}));
el("inspect").addEventListener("click", () => run(async () => {
  await loadCoursePack();
  setStatus("已重新读取保存的 Course Pack。");
}));
el("send").addEventListener("click", () => run(async () => {
  if (!active) throw new Error("请先导入资料或恢复 Session。");
  const question = el("question").value.trim();
  if (!question || question.length > 1500) throw new Error("问题应为 1–1500 个字符。");
  setStatus("本地 Professor 正在生成回答……");
  try {
    const snapshot = await api("/api/chat", {
      ...active, student_text: question, expected_message_count: messageCount,
      mode: el("answer-mode").value
    });
    render(snapshot);
    el("question").value = "";
    setStatus("本轮对话已保存。");
  } catch (error) {
    // The server might have committed a turn before a connection error.
    try { await refresh(); } catch { /* Keep the original error. */ }
    throw error;
  }
}));
if (localStorage.getItem(lastKey)) {
  setStatus("检测到最近的 Session；点击左侧按钮恢复。");
}

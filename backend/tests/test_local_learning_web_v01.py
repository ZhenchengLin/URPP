"""14D-2C: offline UI wiring and API reuse; no Ollama inference."""

import base64

from fastapi.testclient import TestClient

from app.local_learning_web_v01 import create_local_learning_web_v01
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)


class FakeGateway:
    def generate_structured(self, *, prompt_name, payload):
        return {
            "content": "The supplied notes define a line integral.",
            "source_ids": [payload["sources"][0]["source_id"]],
        }


def client_for(tmp_path, *, allow_test_host=True):
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "workspace", gateway_factory=FakeGateway,
    )
    return TestClient(create_local_learning_web_v01(
        workspace=workspace, allow_test_host=allow_test_host,
    ))


def test_html_csp_and_local_assets(tmp_path):
    client = client_for(tmp_path)
    page = client.get("/")
    assert page.status_code == 200
    assert "导入学习资料" in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["cache-control"] == "no-store"
    assert "<script src=\"/assets/local-learning.js\" defer>" in page.text
    assert "<script>" not in page.text
    script = client.get("/assets/local-learning.js")
    style = client.get("/assets/local-learning.css")
    assert script.status_code == style.status_code == 200
    assert "X-URPP-Local-Request" in script.text
    assert "body.textContent = entry.text" in script.text
    assert "innerHTML" not in script.text
    assert "grid-template-columns" in style.text


def test_host_guard_covers_ui_assets(tmp_path):
    client = client_for(tmp_path)
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/assets/local-learning.js", headers={"Host": "evil.example"}).status_code == 403
    assert client_for(tmp_path / "other", allow_test_host=False).get("/").status_code == 403


def test_web_entrypoint_uses_existing_upload_chat_resume_api(tmp_path):
    client = client_for(tmp_path)
    payload = {
        "filename": "notes.md",
        "file_base64": base64.b64encode(b"# CT notes\nProjection is a line integral.").decode(),
        "objective_description": "Explain CT projection.",
        "allow_local_teaching": True,
    }
    headers = {"X-URPP-Local-Request": "1"}
    response = client.post("/api/upload", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    session = response.json()
    turn = client.post("/api/chat", json={
        "session_id": session["session_id"],
        "pack_sha256": session["pack_sha256"],
        "student_text": "Explain projection.",
        "expected_message_count": 0,
    }, headers=headers)
    assert turn.status_code == 200, turn.text
    assert turn.json()["turn_count"] == 1
    resumed = client.get("/api/session/" + session["session_id"], params={
        "pack_sha256": session["pack_sha256"],
    })
    assert resumed.status_code == 200
    assert resumed.json()["messages"] == turn.json()["messages"]


def test_inspector_ui_uses_saved_pack_and_safe_text_rendering(tmp_path):
    client = client_for(tmp_path)
    page = client.get("/").text
    script = client.get("/assets/local-learning.js").text
    assert "Course Pack · 建立过程与内容" in page
    assert "Professor 生成的回答与系统提示" in page
    assert "/course-pack?" in script
    assert 'detail.append(node("pre", source.excerpt_text))' in script
    assert 'window.URPPMarkdownV01.renderInto(detail, message.text)' in script
    assert "innerHTML" not in script


def test_markdown_display_is_local_and_does_not_weaken_html_boundary(tmp_path):
    client = client_for(tmp_path)
    page = client.get("/")
    assert page.status_code == 200
    assert page.text.index('/assets/local-learning-markdown.js') < page.text.index('/assets/local-learning.js')
    assert "script-src 'self'" in page.headers["content-security-policy"]
    markdown = client.get("/assets/local-learning-markdown.js")
    assert markdown.status_code == 200
    assert "renderInto" in markdown.text
    assert "document.createElement" in markdown.text
    assert "innerHTML" not in markdown.text
    assert "DOMParser" not in markdown.text
    assert "textContent" in markdown.text
    assert client.get("/assets/local-learning-markdown.js", headers={"Host": "evil.example"}).status_code == 403
    app = client.get("/assets/local-learning.js").text
    assert 'window.URPPMarkdownV01.renderInto(body, entry.text)' in app
    assert 'window.URPPMarkdownV01.renderInto(detail, message.text)' in app
    assert 'body.textContent = entry.text' in app  # Student/system text stays literal.


def test_markdown_renderer_offline_node_dom_smoke(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    import pytest

    if shutil.which("node") is None:
        pytest.skip("Node.js unavailable; static browser asset contract checked separately")
    script = Path(__file__).resolve().parents[1] / "app" / "local_learning_web_assets_v01" / "markdown_v01.js"
    js = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
class El {
  constructor(tag) { this.tagName = tag; this.childNodes = []; this._text = "";
    this.className = ""; this.classList = {add: () => {}}; }
  set textContent(value) { this._text = String(value); this.childNodes = []; }
  get textContent() { return this._text + this.childNodes.map(x => x.textContent).join(""); }
  append(...items) { this.childNodes.push(...items); }
  replaceChildren(...items) { this._text = ""; this.childNodes = items; }
}
globalThis.document = {
  createElement: (tag) => new El(tag),
  createTextNode: (text) => { const n = new El("#text"); n.textContent = text; return n; }
};
vm.runInThisContext(fs.readFileSync(process.argv[1], "utf8"));
const output = new El("div");
const dangerous = `<img src=x onerror=alert(1)> <script>alert(1)</script>`;
const raw = "# Intro\n\n**bold** and *italic* and `code`\n\n1. first\n2. second\n\n- alpha\n- beta\n\n```js\n" + dangerous + "\n```\n\n$$\nh_{eff} = \\frac{a}{b}\n$$\n\n" + dangerous;
URPPMarkdownV01.renderInto(output, raw);
const tags = [];
function visit(n) { tags.push(n.tagName); n.childNodes.forEach(visit); }
visit(output);
for (const tag of ["h4", "strong", "em", "code", "ol", "ul", "li", "pre", "p"]) assert(tags.includes(tag), tag);
assert(!tags.includes("script"));
assert(!tags.includes("img"));
assert(!tags.includes("a"));
assert(output.textContent.includes(dangerous));
assert(output.textContent.includes("h_{eff} = \\frac{a}{b}"));
URPPMarkdownV01.renderInto(output, "**replacement**");
assert(!output.textContent.includes("onerror"));
assert(output.textContent.includes("replacement"));
assert.throws(() => URPPMarkdownV01.renderInto(output, "x".repeat(20001)), TypeError);
'''
    completed = subprocess.run(
        ["node", "-e", js, str(script)], text=True, capture_output=True,
        timeout=15, check=False,
    )
    assert completed.returncode == 0, completed.stderr

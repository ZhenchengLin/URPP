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
    assert 'item.append(node("div", message.text))' in script
    assert "innerHTML" not in script

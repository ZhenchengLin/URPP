"""14D-3B1: explicit source-free general mode; all model output is fake."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.llm.local_general_knowledge_gateway_v01 import LocalGeneralKnowledgeGatewayV01
from app.local_learning_web_v01 import create_local_learning_web_v01
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01


class CourseGateway:
    def __init__(self):
        self.calls = []

    def generate_structured(self, *, prompt_name, payload):
        self.calls.append(payload)
        return {"content": "Course answer.", "source_ids": [payload["sources"][0]["source_id"]]}


class GeneralGateway:
    def __init__(self):
        self.contexts = []

    def generate_general(self, *, context):
        self.contexts.append(context)
        return "2"


def make_client(tmp_path):
    course, general = CourseGateway(), GeneralGateway()
    root = tmp_path / "private"
    workspace = LocalLearningWorkspaceV01(
        data_root=root,
        gateway_factory=lambda: course,
        general_gateway_factory=lambda: general,
    )
    return TestClient(create_local_learning_web_v01(
        workspace=workspace, allow_test_host=True,
    )), course, general


def upload(client):
    response = client.post("/api/upload", headers={"X-URPP-Local-Request": "1"}, json={
        "filename": "notes.md",
        "file_base64": base64.b64encode(b"# CT notes\nProjection is a line integral.").decode(),
        "objective_description": "Understand CT projection.",
        "allow_local_teaching": True,
    })
    assert response.status_code == 200, response.text
    return response.json()


def chat(client, session, *, mode, question, count=0):
    return client.post("/api/chat", headers={"X-URPP-Local-Request": "1"}, json={
        "session_id": session["session_id"],
        "pack_sha256": session["pack_sha256"],
        "student_text": question,
        "expected_message_count": count,
        "mode": mode,
    })


def test_general_answer_is_explicit_source_free_persisted_and_resumable(tmp_path):
    client, course, general = make_client(tmp_path)
    session = upload(client)
    response = chat(client, session, mode="general", question="What is 1+1?")
    assert response.status_code == 200, response.text
    messages = response.json()["messages"]
    assert messages[0]["text"] == "What is 1+1?"
    assert messages[1]["text"].startswith("[GENERAL KNOWLEDGE — not from uploaded material]\n")
    assert messages[1]["text"].endswith("2")
    assert course.calls == []
    assert len(general.contexts) == 1
    assert general.contexts[0].current_student_message == "What is 1+1?"
    assert general.contexts[0].history == ()
    assert chat(client, session, mode="general", question="Again?", count=0).status_code == 409
    assert len(general.contexts) == 1
    reopened, _, _ = make_client(tmp_path)
    resumed = reopened.get(
        "/api/session/" + session["session_id"],
        params={"pack_sha256": session["pack_sha256"]},
    )
    assert resumed.status_code == 200
    assert resumed.json()["messages"] == messages


def test_course_default_still_uses_source_bound_existing_route(tmp_path):
    client, course, general = make_client(tmp_path)
    session = upload(client)
    response = client.post("/api/chat", headers={"X-URPP-Local-Request": "1"}, json={
        "session_id": session["session_id"], "pack_sha256": session["pack_sha256"],
        "student_text": "What is a projection?", "expected_message_count": 0,
    })
    assert response.status_code == 200, response.text
    assert len(course.calls) == 1 and general.contexts == []


def test_invalid_mode_or_pack_never_generates(tmp_path):
    client, course, general = make_client(tmp_path)
    session = upload(client)
    assert chat(client, session, mode="both", question="Hi").status_code == 400
    bad = {**session, "pack_sha256": "f" * 64}
    assert chat(client, bad, mode="general", question="Hi").status_code == 404
    assert course.calls == [] and general.contexts == []


def test_real_general_gateway_sends_no_material_or_sources():
    requests = []
    def transport(payload):
        requests.append(payload)
        return {"done": True, "done_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps({"content": "2"}),
        }}
    from app.services.course_knowledge.local_chat_context_v01 import LocalChatContextV01
    gateway = LocalGeneralKnowledgeGatewayV01(transport=transport)
    result = gateway.generate_general(context=LocalChatContextV01(
        course_id="local-upload-course", objective_id="uploaded-material",
        current_student_message="1 + 1?",
    ))
    assert result == "2"
    request = requests[0]
    assert request["format"]["required"] == ["content"]
    assert "sources" not in request["messages"][1]["content"]
    assert "Projection" not in request["messages"][1]["content"]
    assert "source_ids" not in request["messages"][1]["content"]


def test_general_gateway_rejects_unexpected_citations():
    from app.services.course_knowledge.local_chat_context_v01 import LocalChatContextV01
    gateway = LocalGeneralKnowledgeGatewayV01(transport=lambda request: {
        "done": True, "done_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps({"content": "2", "source_ids": ["fake"]}),
        },
    })
    with pytest.raises((ValueError, RuntimeError)):
        gateway.generate_general(context=LocalChatContextV01(
            course_id="c", objective_id="o", current_student_message="1+1",
        ))


def test_ui_mode_choice_and_safe_rendering(tmp_path):
    client, _, _ = make_client(tmp_path)
    assert 'id="answer-mode"' in client.get("/").text
    assert 'mode: el("answer-mode").value' in client.get("/assets/local-learning.js").text
    assert 'body.textContent = entry.text' in client.get("/assets/local-learning.js").text


def test_general_mode_does_not_pass_earlier_course_messages_to_injected_gateway(tmp_path):
    client, course, general = make_client(tmp_path)
    session = upload(client)
    first = chat(client, session, mode="course", question="Explain projection")
    assert first.status_code == 200, first.text
    second = chat(client, session, mode="general", question="What is 1+1?", count=2)
    assert second.status_code == 200, second.text
    assert len(course.calls) == 1
    assert len(general.contexts) == 1
    assert general.contexts[0].history == ()


def test_failed_general_generation_does_not_save_turn_or_leak_error(tmp_path):
    class FailedGeneral:
        def generate_general(self, *, context):
            raise RuntimeError("PRIVATE COURSE CONTENT")

    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "private", gateway_factory=CourseGateway,
        general_gateway_factory=FailedGeneral,
    )
    client = TestClient(create_local_learning_web_v01(
        workspace=workspace, allow_test_host=True,
    ))
    session = upload(client)
    response = chat(client, session, mode="general", question="What is 1+1?")
    assert response.status_code == 502
    assert "PRIVATE COURSE CONTENT" not in response.text
    resumed = client.get("/api/session/" + session["session_id"],
        params={"pack_sha256": session["pack_sha256"]})
    assert resumed.status_code == 200
    assert resumed.json()["messages"] == []

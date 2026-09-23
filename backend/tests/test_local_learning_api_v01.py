"""URPP 14D-2B: offline upload/chat/resume HTTP tests with a fake model."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.local_learning_api_v01 import create_local_learning_api_v01
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)


class FakeGateway:
    def __init__(self):
        self.calls = []

    def generate_structured(self, *, prompt_name, payload):
        self.calls.append((prompt_name, payload))
        return {
            "content": "Projection is a line integral, as described in the uploaded notes.",
            "source_ids": [payload["sources"][0]["source_id"]],
        }


def make_client(tmp_path, gateway=None):
    gateway = gateway or FakeGateway()
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "local-learning",
        gateway_factory=lambda: gateway,
    )
    app = create_local_learning_api_v01(workspace=workspace, allow_test_host=True)
    return TestClient(app), gateway


def post(client, path, payload, **options):
    headers = {"X-URPP-Local-Request": "1", **options.pop("headers", {})}
    return client.post(path, json=payload, headers=headers, **options)


def upload(client, *, headers=None, **overrides):
    payload = {
        "filename": "notes.md",
        "file_base64": base64.b64encode(
            b"# CT notes\nProjection is a line integral."
        ).decode("ascii"),
        "objective_description": "Explain CT projection from the notes.",
        "allow_local_teaching": True,
    }
    payload.update(overrides)
    return post(client, "/api/upload", payload, headers=headers or {})


def test_upload_chat_resume_reopen_and_continue(tmp_path):
    client, gateway = make_client(tmp_path)
    assert client.get("/api/health").json() == {"status": "local-demo-ready"}
    imported_response = upload(client)
    assert imported_response.status_code == 200, imported_response.text
    start = imported_response.json()
    assert start["source_count"] == 1
    assert start["message_count"] == 0
    first = post(client, "/api/chat", {
        "session_id": start["session_id"],
        "pack_sha256": start["pack_sha256"],
        "student_text": "What is projection?",
        "expected_message_count": 0,
    })
    assert first.status_code == 200, first.text
    assert first.json()["turn_count"] == 1
    assert len(gateway.calls) == 1

    second_client, second_gateway = make_client(tmp_path)
    resumed = second_client.get(
        "/api/session/" + start["session_id"],
        params={"pack_sha256": start["pack_sha256"]},
    )
    assert resumed.status_code == 200
    assert resumed.json()["messages"] == first.json()["messages"]
    second = post(second_client, "/api/chat", {
        "session_id": start["session_id"],
        "pack_sha256": start["pack_sha256"],
        "student_text": "Explain that again.",
        "expected_message_count": 2,
    })
    assert second.status_code == 200, second.text
    assert second.json()["turn_count"] == 2
    assert "What is projection?" in second_gateway.calls[0][1]["instructions"]
    assert "Projection is a line integral" in second_gateway.calls[0][1]["sources"][0]["content"]


def test_stale_request_does_not_call_model_again(tmp_path):
    client, gateway = make_client(tmp_path)
    start = upload(client).json()
    request = {
        "session_id": start["session_id"],
        "pack_sha256": start["pack_sha256"],
        "student_text": "First question",
        "expected_message_count": 0,
    }
    assert post(client, "/api/chat", request).status_code == 200
    assert post(client, "/api/chat", request).status_code == 409
    assert len(gateway.calls) == 1


def test_wrong_pack_digest_fails_without_model_call(tmp_path):
    client, gateway = make_client(tmp_path)
    start = upload(client).json()
    response = post(client, "/api/chat", {
        "session_id": start["session_id"],
        "pack_sha256": "f" * 64,
        "student_text": "What is CT?",
        "expected_message_count": 0,
    })
    assert response.status_code == 404
    assert gateway.calls == []


def test_no_teaching_permission_means_no_saved_upload(tmp_path):
    client, _ = make_client(tmp_path)
    assert upload(client, allow_local_teaching=False).status_code == 400
    assert list((tmp_path / "local-learning" / "uploads").iterdir()) == []


def test_malformed_upload_and_invalid_file_are_rejected(tmp_path):
    client, _ = make_client(tmp_path)
    assert upload(client, file_base64="invalid==").status_code == 400
    assert upload(client, filename="../notes.md").status_code == 400
    assert upload(client, filename="notes.exe").status_code == 400
    assert list((tmp_path / "local-learning" / "uploads").iterdir()) == []


def test_host_origin_and_custom_header_required(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 403
    assert upload(client, headers={"Origin": "https://evil.example"}).status_code == 403
    assert upload(client, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    response = client.post("/api/upload", json={"filename": "notes.md"})
    assert response.status_code == 403
    assert upload(client).status_code == 200


def test_body_size_and_content_type_rejected_before_import(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post(
        "/api/upload", data="file=notes", headers={"X-URPP-Local-Request": "1"},
    ).status_code == 415
    assert client.post(
        "/api/upload", content=b"{}", headers={
            "X-URPP-Local-Request": "1",
            "Content-Type": "application/json",
            "Content-Length": "11300001",
        },
    ).status_code == 413
    assert list((tmp_path / "local-learning" / "uploads").iterdir()) == []


def test_private_data_not_reflected_in_failed_request(tmp_path):
    client, _ = make_client(tmp_path)
    response = upload(client, filename="../secret_notes.md")
    assert response.status_code == 400
    assert "secret_notes" not in response.text


def test_testserver_is_explicitly_disabled_by_default(tmp_path):
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "private",
        gateway_factory=FakeGateway,
    )
    app = create_local_learning_api_v01(workspace=workspace)
    assert TestClient(app).get("/api/health").status_code == 403

"""14D-3B2A: insufficient-evidence output and citation contract.

All model responses are synthetic. No Ollama or manual Chat.
"""

import base64

from fastapi.testclient import TestClient

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
)
from app.local_learning_api_v01 import create_local_learning_api_v01
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)
from app.services.course_knowledge.structured_professor_adapter_v01 import (
    INSUFFICIENT_COURSE_MESSAGE_V01,
)


class EvidenceGateway:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def generate_structured(self, *, prompt_name, payload):
        self.calls += 1
        return self.response


def setup_session(tmp_path, response):
    gateway = EvidenceGateway(response)
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "workspace",
        gateway_factory=lambda: gateway,
    )
    client = TestClient(
        create_local_learning_api_v01(
            workspace=workspace,
            allow_test_host=True,
        )
    )
    upload = client.post(
        "/api/upload",
        headers={"X-URPP-Local-Request": "1"},
        json={
            "filename": "notes.md",
            "file_base64": base64.b64encode(
                b"# CT notes\nProjection is a line integral."
            ).decode(),
            "objective_description": "Explain CT projection.",
            "allow_local_teaching": True,
        },
    )
    assert upload.status_code == 200, upload.text
    return client, gateway, upload.json()


def ask(client, session):
    return client.post(
        "/api/chat",
        headers={"X-URPP-Local-Request": "1"},
        json={
            "session_id": session["session_id"],
            "pack_sha256": session["pack_sha256"],
            "student_text": "What is 1 + 1?",
            "expected_message_count": 0,
            "mode": "course",
        },
    )


def resume(client, session):
    return client.get(
        "/api/session/" + session["session_id"],
        params={"pack_sha256": session["pack_sha256"]},
    )


def test_insufficient_evidence_uses_no_citation_and_persists_fixed_message(
    tmp_path,
):
    client, gateway, session = setup_session(
        tmp_path,
        {
            "answer_status": "insufficient_evidence",
            "content": "UNSUPPORTED_MODEL_CLAIM",
            "source_ids": [],
        },
    )

    result = ask(client, session)

    assert result.status_code == 200, result.text
    assert gateway.calls == 1

    messages = result.json()["messages"]
    assert messages[1]["text"] == INSUFFICIENT_COURSE_MESSAGE_V01
    assert "UNSUPPORTED_MODEL_CLAIM" not in messages[1]["text"]

    recovered = resume(client, session)
    assert recovered.status_code == 200
    assert recovered.json()["messages"] == messages


def test_insufficient_evidence_with_fabricated_citation_fails_closed(
    tmp_path,
):
    client, gateway, session = setup_session(
        tmp_path,
        {
            "answer_status": "insufficient_evidence",
            "content": "Unsupported claim.",
            "source_ids": ["fabricated-source"],
        },
    )

    result = ask(client, session)

    assert result.status_code == 502
    assert gateway.calls == 1
    assert resume(client, session).json()["messages"] == []


def test_course_grounded_answer_cannot_have_empty_citations(tmp_path):
    client, gateway, session = setup_session(
        tmp_path,
        {
            "answer_status": "course_grounded",
            "content": "An unsupported claim.",
            "source_ids": [],
        },
    )

    assert ask(client, session).status_code == 502
    assert gateway.calls == 1
    assert resume(client, session).json()["messages"] == []


def test_invalid_answer_status_cannot_be_persisted(tmp_path):
    client, gateway, session = setup_session(
        tmp_path,
        {
            "answer_status": "general_knowledge",
            "content": "2",
            "source_ids": [],
        },
    )

    assert ask(client, session).status_code == 502
    assert gateway.calls == 1
    assert resume(client, session).json()["messages"] == []


def test_live_course_schema_exposes_insufficient_evidence_status():
    schema = LocalOllamaProfessorGatewayV01.RESPONSE_SCHEMA

    assert schema["properties"]["source_ids"]["minItems"] == 0
    assert schema["properties"]["answer_status"]["enum"] == [
        "course_grounded",
        "insufficient_evidence",
    ]

    assert "insufficient_evidence" in (
        LocalOllamaProfessorGatewayV01.SYSTEM_INSTRUCTIONS
    )


def test_insufficient_evidence_fixed_message_uses_real_newline():
    assert "[INSUFFICIENT COURSE EVIDENCE]\n" in INSUFFICIENT_COURSE_MESSAGE_V01
    assert "\\n" not in INSUFFICIENT_COURSE_MESSAGE_V01

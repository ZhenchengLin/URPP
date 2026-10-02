"""14D-2A: isolated local material → pinned pack → durable chat tests."""

from __future__ import annotations

from hashlib import sha256

import pytest

from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)


class FakeGateway:
    def __init__(self):
        self.requests = []

    def generate_structured(self, *, prompt_name, payload):
        self.requests.append((prompt_name, payload))
        return {
            "content": "Synthetic explanation from supplied notes.",
            "source_ids": [payload["sources"][0]["source_id"]],
        }


def make_workspace(tmp_path, gateway):
    return LocalLearningWorkspaceV01(
        data_root=tmp_path / "workspace",
        gateway_factory=lambda: gateway,
    )


def upload(workspace, **changes):
    options = dict(
        filename="ct_notes.md",
        content=b"# CT notes\nProjection is a line integral.\n",
        objective_description="Explain the uploaded CT projection notes.",
        allow_local_teaching=True,
    )
    options.update(changes)
    return workspace.import_document(**options)


def test_import_chat_reopen_and_continue(tmp_path):
    first_gateway = FakeGateway()
    workspace = make_workspace(tmp_path, first_gateway)
    imported = upload(workspace)
    start = imported.snapshot
    assert imported.source_count == 1
    assert start.messages == ()
    assert start.pack_sha256
    original = tmp_path / "workspace" / "uploads" / (
        sha256(b"# CT notes\nProjection is a line integral.\n").hexdigest() + ".bin"
    )
    assert original.read_bytes() == b"# CT notes\nProjection is a line integral.\n"

    first = workspace.explain(
        pack_sha256=start.pack_sha256, session_id=start.session_id,
        question="What is projection?", expected_message_count=0,
    )
    assert first.snapshot.turn_count == 1
    assert "What is projection?" in first_gateway.requests[0][1]["instructions"]

    new_gateway = FakeGateway()
    reopened = make_workspace(tmp_path, new_gateway)
    saved = reopened.resume(pack_sha256=start.pack_sha256, session_id=start.session_id)
    assert saved.messages == first.snapshot.messages
    second = reopened.explain(
        pack_sha256=start.pack_sha256, session_id=start.session_id,
        question="Explain the previous answer.", expected_message_count=2,
    )
    assert second.snapshot.turn_count == 2
    assert "What is projection?" in new_gateway.requests[0][1]["instructions"]
    assert "Synthetic explanation" in new_gateway.requests[0][1]["instructions"]
    assert "Projection is a line integral" in new_gateway.requests[0][1]["sources"][0]["content"]


def test_explicit_permission_prevents_storage(tmp_path):
    gateway = FakeGateway()
    workspace = make_workspace(tmp_path, gateway)
    with pytest.raises(PermissionError):
        upload(workspace, allow_local_teaching=False)
    assert list((tmp_path / "workspace" / "uploads").iterdir()) == []
    assert list((tmp_path / "workspace" / "packs").iterdir()) == []
    assert gateway.requests == []


def test_missing_or_wrong_pack_fails_closed_before_generation(tmp_path):
    gateway = FakeGateway()
    workspace = make_workspace(tmp_path, gateway)
    start = upload(workspace).snapshot
    with pytest.raises(LookupError):
        workspace.explain(
            pack_sha256="f" * 64, session_id=start.session_id,
            question="Hello", expected_message_count=0,
        )
    assert gateway.requests == []


def test_corrupted_saved_pack_fails_closed(tmp_path):
    gateway = FakeGateway()
    workspace = make_workspace(tmp_path, gateway)
    start = upload(workspace).snapshot
    pack_file = tmp_path / "workspace" / "packs" / (start.pack_sha256 + ".json")
    pack_file.write_bytes(b"{}")  # simulate external corruption, not a workspace operation
    with pytest.raises(ValueError):
        workspace.resume(pack_sha256=start.pack_sha256, session_id=start.session_id)
    assert gateway.requests == []


def test_stale_append_not_sent_to_model(tmp_path):
    gateway = FakeGateway()
    workspace = make_workspace(tmp_path, gateway)
    start = upload(workspace).snapshot
    workspace.explain(
        pack_sha256=start.pack_sha256, session_id=start.session_id,
        question="First", expected_message_count=0,
    )
    with pytest.raises(ValueError, match="advanced"):
        workspace.explain(
            pack_sha256=start.pack_sha256, session_id=start.session_id,
            question="Stale", expected_message_count=0,
        )
    assert len(gateway.requests) == 1


def test_file_name_path_rejected_without_persistence(tmp_path):
    workspace = make_workspace(tmp_path, FakeGateway())
    with pytest.raises(ValueError):
        upload(workspace, filename="../secret.md")
    assert list((tmp_path / "workspace" / "uploads").iterdir()) == []


def test_existing_upload_is_immutable(tmp_path):
    workspace = make_workspace(tmp_path, FakeGateway())
    imported = upload(workspace)
    again = upload(workspace)
    assert imported.snapshot.session_id != again.snapshot.session_id
    assert imported.snapshot.pack_sha256 == again.snapshot.pack_sha256
    assert len(list((tmp_path / "workspace" / "uploads").glob("*.bin"))) == 1


def test_pdf_uses_existing_parser_contract(tmp_path, monkeypatch):
    from app.services.course_knowledge import local_pdf_import_v01
    monkeypatch.setattr(
        local_pdf_import_v01, "_extract_pdf_pages_v01",
        lambda _: ("Projection uses a line integral.", " "),
    )
    workspace = make_workspace(tmp_path, FakeGateway())
    imported = upload(
        workspace, filename="ct.pdf", content=b"%PDF-1.7\nsynthetic",
    )
    assert imported.source_count == 1
    assert imported.pages_without_text == (2,)


def test_workspace_inside_repo_is_rejected(tmp_path):
    from app.services.course_knowledge.local_learning_workspace_v01 import REPO_ROOT
    with pytest.raises(ValueError, match="outside"):
        LocalLearningWorkspaceV01(
            data_root=REPO_ROOT / "backend" / "tests" / "bad-workspace",
            gateway_factory=FakeGateway,
        )

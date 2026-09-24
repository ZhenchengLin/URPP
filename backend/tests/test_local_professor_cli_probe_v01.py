"""Offline CLI diagnostic: real Workspace pipeline, synthetic model responses."""
import json
from hashlib import sha256

import pytest

from app.local_professor_cli_probe_v01 import probe
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01


@pytest.fixture
def saved_session(tmp_path):
    root = tmp_path / "original"
    workspace = LocalLearningWorkspaceV01(
        data_root=root,
        gateway_factory=lambda: type("NeverUsedGateway", (), {
            "generate_structured": lambda self, **kwargs: (_ for _ in ()).throw(
                AssertionError("No model call during import")
            ),
        })(),
    )
    imported = workspace.import_document(
        filename="notes.md",
        content=b"# CT\nI. INTRODUCTION\nForward projection integrates attenuation.\n",
        objective_description="Explain CT forward projection.",
        allow_local_teaching=True,
    )
    snapshot = imported.snapshot
    database = root / "chat.sqlite3"
    digest = sha256(database.read_bytes()).hexdigest()
    return root, workspace, snapshot, digest


def _run(root, snapshot, **kwargs):
    return probe(
        data_root=root,
        session_id=snapshot.session_id,
        pack_sha256=snapshot.pack_sha256,
        question="Explain projection in the Introduction.",
        **kwargs,
    )


def test_cli_input_only_does_not_call_model_or_write(saved_session, capsys):
    root, workspace, snapshot, digest = saved_session

    def forbidden_transport(request):
        raise AssertionError("Input-only mode must never invoke the model.")

    assert _run(root, snapshot, input_only=True, transport=forbidden_transport) == "INPUT_ONLY"
    output = capsys.readouterr().out
    assert "selected_excerpts=" in output
    assert "INPUT_ONLY" in output
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages == ()
    assert sha256((root / "chat.sqlite3").read_bytes()).hexdigest() == digest


def test_cli_valid_output_reaches_blocked_write_on_copy_only(saved_session, capsys):
    root, workspace, snapshot, digest = saved_session

    def valid_transport(request):
        item = json.loads(request["messages"][1]["content"])["sources"][0]
        output = {"content": "Projection integrates attenuation.",
                  "source_ids": [item["source_id"]], "answer_status": "course_grounded"}
        return {"done": True, "done_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(output),
        }}

    assert _run(root, snapshot, transport=valid_transport) == "VALIDATED_NOT_SAVED"
    assert "VALIDATION: passed" in capsys.readouterr().out
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages == ()
    assert sha256((root / "chat.sqlite3").read_bytes()).hexdigest() == digest


def test_cli_conflicting_status_and_citation_fails_closed(saved_session, capsys):
    root, workspace, snapshot, digest = saved_session

    def conflict_transport(request):
        item = json.loads(request["messages"][1]["content"])["sources"][0]
        output = {"content": "I cannot answer.", "source_ids": [item["source_id"]],
                  "answer_status": "insufficient_evidence"}
        return {"done": True, "done_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(output),
        }}

    assert _run(root, snapshot, transport=conflict_transport) == "REJECTED"
    log = capsys.readouterr().out
    assert "STATUS/CITATION CONFLICT" in log
    assert "ProfessorOutputContractErrorV01" in log
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages == ()
    assert sha256((root / "chat.sqlite3").read_bytes()).hexdigest() == digest

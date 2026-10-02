"""14D-4B4B: bounded local status/citation retry; all outputs synthetic."""
import pytest
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01
from app.services.course_knowledge.structured_professor_adapter_v01 import (
    INSUFFICIENT_COURSE_MESSAGE_V01, ProfessorOutputContractErrorV01,
)

class FakeGateway:
    def __init__(self, second, *, fabricate=False):
        self.second=second
        self.fabricate=fabricate
        self.calls=[]
    def generate_structured(self, *, prompt_name, payload):
        self.calls.append((prompt_name,payload))
        source_id=("fabricated-id" if self.fabricate else payload["sources"][0]["source_id"])
        if len(self.calls)==1:
            return {"content":"CONFLICTING_MODEL_TEXT", "source_ids":[source_id],
                    "answer_status":"insufficient_evidence"}
        if self.second == "valid":
            return {"content":"A line integral follows an X-ray path.",
                    "source_ids":[payload["sources"][0]["source_id"]],
                    "answer_status":"course_grounded"}
        if self.second == "insufficient":
            return {"content":"UNSUPPORTED_MODEL_TEXT", "source_ids":[],
                    "answer_status":"insufficient_evidence"}
        if self.second == "conflict":
            return {"content":"CONFLICTING_AGAIN", "source_ids":[source_id],
                    "answer_status":"insufficient_evidence"}
        raise AssertionError("Unexpected retry")

def prepare(tmp_path, second, *, fabricate=False):
    gateway=FakeGateway(second, fabricate=fabricate)
    workspace=LocalLearningWorkspaceV01(
        data_root=tmp_path/"private",gateway_factory=lambda:gateway,
    )
    imported=workspace.import_document(
        filename="test.md",content=b"# CT projection\nA line integral follows an X-ray path.",
        objective_description="Explain a line integral.",allow_local_teaching=True,
    )
    return workspace,gateway,imported.snapshot

def run(workspace,snapshot):
    return workspace.explain(
        pack_sha256=snapshot.pack_sha256,session_id=snapshot.session_id,
        question="Explain the line integral",expected_message_count=0,
    )

def test_conflict_gets_one_corrective_inference_then_commits_only_valid_answer(tmp_path):
    workspace,gateway,snapshot=prepare(tmp_path,"valid")
    result=run(workspace,snapshot)
    assert len(gateway.calls)==2
    assert "OUTPUT CONTRACT CORRECTION" in gateway.calls[1][1]["instructions"]
    assert gateway.calls[0][1]["sources"]==gateway.calls[1][1]["sources"]
    assert result.snapshot.turn_count==1
    assert result.snapshot.answer_statuses==("course_grounded",)
    assert "CONFLICTING_MODEL_TEXT" not in result.snapshot.messages[-1].text
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages==result.snapshot.messages

def test_conflict_then_valid_insufficient_discards_model_claims(tmp_path):
    workspace,gateway,snapshot=prepare(tmp_path,"insufficient")
    result=run(workspace,snapshot)
    assert len(gateway.calls)==2
    assert result.snapshot.answer_statuses==("insufficient_evidence",)
    assert result.snapshot.messages[-1].text==INSUFFICIENT_COURSE_MESSAGE_V01
    assert "UNSUPPORTED_MODEL_TEXT" not in result.snapshot.messages[-1].text

def test_repeated_conflict_rejected_without_saving_or_third_call(tmp_path):
    workspace,gateway,snapshot=prepare(tmp_path,"conflict")
    with pytest.raises(ProfessorOutputContractErrorV01,match="cannot cite a course source"):
        run(workspace,snapshot)
    assert len(gateway.calls)==2
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages==()

def test_fabricated_citation_not_retried_or_saved(tmp_path):
    workspace,gateway,snapshot=prepare(tmp_path,"valid",fabricate=True)
    with pytest.raises(ProfessorOutputContractErrorV01,match="cannot cite a course source"):
        run(workspace,snapshot)
    assert len(gateway.calls)==1
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                            session_id=snapshot.session_id).messages==()

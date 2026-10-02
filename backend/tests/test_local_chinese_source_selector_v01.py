"""14D-4B4C: bilingual selection, boundary-spanning section, no-source guard."""
from __future__ import annotations
import json
from urllib.parse import quote
from hashlib import sha256
import pytest

from app.services.course_knowledge.local_course_source_selector_v01 import (
    select_course_source_ids_v01,
)
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01
from app.services.course_knowledge.structured_professor_adapter_v01 import (
    INSUFFICIENT_COURSE_MESSAGE_V01, ProfessorOutputContractErrorV01,
)


def pdf_sources():
    pieces = [
        "I. INTRODUCTION\nProjection integrates attenuation; area and volume.",
        "II. FAN-BEAM PROJECTION\nLine integral and area look-up table.",
        "II. FAN-BEAM PROJECTION\n" + "x"*220 + "\nIII. CONE-BEAM PROJECTION\nIntersection volume begins.",
        "III. CONE-BEAM PROJECTION\nA. Exact Ray-Voxel Volume\n" + "Ray voxel volume intersection. "*30 + "(7)\n(9)",
        "B. Height Look-Up Table\nVoxel height hLUT (10) (11) (12) (13) (14).",
        "C. Height Approximation Methods\nRegression Method; Distance Method; height (15) (16).",
    ]
    return tuple({"source_id": f"pdf-{i}", "content": content,
                  "source_locator": f"local-pdf://notes.pdf?sha256=abc&pages={i}-{i}&excerpt={i}"}
                 for i, content in enumerate(pieces, 1))


@pytest.mark.parametrize("question,expected", [
    ("请解释论文第六页的高度近似公式。", ("pdf-6",)),
    ("请解释论文第6页的高度近似公式。", ("pdf-6",)),
    ("Explain page 6 height approximation", ("pdf-6",)),
    ("解释 Section III 的 intersection volume。", ("pdf-3", "pdf-4")),
    ("Explain Section III's intersection volume.", ("pdf-3", "pdf-4")),
    ("请解释公式 (7) 的几何意义", ("pdf-4",)),
    ("请解释不存在的量子纠缠实验。", ()),
    ("请解释第九页的公式。", ()),
])
def test_pdf_questions_select_exact_pages(question, expected):
    assert select_course_source_ids_v01(sources=pdf_sources(),current_question=question) == expected


def test_broad_formula_followup_gets_bounded_original_pages():
    history=(type("M", (), {"role":"student", "text":"和我说说这个paper最重要的数学公式是哪些？"})(),)
    result=select_course_source_ids_v01(sources=pdf_sources(),current_question="把 function 发给我。",history=history)
    assert result == ("pdf-4", "pdf-5")
    assert select_course_source_ids_v01(sources=pdf_sources(),
                                         current_question="整篇论文最重要的数学公式") == ("pdf-4", "pdf-5")


class FakeGateway:
    def __init__(self, *, fabricate=False):
        self.calls=[]
        self.fabricate=fabricate
    def generate_structured(self, *, prompt_name, payload):
        self.calls.append(payload)
        return {"content":"A supported synthetic explanation.",
                "source_ids": ["fabricated-id" if self.fabricate else payload["sources"][-1]["source_id"]],
                "answer_status": "course_grounded"}


def _workspace(tmp_path, *, fabricate=False):
    gateway=FakeGateway(fabricate=fabricate)
    workspace=LocalLearningWorkspaceV01(data_root=tmp_path / "private",gateway_factory=lambda:gateway)
    # Real material splitting preserves every original chunk without rewriting.
    p1="I. INTRODUCTION\n"+"a"*5900
    p2="II. FAN-BEAM PROJECTION\n"+"b"*5600+"\nIII. CONE-BEAM PROJECTION\n"
    p3="A. Exact Ray-Voxel Volume\n"+"c"*4000
    imported=workspace.import_document(filename="notes.md", content=(p1+p2+p3).encode(),
                 objective_description="Explain CT",allow_local_teaching=True)
    return workspace,gateway,imported.snapshot


def test_missing_chinese_subject_fails_closed_without_ollama_or_fake_citation(tmp_path):
    workspace,gateway,snapshot=_workspace(tmp_path)
    result=workspace.explain(pack_sha256=snapshot.pack_sha256,session_id=snapshot.session_id,
                             question="请解释不存在的量子纠缠实验。", expected_message_count=0)
    assert gateway.calls==[]
    assert result.snapshot.answer_statuses == ("insufficient_evidence",)
    assert result.snapshot.messages[-1].text==INSUFFICIENT_COURSE_MESSAGE_V01


def test_selected_multi_source_still_rejects_fabricated_citation_without_writes(tmp_path):
    workspace,gateway,snapshot=_workspace(tmp_path,fabricate=True)
    with pytest.raises(ProfessorOutputContractErrorV01, match="outside Course Knowledge"):
        workspace.explain(pack_sha256=snapshot.pack_sha256,session_id=snapshot.session_id,
                          question="解释 Section III 的 intersection volume。", expected_message_count=0)
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,session_id=snapshot.session_id).messages==()

"""14D-4A1: bounded current-question excerpt selection; no real inference."""
import pytest

from app.services.course_knowledge.local_course_source_selector_v01 import (
    select_course_source_ids_v01,
)
from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)
from app.services.course_knowledge.structured_professor_adapter_v01 import (
    ProfessorOutputContractErrorV01,
)
from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
)


def fixtures():
    return (
        {"source_id": "intro", "content": "I. INTRODUCTION\nProjection is a line integral. CUDA is mentioned."},
        {"source_id": "cone", "content": "III. CONE-BEAM PROJECTION\nThe source-bin pyramid intersects a voxel."},
        {"source_id": "cuda", "content": "IV. GPU IMPLEMENTATION USING CUDA\nCUDA kernels operate on voxels."},
    )


@pytest.mark.parametrize("question,expected", [
    ("Explain the Introduction", "intro"),
    ("Teach Section III", "cone"),
    ("What is the cone-beam source-bin pyramid?", "cone"),
    ("Explain the CUDA implementation", "cuda"),
    ("Teach me the first concept", "intro"),
])
def test_question_selects_complete_original_excerpt(question, expected):
    source_items = fixtures()
    chosen = select_course_source_ids_v01(sources=source_items, current_question=question)
    assert chosen == (expected,)
    assert len(source_items) == 3
    assert source_items[2]["content"].startswith("IV.")


def test_local_gateway_explicit_context_budget():
    requests = []
    import json
    response = {"done": True, "done_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps({
            "content": "Synthetic answer.", "source_ids": ["intro"],
            "answer_status": "course_grounded",
        }),
    }}
    gateway = LocalOllamaProfessorGatewayV01(
        transport=lambda payload: (requests.append(payload), response)[1]
    )
    payload = {
        "contract_version": "structured-professor-v0.1",
        "instructions": "Synthetic instruction", "objective": {},
        "teaching_action": "conceptual_review",
        "student_request_kind": "request_explanation",
        "sources": [{"source_id": "intro", "source_revision": "v1",
                     "source_locator": "synthetic:1", "content": "Introduction"}],
    }
    gateway.generate_structured(prompt_name=gateway.PROMPT_NAME, payload=payload)
    assert requests[0]["options"]["num_ctx"] == 8192
    assert requests[0]["options"]["num_predict"] == 1024


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.force_source = None

    def generate_structured(self, *, prompt_name, payload):
        self.calls.append(payload)
        return {
            "content": "Synthetic answer.",
            "source_ids": [self.force_source or payload["sources"][0]["source_id"]],
            "answer_status": "course_grounded",
        }


def setup_workspace(tmp_path):
    gateway = FakeGateway()
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "private", gateway_factory=lambda: gateway,
    )
    # Exactly two 6000-character blocks. The second one has the CUDA heading.
    start = "I. INTRODUCTION\nProjection is a line integral.\n"
    material = start + ("x" * (6000 - len(start))) + (
        "IV. GPU IMPLEMENTATION USING CUDA\nCUDA kernels use voxel blocks."
    )
    imported = workspace.import_document(
        filename="synthetic.md", content=material.encode(),
        objective_description="Synthetic explanation of CT projection.",
        allow_local_teaching=True,
    )
    return workspace, gateway, imported.snapshot, material


def test_real_local_chat_service_sends_only_relevant_authorized_source(tmp_path):
    workspace, gateway, snapshot, original = setup_workspace(tmp_path)
    result = workspace.explain(
        pack_sha256=snapshot.pack_sha256, session_id=snapshot.session_id,
        question="Explain the CUDA GPU implementation", expected_message_count=0,
    )
    assert len(gateway.calls) == 1
    selected = gateway.calls[0]["sources"]
    assert len(selected) == 1
    assert selected[0]["content"].startswith("IV. GPU IMPLEMENTATION USING CUDA")
    assert result.snapshot.answer_statuses == ("course_grounded",)
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                             session_id=snapshot.session_id).turn_count == 1


def test_citing_authorized_but_unselected_source_fails_and_saves_nothing(tmp_path):
    workspace, gateway, snapshot, original = setup_workspace(tmp_path)
    pack = workspace._load_pack(snapshot.pack_sha256)
    gateway.force_source = pack.sources[0].source_id
    with pytest.raises(ProfessorOutputContractErrorV01, match="outside Course Knowledge"):
        workspace.explain(
            pack_sha256=snapshot.pack_sha256, session_id=snapshot.session_id,
            question="Explain the CUDA GPU implementation", expected_message_count=0,
        )
    assert len(gateway.calls) == 1
    assert len(gateway.calls[0]["sources"]) == 1
    assert workspace.resume(pack_sha256=snapshot.pack_sha256,
                             session_id=snapshot.session_id).messages == ()

def _cross_page_equation_sources():
    return (
        {
            "source_id": "page5",
            "source_locator": (
                "local-pdf://synthetic.pdf?"
                "sha256=abc&pages=5-5&excerpt=5"
            ),
            "content": (
                "C. Height Approximation Methods\n"
                "1) Regression Method :\n"
                "Discussion continues on the next page."
            ),
        },
        {
            "source_id": "page6",
            "source_locator": (
                "local-pdf://synthetic.pdf?"
                "sha256=abc&pages=6-6&excerpt=6"
            ),
            "content": (
                "height = piece-wise approximation. (15)\n"
                "2) Distance Method :\n"
                "h_eff = interval overlap. (16)"
            ),
        },
    )

def test_eq15_method_attribution_adds_prior_page_context():
    chosen = select_course_source_ids_v01(
        sources=_cross_page_equation_sources(),
        current_question=(
            "Which approximation method does Equation (15) belong to?"
        ),
    )

    assert chosen == ("page6", "page5")

def test_eq15_formula_request_does_not_add_prior_method_context():
    chosen = select_course_source_ids_v01(
        sources=_cross_page_equation_sources(),
        current_question="Write Equation (15).",
    )

    assert chosen == ("page6",)

def test_eq16_method_attribution_uses_heading_on_equation_page():
    chosen = select_course_source_ids_v01(
        sources=_cross_page_equation_sources(),
        current_question=(
            "Which approximation method does Equation (16) belong to?"
        ),
    )

    assert chosen == ("page6",)

def test_method_context_does_not_cross_nonadjacent_pages():
    page5, page6 = _cross_page_equation_sources()

    page7 = {
        **page6,
        "source_locator": (
            "local-pdf://synthetic.pdf?"
            "sha256=abc&pages=7-7&excerpt=7"
        ),
    }

    chosen = select_course_source_ids_v01(
        sources=(page5, page7),
        current_question=(
            "Which method does Equation (15) belong to?"
        ),
    )

    assert chosen == ("page6",)

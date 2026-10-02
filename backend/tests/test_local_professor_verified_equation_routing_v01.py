import importlib.util
import json
from dataclasses import MISSING
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.local_professor_benchmark_adapter_v01 import (
    run_local_professor_benchmark_case_v01,
)
from app.services.course_knowledge.local_professor_chat_service_v01 import (
    LocalProfessorChatTurnV01,
)
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    SourceGroundedBenchmarkCaseV01,
)
from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
)
from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

def _template_pack():
    path = Path(__file__).with_name(
        "test_local_professor_benchmark_adapter_v01.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_adapter_fixture",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    candidate = module.pack()
    assert isinstance(candidate, CoursePackV01)
    return candidate

def _pack():
    data = _template_pack().model_dump(mode="python")
    sources_key = next(
        k for k, v in data.items()
        if isinstance(v, (list, tuple)) and v
        and isinstance(v[0], dict)
        and {"source_id", "content"} <= set(v[0])
    )
    objectives_key = next(
        k for k, v in data.items()
        if isinstance(v, (list, tuple)) and v
        and isinstance(v[0], dict)
        and {"objective_id", "source_refs"} <= set(v[0])
    )
    source = dict(data[sources_key][0])
    source["content"] = "Synthetic equation (7)."
    source["content_sha256"] = sha256(source["content"].encode()).hexdigest()
    data[sources_key] = (source,)
    objective = dict(data[objectives_key][0])
    ref = dict(objective["source_refs"][0])
    ref.update(
        source_id=source["source_id"],
        source_revision=source["source_revision"],
        content_sha256=source["content_sha256"],
    )
    if "source_locator" in ref:
        ref["source_locator"] = source["source_locator"]
    objective["source_refs"] = (ref,)
    data[objectives_key] = (objective,)
    return CoursePackV01.model_validate(data)

def _case(question, case_id):
    path = Path(__file__).with_name(
        "test_local_professor_benchmark_adapter_v01.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_adapter_case_fixture",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    candidate = module.positive_case()
    assert isinstance(
        candidate,
        SourceGroundedBenchmarkCaseV01,
    )
    return candidate.model_copy(
        update={
            "case_id": case_id,
            "question": question,
        }
    )

def _registry(pack, label="7"):
    objective = pack.objectives[0]
    source_id = objective.source_refs[0].source_id
    source = next(s for s in pack.sources if s.source_id == source_id)
    return VerifiedEquationRegistryV01(
        records=(
            VerifiedEquationRecordV01(
                record_id=f"synthetic-record-{label}",
                record_revision="synthetic-record-v01",
                equation_label=label,
                source_ref=source.reference(),
                equation_locator=f"synthetic-equation-{label}",
                normalized_latex=rf"verified_{{{label}}} = exact",
                review_status="source_checked",
                reviewer_id="synthetic-reviewer",
                reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ),
    )

def _transport(calls):
    def transport(payload):
        calls.append(payload)
        return {
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "content": "Insufficient evidence.",
                    "source_ids": [],
                    "answer_status": "insufficient_evidence",
                }),
            }
        }
    return transport

def _run(pack, case, registry, calls, suffix):
    scoped_ref = pack.objectives[0].source_refs[0]
    scoped_required_evidence = tuple(
        item.model_copy(update={"source_ref": scoped_ref})
        for item in case.required_evidence
    )
    scoped_case = case.model_copy(
        update={
            "source_scope_refs": (
                pack.objectives[0].source_refs
            ),
            "required_evidence": scoped_required_evidence,
        }
    )
    return run_local_professor_benchmark_case_v01(
        case=scoped_case,
        pack=pack,
        objective_id=pack.objectives[0].objective_id,
        candidate_version="synthetic-14f",
        run_id=f"synthetic-{suffix}",
        run_started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        transport=_transport(calls),
        verified_equation_registry=registry,
    )

def test_deterministic_transcription_makes_zero_transport_calls():
    pack = _pack()
    calls = []
    trace = _run(
        pack,
        _case("Please copy Eq. (7).", "synthetic-copy-7"),
        _registry(pack),
        calls,
        "copy",
    )
    assert calls == []
    assert trace.system_answer_status == "course_grounded"
    assert trace.final_status == "answered"
    assert r"verified_{7} = exact" in trace.final_answer

def test_missing_verified_label_abstains_without_transport():
    pack = _pack()
    calls = []
    trace = _run(
        pack,
        _case("Please copy Eq. (7).", "synthetic-missing-7"),
        _registry(pack, label="10"),
        calls,
        "missing",
    )
    assert calls == []
    assert trace.system_answer_status == "insufficient_evidence"
    assert trace.final_status == "abstained"
    assert r"verified_{7}" not in trace.final_answer

def test_explain_request_keeps_existing_transport_path():
    pack = _pack()
    case = _case("Please explain Eq. (7).", "synthetic-explain-7")
    with_registry_calls = []
    without_registry_calls = []
    with_registry = _run(
        pack, case, _registry(pack), with_registry_calls, "explain-with"
    )
    without_registry = _run(
        pack, case, None, without_registry_calls, "explain-without"
    )
    assert with_registry_calls
    assert without_registry_calls
    assert with_registry.system_answer_status == without_registry.system_answer_status
    assert with_registry.final_status == without_registry.final_status

def test_turn_provenance_field_is_strictly_optional():
    field = LocalProfessorChatTurnV01.__dataclass_fields__[
        "verified_equation_provenance"
    ]
    assert field.default is None
    assert field.default_factory is MISSING

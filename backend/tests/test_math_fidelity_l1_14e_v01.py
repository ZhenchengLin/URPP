from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)
from app.services.course_knowledge.math_fidelity_l1_14e_v01 import (
    check_equation_markers_14e_v01,
    evaluate_l1_run_14e_v01,
)
from app.services.course_knowledge.math_fidelity_runner_14e_v01 import (
    run_math_fidelity_14e_v01,
)
from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    BenchmarkConversationTurnV01,
    BenchmarkEvidenceExpectationV01,
    BenchmarkGoldV01,
    SourceGroundedBenchmarkCaseV01,
)

RUN_AT = datetime(
    2026,
    10,
    1,
    8,
    0,
    tzinfo=timezone.utc,
)

def course_source(
    source_id: str,
    *,
    page: int,
    content: str,
) -> CourseSourceV01:
    return CourseSourceV01(
        course_id="course-1",
        source_id=source_id,
        source_revision="synthetic-revision-1",
        source_locator=(
            "local-pdf://synthetic.pdf"
            "?sha256="
            + ("f" * 64)
            + f"&pages={page}-{page}"
            + f"&excerpt={page}"
        ),
        content=content,
        content_sha256=sha256(
            content.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

def synthetic_pack() -> CoursePackV01:
    page6 = course_source(
        "pdf-6",
        page=6,
        content=(
            "Synthetic source about a regression "
            "method and a height expression."
        ),
    )
    page7 = course_source(
        "pdf-7",
        page=7,
        content=(
            "Synthetic source about another "
            "unrelated method."
        ),
    )

    objective = CourseLearningObjectiveV01(
        course_id="course-1",
        objective_id="objective-1",
        description="Synthetic objective.",
        review_status="approved",
        source_refs=(
            page6.reference(),
            page7.reference(),
        ),
    )

    return CoursePackV01(
        course_id="course-1",
        pack_id="synthetic-pack",
        pack_revision="synthetic-pack-v1",
        objectives=(objective,),
        sources=(
            page6,
            page7,
        ),
    )

def write_pack(
    tmp_path: Path,
) -> tuple[Path, str, CoursePackV01]:
    material = synthetic_pack()
    path = tmp_path / "pack.json"
    path.write_text(
        material.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return (
        path,
        sha256(path.read_bytes()).hexdigest(),
        material,
    )

def synthetic_case(
    material: CoursePackV01,
    *,
    case_id: str = "case-a",
    prior: bool = False,
) -> SourceGroundedBenchmarkCaseV01:
    page6 = next(
        source
        for source in material.sources
        if source.source_id == "pdf-6"
    )

    prior_turns = (
        (
            BenchmarkConversationTurnV01(
                role="student",
                text="Synthetic prior question.",
            ),
        )
        if prior
        else ()
    )

    return SourceGroundedBenchmarkCaseV01(
        case_id=case_id,
        benchmark_version="v0.1",
        split="development",
        language="en",
        question_type="conceptual_explanation",
        question="Explain the synthetic method.",
        prior_turns=prior_turns,
        source_scope_refs=(
            page6.reference(),
        ),
        required_evidence=(
            BenchmarkEvidenceExpectationV01(
                source_ref=page6.reference(),
                evidence_locator="Synthetic page 6.",
                evidence_kind="method",
                rationale="Synthetic evidence.",
            ),
        ),
        gold=BenchmarkGoldV01(
            required_facts=(
                "The synthetic method is identified.",
            ),
            equations=(),
            prohibited_errors=(
                "Do not cite an unrelated source.",
            ),
            acceptable_variants=(),
        ),
        expected_outcome="answer",
        evaluation_categories=(
            "source_selection",
        ),
        notes="Synthetic only.",
    )

class FakeTransport:
    def __init__(
        self,
        *,
        source_ids=None,
        answer_status="course_grounded",
        content="Synthetic grounded answer.",
    ):
        self.source_ids = (
            ["pdf-6"]
            if source_ids is None
            else list(source_ids)
        )
        self.answer_status = answer_status
        self.content = content

    def __call__(self, request):
        raw = json.dumps(
            {
                "content": self.content,
                "source_ids": self.source_ids,
                "answer_status": self.answer_status,
            },
            ensure_ascii=False,
        )
        return {
            "done": True,
            "done_reason": "stop",
            "message": {
                "role": "assistant",
                "content": raw,
            },
        }

def build_run(
    tmp_path: Path,
    *,
    cases,
    transport,
    run_id="synthetic-run",
) -> Path:
    pack_path, digest, _ = write_pack(
        tmp_path
    )
    return run_math_fidelity_14e_v01(
        pack_path=pack_path,
        output_root=tmp_path / "out",
        run_id=run_id,
        run_started_at=RUN_AT,
        candidate_version="synthetic-candidate-v1",
        transport=transport,
        cases=cases,
        expected_pack_sha256=digest,
        objective_id="objective-1",
    )

def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )

def checks_by_id(report, case_index=0):
    return {
        item["check_id"]: item
        for item in report["cases"][
            case_index
        ]["checks"]
    }

def test_passing_trace_has_deterministic_pass_checks(
    tmp_path: Path,
):
    material = synthetic_pack()
    case = synthetic_case(material)
    run_dir = build_run(
        tmp_path,
        cases=(case,),
        transport=FakeTransport(),
    )

    report_path = evaluate_l1_run_14e_v01(
        run_dir=run_dir,
        cases=(case,),
    )
    checks = checks_by_id(
        read_json(report_path)
    )

    assert checks["L1-RECORD"]["status"] == "PASS"
    assert checks["L1-RUN"]["status"] == "PASS"
    assert (
        checks["L1-TRACE-VALID"]["status"]
        == "PASS"
    )
    assert (
        checks["L1-FINAL-STATUS"]["status"]
        == "PASS"
    )
    assert checks["L1-CONTRACT"]["status"] == "PASS"
    assert (
        checks["L1-NO-SESSION-WRITE"]["status"]
        == "PASS"
    )
    assert (
        checks["L1-CITATION-SCOPE"]["status"]
        == "PASS"
    )
    assert checks["L1-OUTCOME"]["status"] == "PASS"

def test_error_trace_is_reported_as_failure(
    tmp_path: Path,
):
    material = synthetic_pack()
    case = synthetic_case(material)

    def failing_transport(request):
        raise RuntimeError("synthetic offline")

    run_dir = build_run(
        tmp_path,
        cases=(case,),
        transport=failing_transport,
    )

    report = read_json(
        evaluate_l1_run_14e_v01(
            run_dir=run_dir,
            cases=(case,),
        )
    )
    checks = checks_by_id(report)

    assert checks["L1-RECORD"]["status"] == "PASS"
    assert (
        checks["L1-RUN"]["status"]
        in {"PASS", "FAIL"}
    )

    if checks["L1-RUN"]["status"] == "PASS":
        assert (
            checks["L1-FINAL-STATUS"]["status"]
            == "FAIL"
        )

def test_out_of_scope_raw_citation_fails(
    tmp_path: Path,
):
    material = synthetic_pack()
    case = synthetic_case(material)

    run_dir = build_run(
        tmp_path,
        cases=(case,),
        transport=FakeTransport(
            source_ids=["pdf-7"],
        ),
    )

    report = read_json(
        evaluate_l1_run_14e_v01(
            run_dir=run_dir,
            cases=(case,),
        )
    )
    checks = checks_by_id(report)

    if checks["L1-RUN"]["status"] == "PASS":
        assert (
            checks["L1-CITATION-SCOPE"]["status"]
            == "FAIL"
        )

def test_unsupported_prior_turn_case_is_not_dropped(
    tmp_path: Path,
):
    material = synthetic_pack()
    case = synthetic_case(
        material,
        case_id="case-follow",
        prior=True,
    )

    run_dir = build_run(
        tmp_path,
        cases=(case,),
        transport=FakeTransport(),
    )

    report = read_json(
        evaluate_l1_run_14e_v01(
            run_dir=run_dir,
            cases=(case,),
        )
    )

    assert len(report["cases"]) == 1
    assert (
        report["cases"][0]["case_id"]
        == "case-follow"
    )

    checks = checks_by_id(report)

    assert (
        checks["L1-RUN"]["status"]
        == "NOT_RUN"
    )
    assert (
        checks["L1-RUN"]["detail"]
        == "current chain does not support prior_turns"
    )
    assert (
        checks["L1-TRACE-VALID"]["status"]
        == "NOT_RUN"
    )

@pytest.mark.parametrize(
    ("label", "answer"),
    [
        (
            "7",
            r"\sum d_n r^2 \gamma_i \gamma_j \sin(\theta)",
        ),
        (
            "10",
            r"\frac{\Delta x}{\Delta y}",
        ),
        (
            "15",
            r"\begin{cases}\Delta z/2-D_{pl}&x\\0&otherwise\end{cases}",
        ),
        (
            "16",
            r"\begin{cases}\min(\max(z^{+},t_c^{+}),1)\\0&otherwise\end{cases}",
        ),
    ],
)
def test_equation_marker_pass_cases(
    label,
    answer,
):
    passed, missing = (
        check_equation_markers_14e_v01(
            equation_label=label,
            final_answer=answer,
        )
    )
    assert passed is True
    assert missing == ()

@pytest.mark.parametrize(
    ("label", "answer", "missing_marker"),
    [
        (
            "7",
            r"d_n^2 \gamma_i \sin(x)",
            "sum sign",
        ),
        (
            "10",
            r"\Delta x + q",
            "Delta y",
        ),
        (
            "15",
            r"\Delta z/2-D_{pl}",
            "zero branch",
        ),
        (
            "16",
            r"\min(z^{+},t_c^{+})",
            "max",
        ),
    ],
)
def test_equation_marker_fail_cases(
    label,
    answer,
    missing_marker,
):
    passed, missing = (
        check_equation_markers_14e_v01(
            equation_label=label,
            final_answer=answer,
        )
    )
    assert passed is False
    assert missing_marker in missing

def test_incomplete_manifest_is_refused(
    tmp_path: Path,
):
    run_dir = tmp_path / "run"
    (run_dir / "cases").mkdir(
        parents=True
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "complete": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        evaluate_l1_run_14e_v01(
            run_dir=run_dir,
            cases=(),
        )

    assert not (
        run_dir / "l1"
    ).exists()

def test_existing_report_is_refused(
    tmp_path: Path,
):
    run_dir = tmp_path / "run"
    report = (
        run_dir
        / "l1"
        / "l1_report.json"
    )
    report.parent.mkdir(
        parents=True
    )
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "complete": True,
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        "sentinel",
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError):
        evaluate_l1_run_14e_v01(
            run_dir=run_dir,
            cases=(),
        )

    assert report.read_text(
        encoding="utf-8"
    ) == "sentinel"

def test_evaluation_does_not_modify_manifest_or_case_records(
    tmp_path: Path,
):
    material = synthetic_pack()
    case = synthetic_case(material)

    run_dir = build_run(
        tmp_path,
        cases=(case,),
        transport=FakeTransport(),
    )

    manifest = run_dir / "manifest.json"
    record = (
        run_dir
        / "cases"
        / "01-case-a.json"
    )

    before_manifest = manifest.read_bytes()
    before_record = record.read_bytes()

    report = evaluate_l1_run_14e_v01(
        run_dir=run_dir,
        cases=(case,),
    )

    assert report.is_file()
    assert manifest.read_bytes() == before_manifest
    assert record.read_bytes() == before_record

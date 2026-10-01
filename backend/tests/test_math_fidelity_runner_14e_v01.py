from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)
from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    PINNED_PACK_SHA256_14E_V01,
    build_math_fidelity_cases_14e_v01,
)
from app.services.course_knowledge.math_fidelity_runner_14e_v01 import (
    _REPO_ROOT,
    build_case_scoped_pack_14e_v01,
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
CANDIDATE_VERSION = "synthetic-candidate-v0.1"

def course_source(
    source_id: str,
    *,
    page: int,
    content: str,
):
    return CourseSourceV01(
        course_id="course-1",
        source_id=source_id,
        source_revision="paper-revision-1",
        source_locator=(
            "local-pdf://paper.pdf"
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
        use_permission=(
            "approved_for_local_teaching"
        ),
        review_status="approved",
    )

def synthetic_pack() -> CoursePackV01:
    page4 = course_source(
        "pdf-4",
        page=4,
        content=(
            "Synthetic page four text about "
            "a projection geometry example."
        ),
    )
    page5 = course_source(
        "pdf-5",
        page=5,
        content=(
            "Synthetic page five text about "
            "a height lookup table."
        ),
    )
    page6 = course_source(
        "pdf-6",
        page=6,
        content=(
            "Synthetic page six. "
            "Regression Method appears with "
            "Equation (15). Distance Method "
            "appears with Equation (16)."
        ),
    )

    objective = CourseLearningObjectiveV01(
        course_id="course-1",
        objective_id="objective-1",
        description=(
            "Understand synthetic projection "
            "method examples."
        ),
        review_status="approved",
        source_refs=(
            page4.reference(),
            page5.reference(),
            page6.reference(),
        ),
    )

    return CoursePackV01(
        course_id="course-1",
        pack_id="synthetic-pack",
        pack_revision="synthetic-pack-v1",
        objectives=(objective,),
        sources=(
            page4,
            page5,
            page6,
        ),
    )

def write_pack(
    tmp_path: Path,
) -> tuple[Path, str, CoursePackV01]:
    material = synthetic_pack()
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        material.model_dump_json(indent=2),
        encoding="utf-8",
    )
    digest = sha256(
        pack_path.read_bytes()
    ).hexdigest()
    return pack_path, digest, material

def case_a(
    material: CoursePackV01,
) -> SourceGroundedBenchmarkCaseV01:
    page6 = next(
        source
        for source in material.sources
        if source.source_id == "pdf-6"
    )

    return SourceGroundedBenchmarkCaseV01(
        case_id="case-a",
        benchmark_version="v0.1",
        split="development",
        language="zh",
        question_type="equation_transcription",
        question="请写出式 (15) 的完整公式。",
        source_scope_refs=(
            page6.reference(),
        ),
        required_evidence=(
            BenchmarkEvidenceExpectationV01(
                source_ref=page6.reference(),
                evidence_locator=(
                    "Synthetic page 6, "
                    "Equation (15)"
                ),
                evidence_kind="equation",
                rationale=(
                    "Synthetic evidence region "
                    "supports Equation (15)."
                ),
            ),
        ),
        gold=BenchmarkGoldV01(
            required_facts=(
                "Equation (15) belongs to "
                "Regression Method.",
            ),
            prohibited_errors=(
                "Do not attribute Equation (15) "
                "to another method.",
            ),
        ),
        expected_outcome="answer",
        evaluation_categories=(
            "source_selection",
            "formula_transcription",
        ),
        notes="Synthetic benchmark metadata.",
    )

def case_b(
    material: CoursePackV01,
) -> SourceGroundedBenchmarkCaseV01:
    base = case_a(material)
    return base.model_copy(
        update={
            "case_id": "case-b",
            "prior_turns": (
                BenchmarkConversationTurnV01(
                    role="student",
                    text=(
                        "PRIOR-TURN-SENTINEL: "
                        "论文有哪些数学公式？"
                    ),
                ),
            ),
        }
    )

class FakeTransport:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        raw = json.dumps(
            {
                "content": (
                    "式 (15) 是 Regression Method "
                    "中的高度近似公式。"
                ),
                "source_ids": ["pdf-6"],
                "answer_status": "course_grounded",
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

def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )

def test_case_scoped_pack_contains_exact_scope_and_validates():
    material = synthetic_pack()
    case = case_a(material)

    scoped = build_case_scoped_pack_14e_v01(
        pack=material,
        case=case,
        objective_id="objective-1",
    )

    assert len(scoped.objectives) == 1
    assert (
        scoped.objectives[0].source_refs
        == case.source_scope_refs
    )
    assert [
        source.source_id
        for source in scoped.sources
    ] == ["pdf-6"]

    validated = CoursePackV01.model_validate(
        scoped.model_dump(mode="python")
    )
    assert validated == scoped

def test_case_scoped_pack_fails_closed_on_reference_mismatch():
    material = synthetic_pack()
    base = case_a(material)

    bad_ref = base.source_scope_refs[0].model_copy(
        update={
            "content_sha256": "0" * 64,
        }
    )
    bad_case = base.model_copy(
        update={
            "source_scope_refs": (
                bad_ref,
            ),
        }
    )

    with pytest.raises(ValueError):
        build_case_scoped_pack_14e_v01(
            pack=material,
            case=bad_case,
            objective_id="objective-1",
        )

def test_run_preserves_trace_and_prior_turn_case(
    tmp_path: Path,
):
    pack_path, digest, material = write_pack(
        tmp_path
    )
    transport = FakeTransport()

    run_dir = run_math_fidelity_14e_v01(
        pack_path=pack_path,
        output_root=tmp_path / "out",
        run_id="run-two-cases",
        run_started_at=RUN_AT,
        candidate_version=CANDIDATE_VERSION,
        transport=transport,
        cases=(
            case_a(material),
            case_b(material),
        ),
        expected_pack_sha256=digest,
        objective_id="objective-1",
    )

    manifest_path = run_dir / "manifest.json"
    cases_dir = run_dir / "cases"

    assert manifest_path.is_file()

    case_files = sorted(
        cases_dir.glob("*.json")
    )
    assert [
        item.name
        for item in case_files
    ] == [
        "01-case-a.json",
        "02-case-b.json",
    ]

    first = read_json(case_files[0])
    second = read_json(case_files[1])
    manifest = read_json(manifest_path)

    assert first["record_kind"] == "trace"
    assert first["trace"] is not None
    assert (
        first["trace"]["raw_model_output"]
        is not None
    )
    assert (
        first["trace"]["session_write_performed"]
        is False
    )

    assert second["case_id"] == "case-b"
    assert second["record_kind"] in {
        "unsupported_by_current_chain",
        "trace",
    }

    if second["record_kind"] == "trace":
        assert (
            second["trace"]["final_status"]
            == "error"
        )

    prior_text = (
        "PRIOR-TURN-SENTINEL: "
        "论文有哪些数学公式？"
    )
    assert all(
        prior_text not in repr(request)
        for request in transport.requests
    )

    assert manifest["complete"] is True
    assert manifest["l1_status"] == "not_evaluated"
    assert manifest["l2_status"] == "not_evaluated"

def test_pack_sha_mismatch_creates_no_run_tree(
    tmp_path: Path,
):
    pack_path, _, material = write_pack(
        tmp_path
    )
    out = tmp_path / "out"

    with pytest.raises(ValueError):
        run_math_fidelity_14e_v01(
            pack_path=pack_path,
            output_root=out,
            run_id="bad-sha",
            run_started_at=RUN_AT,
            candidate_version=CANDIDATE_VERSION,
            transport=FakeTransport(),
            cases=(case_a(material),),
            expected_pack_sha256="0" * 64,
            objective_id="objective-1",
        )

    assert not (out / "14E").exists()

def test_existing_run_dir_is_untouched(
    tmp_path: Path,
):
    pack_path, digest, material = write_pack(
        tmp_path
    )
    out = tmp_path / "out"
    run_dir = out / "14E" / "existing-run"
    run_dir.mkdir(parents=True)
    sentinel = run_dir / "sentinel.txt"
    sentinel.write_text(
        "keep-me",
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError):
        run_math_fidelity_14e_v01(
            pack_path=pack_path,
            output_root=out,
            run_id="existing-run",
            run_started_at=RUN_AT,
            candidate_version=CANDIDATE_VERSION,
            transport=FakeTransport(),
            cases=(case_a(material),),
            expected_pack_sha256=digest,
            objective_id="objective-1",
        )

    assert sentinel.read_text(
        encoding="utf-8"
    ) == "keep-me"

def test_output_root_inside_repository_fails_before_creation(
    tmp_path: Path,
):
    pack_path, digest, material = write_pack(
        tmp_path
    )
    bad_root = (
        _REPO_ROOT
        / "tmp-14e-must-not-exist"
    )

    assert not bad_root.exists()

    with pytest.raises(ValueError):
        run_math_fidelity_14e_v01(
            pack_path=pack_path,
            output_root=bad_root,
            run_id="inside-repo",
            run_started_at=RUN_AT,
            candidate_version=CANDIDATE_VERSION,
            transport=FakeTransport(),
            cases=(case_a(material),),
            expected_pack_sha256=digest,
            objective_id="objective-1",
        )

    assert not bad_root.exists()

def test_transport_exception_still_preserves_case_and_manifest(
    tmp_path: Path,
):
    pack_path, digest, material = write_pack(
        tmp_path
    )

    def failing_transport(request):
        raise RuntimeError("synthetic offline")

    run_dir = run_math_fidelity_14e_v01(
        pack_path=pack_path,
        output_root=tmp_path / "out",
        run_id="transport-error",
        run_started_at=RUN_AT,
        candidate_version=CANDIDATE_VERSION,
        transport=failing_transport,
        cases=(case_a(material),),
        expected_pack_sha256=digest,
        objective_id="objective-1",
    )

    case_record = read_json(
        run_dir
        / "cases"
        / "01-case-a.json"
    )
    manifest = read_json(
        run_dir / "manifest.json"
    )

    assert case_record["record_kind"] in {
        "trace",
        "harness_exception",
    }

    if case_record["record_kind"] == "trace":
        assert (
            case_record["trace"]["final_status"]
            == "error"
        )
    else:
        assert case_record["trace"] is None
        assert (
            case_record["exception_type"]
            == "RuntimeError"
        )

    assert manifest["complete"] is True

def test_frozen_eight_cases_are_all_preserved_without_chat_db_mutation(
    tmp_path: Path,
):
    data_root = (
        Path.home()
        / "Library"
        / "Application Support"
        / "URPP"
        / "local-learning-demo-v01"
    )
    pinned_pack = (
        data_root
        / "packs"
        / f"{PINNED_PACK_SHA256_14E_V01}.json"
    )

    if not pinned_pack.is_file():
        pytest.skip(
            "Pinned local 14E Course Pack is absent."
        )

    chat_db = data_root / "chat.sqlite3"

    before_chat_sha = (
        sha256(chat_db.read_bytes()).hexdigest()
        if chat_db.is_file()
        else None
    )

    def offline_transport(request):
        raise RuntimeError("fake offline")

    frozen_cases = tuple(
        build_math_fidelity_cases_14e_v01()
    )

    run_dir = run_math_fidelity_14e_v01(
        pack_path=pinned_pack,
        output_root=tmp_path / "out",
        run_id="frozen-offline",
        run_started_at=RUN_AT,
        candidate_version=CANDIDATE_VERSION,
        transport=offline_transport,
    )

    files = sorted(
        (run_dir / "cases").glob("*.json")
    )

    assert len(files) == 8

    assert [
        item.name
        for item in files
    ] == [
        (
            f"{index:02d}-"
            f"{case.case_id}.json"
        )
        for index, case in enumerate(
            frozen_cases,
            start=1,
        )
    ]

    follow = [
        read_json(item)
        for item in files
        if "14e-M07-FOLLOW" in item.name
    ]
    assert len(follow) == 1
    assert (
        follow[0]["case_id"]
        == "14e-M07-FOLLOW"
    )

    after_chat_sha = (
        sha256(chat_db.read_bytes()).hexdigest()
        if chat_db.is_file()
        else None
    )

    assert after_chat_sha == before_chat_sha

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)
from app.services.course_knowledge.math_fidelity_l2_bundle_14e_v01 import (
    GOLD_LABEL_14E_V01,
    NO_SCORE_NOTICE_14E_V01,
    build_l2_review_bundles_14e_v01,
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
    source = course_source(
        "pdf-1",
        page=1,
        content=(
            "Synthetic source material describing "
            "a fictional numerical method."
        ),
    )

    objective = CourseLearningObjectiveV01(
        course_id="course-1",
        objective_id="objective-1",
        description="Synthetic objective.",
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id="course-1",
        pack_id="synthetic-pack",
        pack_revision="synthetic-v1",
        objectives=(objective,),
        sources=(source,),
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
    case_id: str,
    prior: bool = False,
) -> SourceGroundedBenchmarkCaseV01:
    source = material.sources[0]

    prior_turns = (
        (
            BenchmarkConversationTurnV01(
                role="student",
                text="Synthetic prior turn.",
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
        question_type=(
            "follow_up"
            if prior
            else "conceptual_explanation"
        ),
        question="Explain the synthetic method.",
        prior_turns=prior_turns,
        source_scope_refs=(source.reference(),),
        required_evidence=(
            BenchmarkEvidenceExpectationV01(
                source_ref=source.reference(),
                evidence_locator="Synthetic page 1.",
                evidence_kind="method",
                rationale="Synthetic support.",
            ),
        ),
        gold=BenchmarkGoldV01(
            required_facts=(
                "The fictional method is identified.",
            ),
            equations=(),
            prohibited_errors=(
                "Do not invent another method.",
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
    def __call__(self, request):
        raw = json.dumps(
            {
                "content": (
                    "Synthetic candidate answer."
                ),
                "source_ids": ["pdf-1"],
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

def build_run(
    tmp_path: Path,
):
    pack_path, digest, material = (
        write_pack(tmp_path)
    )
    cases = (
        synthetic_case(
            material,
            case_id="case-a",
        ),
        synthetic_case(
            material,
            case_id="case-follow",
            prior=True,
        ),
    )

    run_dir = run_math_fidelity_14e_v01(
        pack_path=pack_path,
        output_root=tmp_path / "out",
        run_id="synthetic-l2",
        run_started_at=RUN_AT,
        candidate_version="synthetic-v1",
        transport=FakeTransport(),
        cases=cases,
        expected_pack_sha256=digest,
        objective_id="objective-1",
    )

    return run_dir, cases

def read_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )

def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)

def test_bundles_exist_for_trace_and_unsupported_case(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)

    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    names = sorted(
        path.name
        for path in l2_dir.iterdir()
    )
    assert names == [
        "01-case-a.json",
        "01-case-a.md",
        "02-case-follow.json",
        "02-case-follow.md",
        "index.md",
    ]

    follow = read_json(
        l2_dir / "02-case-follow.json"
    )
    assert (
        follow["candidate"]["note"]
        == "candidate did not run"
    )
    assert (
        follow["candidate"]["record"][
            "record_kind"
        ]
        == "unsupported_by_current_chain"
    )

def test_review_fields_are_blank_and_labels_present(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)
    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    for index, case in enumerate(
        cases,
        start=1,
    ):
        payload = read_json(
            l2_dir
            / f"{index:02d}-{case.case_id}.json"
        )

        assert (
            payload["gold_label"]
            == GOLD_LABEL_14E_V01
        )
        assert (
            payload["no_score_notice"]
            == NO_SCORE_NOTICE_14E_V01
        )
        assert (
            payload["review"]["error_category"]
            is None
        )
        assert payload["review"]["reviewer"] is None
        assert (
            payload["review"]["reviewer_notes"]
            is None
        )

        for item in payload["review"][
            "required_fact_reviews"
        ]:
            assert item["verdict"] is None
            assert item["allowed_verdicts"] == [
                "PASS",
                "FAIL",
                "NOT_ASSESSABLE",
            ]

        for item in payload["review"][
            "prohibited_error_reviews"
        ]:
            assert item["observed"] is None
            assert item["allowed_observed"] == [
                True,
                False,
            ]

        markdown = (
            l2_dir
            / f"{index:02d}-{case.case_id}.md"
        ).read_text(encoding="utf-8")

        assert GOLD_LABEL_14E_V01 in markdown
        assert NO_SCORE_NOTICE_14E_V01 in markdown
        assert "[ ] PASS" in markdown
        assert "[ ] observed=true" in markdown

    index_text = (
        l2_dir / "index.md"
    ).read_text(encoding="utf-8")
    assert GOLD_LABEL_14E_V01 in index_text
    assert NO_SCORE_NOTICE_14E_V01 in index_text

def test_no_numeric_score_keys_exist_anywhere(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)
    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    forbidden = {
        "score",
        "accuracy",
        "pass_rate",
    }

    for json_path in l2_dir.glob("*.json"):
        payload = read_json(json_path)
        assert forbidden.isdisjoint(
            set(walk_keys(payload))
        )

def test_candidate_outputs_are_preserved_verbatim(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)

    source_record = read_json(
        run_dir
        / "cases"
        / "01-case-a.json"
    )
    trace = source_record["trace"]

    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )
    bundle = read_json(
        l2_dir / "01-case-a.json"
    )

    assert (
        bundle["candidate"]["final_answer"]
        == trace["final_answer"]
    )
    assert (
        bundle["candidate"]["raw_model_output"]
        == trace["raw_model_output"]
    )

def test_l1_pointer_included_when_report_exists(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)

    l1_path = (
        run_dir
        / "l1"
        / "l1_report.json"
    )
    l1_path.parent.mkdir()
    l1_path.write_text(
        '{"synthetic":"l1"}\n',
        encoding="utf-8",
    )

    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    bundle = read_json(
        l2_dir / "01-case-a.json"
    )
    assert (
        bundle["l1_report"]
        == "l1/l1_report.json"
    )

def test_existing_run_files_are_byte_identical(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)

    manifest = run_dir / "manifest.json"
    first = (
        run_dir
        / "cases"
        / "01-case-a.json"
    )
    second = (
        run_dir
        / "cases"
        / "02-case-follow.json"
    )
    l1_path = (
        run_dir
        / "l1"
        / "l1_report.json"
    )
    l1_path.parent.mkdir()
    l1_path.write_text(
        '{"sentinel":true}\n',
        encoding="utf-8",
    )

    before = {
        path: path.read_bytes()
        for path in (
            manifest,
            first,
            second,
            l1_path,
        )
    }

    build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    for path, raw in before.items():
        assert path.read_bytes() == raw

def test_rerun_refused_without_modification(
    tmp_path: Path,
):
    run_dir, cases = build_run(tmp_path)

    l2_dir = build_l2_review_bundles_14e_v01(
        run_dir=run_dir,
        cases=cases,
    )

    before = {
        path.relative_to(l2_dir): (
            path.read_bytes()
        )
        for path in l2_dir.iterdir()
        if path.is_file()
    }

    with pytest.raises(FileExistsError):
        build_l2_review_bundles_14e_v01(
            run_dir=run_dir,
            cases=cases,
        )

    after = {
        path.relative_to(l2_dir): (
            path.read_bytes()
        )
        for path in l2_dir.iterdir()
        if path.is_file()
    }
    assert after == before

def test_incomplete_manifest_is_refused(
    tmp_path: Path,
):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        '{"complete":false}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        build_l2_review_bundles_14e_v01(
            run_dir=run_dir,
            cases=(),
        )

    assert not (run_dir / "l2").exists()

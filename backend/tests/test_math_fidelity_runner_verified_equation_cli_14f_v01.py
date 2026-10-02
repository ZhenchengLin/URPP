from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    PINNED_PACK_SHA256_14E_V01,
)
from app.services.course_knowledge import math_fidelity_runner_14e_v01 as runner
from app.services.course_knowledge.models_v01 import CourseSourceRefV01
from app.services.course_knowledge.verified_equation_record_v01 import (
    VerifiedEquationRecordV01,
)
from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)

def _registry() -> VerifiedEquationRegistryV01:
    return VerifiedEquationRegistryV01(
        records=(
            VerifiedEquationRecordV01(
                record_id="synthetic-equation-7",
                record_revision="synthetic-record-v01",
                equation_label="7",
                source_ref=CourseSourceRefV01(
                    source_id="synthetic-source",
                    source_revision="synthetic-source-v01",
                    source_locator="synthetic-page-1",
                    content_sha256="b" * 64,
                ),
                equation_locator="synthetic-equation-7",
                normalized_latex=r"x = y + z",
                review_status="source_checked",
                reviewer_id="synthetic-reviewer",
                reviewed_at=datetime(
                    2026, 1, 1, tzinfo=timezone.utc
                ),
            ),
        ),
    )

def _fake_run(tmp_path: Path, captured: dict):
    def fake_run(**kwargs):
        captured.update(kwargs)
        run_dir = tmp_path / "fake-run"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(
            json.dumps({"kind_counts": {}}),
            encoding="utf-8",
        )
        return run_dir
    return fake_run

def test_main_absent_registry_option_preserves_none(
    tmp_path: Path,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        runner,
        "run_math_fidelity_14e_v01",
        _fake_run(tmp_path, captured),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--run-id", "synthetic-run",
            "--candidate-version", "synthetic-candidate",
            "--pack-path", str(tmp_path / "pack.json"),
            "--output-root", str(tmp_path / "out"),
        ],
    )

    runner.main()

    assert captured["verified_equation_registry"] is None

def test_main_loads_explicit_canonical_registry_via_store(
    tmp_path: Path,
    monkeypatch,
):
    expected = _registry()
    registry_path = (
        tmp_path
        / "verified-equations"
        / f"{PINNED_PACK_SHA256_14E_V01}.json"
    )
    registry_path.parent.mkdir()
    registry_path.write_text(
        expected.model_dump_json(),
        encoding="utf-8",
    )

    captured = {}
    monkeypatch.setattr(
        runner,
        "run_math_fidelity_14e_v01",
        _fake_run(tmp_path, captured),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runner",
            "--run-id", "synthetic-run",
            "--candidate-version", "synthetic-candidate",
            "--pack-path", str(tmp_path / "pack.json"),
            "--output-root", str(tmp_path / "out"),
            "--verified-equation-registry", str(registry_path),
        ],
    )

    runner.main()

    assert captured["verified_equation_registry"] == expected

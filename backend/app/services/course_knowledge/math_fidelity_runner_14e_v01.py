"""URPP 14E — math-fidelity run harness v0.1.

Runs frozen 14E cases through the existing Local Professor benchmark adapter
(read-only reuse) with a per-case scoped sub-pack, and preserves every
per-case record, including failures, in an isolated output directory outside
the repository. No grading happens here; L1 and L2 are separate steps.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Sequence

from app.services.course_knowledge.course_pack_v01 import CoursePackV01
from app.services.course_knowledge.local_professor_benchmark_adapter_v01 import (
    run_local_professor_benchmark_case_v01,
)

from app.services.course_knowledge.verified_equation_registry_v01 import (
    VerifiedEquationRegistryV01,
)
from app.services.course_knowledge.verified_equation_registry_store_v01 import (
    load_verified_equation_registry_v01,
    verified_equation_registry_path_v01,
)
from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    BENCHMARK_VERSION_14E_V01,
    GOLD_REVIEW_STATUS_14E_V01,
    OBJECTIVE_ID_14E_V01,
    PINNED_PACK_SHA256_14E_V01,
    build_math_fidelity_cases_14e_v01,
)
from app.services.course_knowledge.models_v01 import CourseLearningObjectiveV01
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
    validate_source_grounded_benchmark_case_v01,
)

RUNNER_VERSION_14E_V01 = "14e-runner-v0.1"
_REPO_ROOT = Path(__file__).resolve().parents[4]

def load_verified_equation_registry_cli_v01(
    *,
    path: Path | None,
    pack_sha256: str = PINNED_PACK_SHA256_14E_V01,
) -> VerifiedEquationRegistryV01 | None:
    """Load an explicitly requested canonical external registry snapshot."""

    if path is None:
        return None

    supplied = Path(path).expanduser().absolute()
    data_root = supplied.parent.parent
    canonical = verified_equation_registry_path_v01(
        data_root=data_root,
        pack_sha256=pack_sha256,
    )
    if supplied != canonical:
        raise ValueError(
            "Verified-equation registry path must match the canonical "
            "external-store path for the pinned Course Pack."
        )

    registry = load_verified_equation_registry_v01(
        data_root=data_root,
        pack_sha256=pack_sha256,
    )
    if registry is None:
        raise ValueError(
            "Verified-equation registry file does not exist."
        )
    return registry

def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    temporary.write_text(
        serialized + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)

def build_case_scoped_pack_14e_v01(
    *,
    pack: CoursePackV01,
    case: SourceGroundedBenchmarkCaseV01,
    objective_id: str,
) -> CoursePackV01:
    objective = next(
        (
            item
            for item in pack.objectives
            if item.objective_id == objective_id
        ),
        None,
    )
    if objective is None:
        raise ValueError(
            f"objective_id {objective_id!r} is missing from Course Pack"
        )

    source_by_id = {
        source.source_id: source
        for source in pack.sources
    }

    scoped_sources = []

    for scope_ref in case.source_scope_refs:
        source = source_by_id.get(scope_ref.source_id)
        if source is None:
            raise ValueError(
                "benchmark case references a source absent from Course Pack: "
                f"{scope_ref.source_id!r}"
            )

        pack_ref = source.reference()

        if (
            pack_ref.source_id != scope_ref.source_id
            or pack_ref.source_revision != scope_ref.source_revision
            or pack_ref.source_locator != scope_ref.source_locator
            or pack_ref.content_sha256 != scope_ref.content_sha256
        ):
            raise ValueError(
                "benchmark source reference does not exactly match "
                f"Course Pack source {scope_ref.source_id!r}"
            )

        scoped_sources.append(source)

    new_objective = CourseLearningObjectiveV01.model_validate(
        {
            **objective.model_dump(mode="python"),
            "source_refs": case.source_scope_refs,
        }
    )

    return CoursePackV01(
        course_id=pack.course_id,
        pack_id=pack.pack_id,
        pack_revision=pack.pack_revision,
        objectives=(new_objective,),
        sources=tuple(scoped_sources),
    )

def run_math_fidelity_14e_v01(
    *,
    pack_path: Path,
    output_root: Path,
    run_id: str,
    run_started_at: datetime,
    candidate_version: str,
    model_id: str = "qwen3.5:4b",
    transport=None,
    cases: Sequence[SourceGroundedBenchmarkCaseV01] | None = None,
    expected_pack_sha256: str = PINNED_PACK_SHA256_14E_V01,
    objective_id: str = OBJECTIVE_ID_14E_V01,
    verified_equation_registry: VerifiedEquationRegistryV01 | None = None,
) -> Path:
    if re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",
        run_id,
    ) is None:
        raise ValueError(
            "run_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
        )

    if (
        run_started_at.tzinfo is None
        or run_started_at.utcoffset() is None
    ):
        raise ValueError(
            "run_started_at must be timezone-aware"
        )

    try:
        pack_bytes = Path(pack_path).read_bytes()
    except OSError as exc:
        raise ValueError(
            f"could not read Course Pack: {pack_path}"
        ) from exc

    verified_pack_sha256 = sha256(pack_bytes).hexdigest()

    if verified_pack_sha256 != expected_pack_sha256:
        raise ValueError(
            "Course Pack SHA-256 does not match expected pinned hash"
        )

    try:
        pack = CoursePackV01.model_validate_json(pack_bytes)
    except Exception as exc:
        raise ValueError(
            "Course Pack failed CoursePackV01 validation"
        ) from exc

    resolved_output_root = Path(output_root).resolve()

    if (
        resolved_output_root == _REPO_ROOT
        or _REPO_ROOT in resolved_output_root.parents
    ):
        raise ValueError(
            "14E output_root must be outside the repository"
        )

    run_dir = resolved_output_root / "14E" / run_id

    if run_dir.exists():
        raise FileExistsError(
            f"14E run directory already exists: {run_dir}"
        )

    run_dir.mkdir(parents=True)
    cases_dir = run_dir / "cases"
    cases_dir.mkdir()

    selected_cases = (
        tuple(build_math_fidelity_cases_14e_v01())
        if cases is None
        else tuple(cases)
    )

    case_ids: list[str] = []
    case_digests: dict[str, str] = {}
    record_kinds: dict[str, str] = {}
    kind_counts: dict[str, int] = {}

    for case_index, case in enumerate(
        selected_cases,
        start=1,
    ):
        checked_case = (
            validate_source_grounded_benchmark_case_v01(
                case
            )
        )
        case_digest = benchmark_case_digest_v01(
            checked_case
        )

        record: dict[str, object] = {
            "runner_version": RUNNER_VERSION_14E_V01,
            "run_id": run_id,
            "case_index": case_index,
            "case_id": checked_case.case_id,
            "case_digest": case_digest,
            "benchmark_version": (
                checked_case.benchmark_version
            ),
            "scoped_source_ids": [
                ref.source_id
                for ref in checked_case.source_scope_refs
            ],
        }

        try:
            scoped_pack = build_case_scoped_pack_14e_v01(
                pack=pack,
                case=checked_case,
                objective_id=objective_id,
            )

            trace = run_local_professor_benchmark_case_v01(
                case=checked_case,
                pack=scoped_pack,
                objective_id=objective_id,
                candidate_version=candidate_version,
                run_id=run_id,
                run_started_at=run_started_at,
                model_id=model_id,
                transport=transport,
                verified_equation_registry=verified_equation_registry,
            )

            record_kind = "trace"
            record["record_kind"] = record_kind
            record["trace"] = trace.model_dump(
                mode="json"
            )

        except Exception as exc:
            message = str(exc)

            if "prior_turns" in message:
                record_kind = (
                    "unsupported_by_current_chain"
                )
            else:
                record_kind = "harness_exception"

            record["record_kind"] = record_kind
            record["exception_type"] = (
                type(exc).__name__
            )
            record["exception_message"] = message
            record["trace"] = None

        case_ids.append(checked_case.case_id)
        case_digests[checked_case.case_id] = (
            case_digest
        )
        record_kinds[checked_case.case_id] = (
            record_kind
        )
        kind_counts[record_kind] = (
            kind_counts.get(record_kind, 0) + 1
        )

        case_path = (
            cases_dir
            / (
                f"{case_index:02d}-"
                f"{checked_case.case_id}.json"
            )
        )
        _atomic_write_json(
            case_path,
            record,
        )

    manifest: dict[str, object] = {
        "runner_version": RUNNER_VERSION_14E_V01,
        "benchmark_version": BENCHMARK_VERSION_14E_V01,
        "run_id": run_id,
        "run_started_at": run_started_at.isoformat(),
        "candidate_version": candidate_version,
        "model_id": model_id,
        "pinned_pack_sha256": (
            verified_pack_sha256
        ),
        "objective_id": objective_id,
        "gold_review_status": (
            GOLD_REVIEW_STATUS_14E_V01
        ),
        "case_ids": case_ids,
        "case_digests": case_digests,
        "record_kinds": record_kinds,
        "kind_counts": kind_counts,
        "l1_status": "not_evaluated",
        "l2_status": "not_evaluated",
        "complete": True,
    }

    _atomic_write_json(
        run_dir / "manifest.json",
        manifest,
    )

    return run_dir

def main() -> None:
    from app.local_learning_web_v01 import (
        DEFAULT_DATA_ROOT,
    )

    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen URPP 14E math-fidelity "
            "benchmark through the existing Local "
            "Professor adapter."
        )
    )
    parser.add_argument(
        "--run-id",
        required=True,
    )
    parser.add_argument(
        "--candidate-version",
        required=True,
    )
    parser.add_argument(
        "--model-id",
        default="qwen3.5:4b",
    )
    parser.add_argument(
        "--pack-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--verified-equation-registry",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    pack_path = (
        args.pack_path
        if args.pack_path is not None
        else (
            DEFAULT_DATA_ROOT
            / "packs"
            / f"{PINNED_PACK_SHA256_14E_V01}.json"
        )
    )

    output_root = (
        args.output_root
        if args.output_root is not None
        else DEFAULT_DATA_ROOT / "evaluations"
    )

    verified_equation_registry = (
        load_verified_equation_registry_cli_v01(
            path=args.verified_equation_registry,
        )
    )

    run_dir = run_math_fidelity_14e_v01(
        pack_path=pack_path,
        output_root=output_root,
        run_id=args.run_id,
        run_started_at=datetime.now(timezone.utc),
        candidate_version=args.candidate_version,
        model_id=args.model_id,
        verified_equation_registry=verified_equation_registry,
    )

    manifest = json.loads(
        (run_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    print(f"run_dir={run_dir}")
    print(
        "kind_counts="
        + json.dumps(
            manifest["kind_counts"],
            ensure_ascii=False,
            sort_keys=True,
        )
    )

if __name__ == "__main__":
    main()

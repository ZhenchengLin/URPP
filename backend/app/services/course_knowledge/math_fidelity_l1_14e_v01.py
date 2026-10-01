"""URPP 14E — deterministic L1 math-fidelity checks v0.1."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Callable, Sequence

from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    build_math_fidelity_cases_14e_v01,
)
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    BenchmarkExecutionTraceV01,
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
    validate_benchmark_execution_trace_v01,
    validate_source_grounded_benchmark_case_v01,
)

L1_REPORT_VERSION_14E_V01 = "14e-l1-v0.1"
L1_STATUSES_14E_V01 = (
    "PASS",
    "FAIL",
    "NOT_APPLICABLE",
    "NOT_RUN",
)

EQUATION_MARKER_SETS_14E_V01 = {
    "7": (
        "sum sign",
        "d_n",
        "squared distance",
        "gamma factor 1",
        "gamma factor 2",
        "sin",
    ),
    "10": (
        "Delta x",
        "Delta y",
        "fraction or division",
    ),
    "15": (
        "Delta z / 2",
        "D_pl",
        "zero branch",
        "piecewise construct",
    ),
    "16": (
        "min",
        "max",
        "z^+",
        "t_c^+",
        "zero branch",
    ),
}

def _compact(text: str | None) -> str:
    return re.sub(
        r"\s+",
        "",
        text or "",
    )

def _contains_any(
    text: str,
    variants: tuple[str, ...],
) -> bool:
    folded = text.casefold()
    return any(
        variant.casefold() in folded
        for variant in variants
    )

def _gamma_occurrences(text: str) -> int:
    return len(
        re.findall(
            r"(?:\\gamma|γ)",
            text,
            flags=re.IGNORECASE,
        )
    )

def _eq7_marker_results(text: str) -> dict[str, bool]:
    compact = _compact(text)
    return {
        "sum sign": _contains_any(
            compact,
            ("\\sum", "∑"),
        ),
        "d_n": _contains_any(
            compact,
            (
                "d_n",
                "d_{n}",
                "dₙ",
            ),
        ),
        "squared distance": _contains_any(
            compact,
            (
                "^{2}",
                "^2",
                "²",
            ),
        ),
        "gamma factor 1": (
            _gamma_occurrences(compact) >= 1
        ),
        "gamma factor 2": (
            _gamma_occurrences(compact) >= 2
        ),
        "sin": _contains_any(
            compact,
            (
                "\\sin",
                "sin",
            ),
        ),
    }

def _eq10_marker_results(text: str) -> dict[str, bool]:
    compact = _compact(text)
    return {
        "Delta x": _contains_any(
            compact,
            (
                "\\Deltax",
                "\\Delta{x}",
                "Δx",
            ),
        ),
        "Delta y": _contains_any(
            compact,
            (
                "\\Deltay",
                "\\Delta{y}",
                "Δy",
            ),
        ),
        "fraction or division": (
            "\\frac" in compact
            or "/" in compact
            or "÷" in compact
        ),
    }

def _eq15_marker_results(text: str) -> dict[str, bool]:
    compact = _compact(text)
    return {
        "Delta z / 2": (
            _contains_any(
                compact,
                (
                    "\\Deltaz/2",
                    "\\Delta{z}/2",
                    "Δz/2",
                ),
            )
            or bool(
                re.search(
                    r"\\frac\{(?:\\Delta)?z\}\{2\}",
                    compact,
                )
            )
        ),
        "D_pl": _contains_any(
            compact,
            (
                "D_{pl}",
                "D_pl",
                "Dpl",
            ),
        ),
        "zero branch": _contains_any(
            compact,
            (
                "=0",
                "&0",
                "\\0&",
                "{0,",
                ",0",
            ),
        ),
        "piecewise construct": _contains_any(
            compact,
            (
                "\\begin{cases}",
                "cases",
                "piecewise",
                "otherwise",
                "否则",
            ),
        ),
    }

def _eq16_marker_results(text: str) -> dict[str, bool]:
    compact = _compact(text)
    return {
        "min": _contains_any(
            compact,
            ("\\min", "min"),
        ),
        "max": _contains_any(
            compact,
            ("\\max", "max"),
        ),
        "z^+": _contains_any(
            compact,
            (
                "z^{+}",
                "z^+",
                "z⁺",
            ),
        ),
        "t_c^+": _contains_any(
            compact,
            (
                "t_c^{+}",
                "t_{c}^{+}",
                "t_c^+",
                "t_{c}^+",
                "t_c⁺",
                "t_c⁺",
            ),
        ),
        "zero branch": _contains_any(
            compact,
            (
                "=0",
                "&0",
                "\\0&",
                "{0,",
                ",0",
            ),
        ),
    }

_MARKER_FUNCTIONS: dict[
    str,
    Callable[[str], dict[str, bool]],
] = {
    "7": _eq7_marker_results,
    "10": _eq10_marker_results,
    "15": _eq15_marker_results,
    "16": _eq16_marker_results,
}

def check_equation_markers_14e_v01(
    *,
    equation_label: str,
    final_answer: str | None,
) -> tuple[bool, tuple[str, ...]]:
    label = equation_label.strip().strip("()")
    marker_function = _MARKER_FUNCTIONS.get(label)

    if marker_function is None:
        return False, (
            f"unsupported equation label {equation_label!r}",
        )

    results = marker_function(
        final_answer or ""
    )
    missing = tuple(
        marker
        for marker, present in results.items()
        if not present
    )
    return not missing, missing

def _check(
    check_id: str,
    status: str,
    detail: str,
) -> dict[str, str]:
    if status not in L1_STATUSES_14E_V01:
        raise ValueError(
            f"unsupported L1 status {status!r}"
        )

    return {
        "check_id": check_id,
        "status": status,
        "detail": detail,
    }

def _later_check_ids(
    case: SourceGroundedBenchmarkCaseV01,
) -> tuple[str, ...]:
    ids = [
        "L1-TRACE-VALID",
        "L1-FINAL-STATUS",
        "L1-CONTRACT",
        "L1-NO-SESSION-WRITE",
        "L1-CITATION-SCOPE",
        "L1-OUTCOME",
    ]

    for equation in case.gold.equations:
        label = (
            equation.equation_label
            .strip()
            .strip("()")
        )
        ids.append(
            f"L1-EQ-MARKERS-{label}"
        )

    if case.case_id == "14e-M07-MISSING":
        ids.append(
            "L1-NO-FABRICATED-EQ7"
        )

    return tuple(ids)

def _not_run_later_checks(
    case: SourceGroundedBenchmarkCaseV01,
    detail: str,
) -> list[dict[str, str]]:
    return [
        _check(
            check_id,
            "NOT_RUN",
            detail,
        )
        for check_id in _later_check_ids(case)
    ]

def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"cannot read valid JSON from {path}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            f"expected JSON object in {path}"
        )

    return value

def _citation_scope_check(
    *,
    trace: BenchmarkExecutionTraceV01,
    case: SourceGroundedBenchmarkCaseV01,
) -> dict[str, str]:
    allowed = {
        ref.source_id
        for ref in case.source_scope_refs
    }

    selected = {
        ref.source_id
        for ref in trace.selected_source_refs
    }
    out_of_scope_selected = sorted(
        selected - allowed
    )

    if out_of_scope_selected:
        return _check(
            "L1-CITATION-SCOPE",
            "FAIL",
            (
                "selected_source_refs outside case scope: "
                + ", ".join(out_of_scope_selected)
            ),
        )

    if trace.raw_model_output is None:
        return _check(
            "L1-CITATION-SCOPE",
            "NOT_APPLICABLE",
            (
                "selected_source_refs are in scope; "
                "raw_model_output is absent"
            ),
        )

    try:
        raw = json.loads(
            trace.raw_model_output
        )
    except json.JSONDecodeError:
        return _check(
            "L1-CITATION-SCOPE",
            "NOT_APPLICABLE",
            (
                "selected_source_refs are in scope; "
                "raw_model_output does not parse as JSON"
            ),
        )

    if not isinstance(raw, dict):
        return _check(
            "L1-CITATION-SCOPE",
            "NOT_APPLICABLE",
            (
                "selected_source_refs are in scope; "
                "raw_model_output JSON is not an object"
            ),
        )

    source_ids = raw.get("source_ids")
    if not isinstance(source_ids, list):
        return _check(
            "L1-CITATION-SCOPE",
            "NOT_APPLICABLE",
            (
                "selected_source_refs are in scope; "
                "raw_model_output has no source_ids list"
            ),
        )

    raw_ids = {
        item
        for item in source_ids
        if isinstance(item, str)
    }
    out_of_scope_raw = sorted(
        raw_ids - allowed
    )

    if out_of_scope_raw:
        return _check(
            "L1-CITATION-SCOPE",
            "FAIL",
            (
                "raw_model_output source_ids outside "
                "case scope: "
                + ", ".join(out_of_scope_raw)
            ),
        )

    return _check(
        "L1-CITATION-SCOPE",
        "PASS",
        (
            "selected_source_refs and parsed "
            "raw source_ids are within case scope"
        ),
    )

def _evaluate_trace_checks(
    *,
    trace: BenchmarkExecutionTraceV01,
    case: SourceGroundedBenchmarkCaseV01,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    checks.append(
        _check(
            "L1-TRACE-VALID",
            "PASS",
            "trace validates as BenchmarkExecutionTraceV01",
        )
    )

    if trace.final_status == "error":
        checks.append(
            _check(
                "L1-FINAL-STATUS",
                "FAIL",
                (
                    "final_status=error; error_code="
                    f"{trace.error_code!r}"
                ),
            )
        )
    else:
        checks.append(
            _check(
                "L1-FINAL-STATUS",
                "PASS",
                f"final_status={trace.final_status}",
            )
        )

    checks.append(
        _check(
            "L1-CONTRACT",
            (
                "PASS"
                if trace.contract_valid is True
                else "FAIL"
            ),
            f"contract_valid={trace.contract_valid!r}",
        )
    )

    checks.append(
        _check(
            "L1-NO-SESSION-WRITE",
            (
                "PASS"
                if trace.session_write_performed is False
                else "FAIL"
            ),
            (
                "session_write_performed="
                f"{trace.session_write_performed!r}"
            ),
        )
    )

    checks.append(
        _citation_scope_check(
            trace=trace,
            case=case,
        )
    )

    expected = case.expected_outcome
    expected_status = (
        "answered"
        if expected == "answer"
        else "abstained"
    )
    checks.append(
        _check(
            "L1-OUTCOME",
            (
                "PASS"
                if trace.final_status == expected_status
                else "FAIL"
            ),
            (
                f"expected {expected_status}; "
                f"observed {trace.final_status}"
            ),
        )
    )

    for equation in case.gold.equations:
        label = (
            equation.equation_label
            .strip()
            .strip("()")
        )
        passed, missing = (
            check_equation_markers_14e_v01(
                equation_label=label,
                final_answer=trace.final_answer,
            )
        )
        detail = (
            "all required markers found; "
            "structural marker check, not semantic correctness"
            if passed
            else (
                "missing markers: "
                + ", ".join(missing)
                + "; structural marker check, "
                "not semantic correctness"
            )
        )
        checks.append(
            _check(
                f"L1-EQ-MARKERS-{label}",
                "PASS" if passed else "FAIL",
                detail,
            )
        )

    if case.case_id == "14e-M07-MISSING":
        compact = _compact(
            trace.final_answer
        )
        has_sum = _contains_any(
            compact,
            ("\\sum", "∑"),
        )
        has_gamma = _gamma_occurrences(
            compact
        ) >= 1
        fabricated = has_sum and has_gamma

        checks.append(
            _check(
                "L1-NO-FABRICATED-EQ7",
                "FAIL" if fabricated else "PASS",
                (
                    "answer contains both a sum sign and "
                    "a gamma marker"
                    if fabricated
                    else (
                        "answer does not contain both a "
                        "sum sign and a gamma marker"
                    )
                ),
            )
        )

    return checks

def _atomic_write_json(
    path: Path,
    payload: dict[str, object],
) -> None:
    temporary = path.with_name(
        f".{path.name}.tmp"
    )
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(
        temporary,
        path,
    )

def evaluate_l1_run_14e_v01(
    *,
    run_dir: Path,
    cases: Sequence[
        SourceGroundedBenchmarkCaseV01
    ] | None = None,
) -> Path:
    run_dir = Path(run_dir)
    manifest_path = (
        run_dir / "manifest.json"
    )

    if not manifest_path.is_file():
        raise ValueError(
            "14E manifest.json is missing"
        )

    manifest = _load_json(
        manifest_path
    )

    if manifest.get("complete") is not True:
        raise ValueError(
            "14E manifest is not complete=true"
        )

    report_path = (
        run_dir
        / "l1"
        / "l1_report.json"
    )

    if report_path.exists():
        raise FileExistsError(
            f"L1 report already exists: {report_path}"
        )

    selected_cases = (
        tuple(
            build_math_fidelity_cases_14e_v01()
        )
        if cases is None
        else tuple(cases)
    )

    validated_cases = tuple(
        validate_source_grounded_benchmark_case_v01(
            case
        )
        for case in selected_cases
    )

    case_results = []
    status_counts = {
        status: 0
        for status in L1_STATUSES_14E_V01
    }

    for index, case in enumerate(
        validated_cases,
        start=1,
    ):
        expected_digest = (
            benchmark_case_digest_v01(
                case
            )
        )
        record_path = (
            run_dir
            / "cases"
            / f"{index:02d}-{case.case_id}.json"
        )
        checks: list[dict[str, str]] = []

        if not record_path.is_file():
            checks.append(
                _check(
                    "L1-RECORD",
                    "FAIL",
                    "case record is missing",
                )
            )
            checks.append(
                _check(
                    "L1-RUN",
                    "NOT_RUN",
                    "case record is missing",
                )
            )
            checks.extend(
                _not_run_later_checks(
                    case,
                    "case record is missing",
                )
            )
        else:
            try:
                record = _load_json(
                    record_path
                )
            except ValueError as exc:
                checks.append(
                    _check(
                        "L1-RECORD",
                        "FAIL",
                        str(exc),
                    )
                )
                checks.append(
                    _check(
                        "L1-RUN",
                        "NOT_RUN",
                        "case record could not be read",
                    )
                )
                checks.extend(
                    _not_run_later_checks(
                        case,
                        "case record could not be read",
                    )
                )
            else:
                record_ok = (
                    record.get("case_id")
                    == case.case_id
                    and record.get("case_digest")
                    == expected_digest
                )

                checks.append(
                    _check(
                        "L1-RECORD",
                        (
                            "PASS"
                            if record_ok
                            else "FAIL"
                        ),
                        (
                            "case_id and case_digest "
                            "match frozen case"
                            if record_ok
                            else (
                                "case_id or case_digest "
                                "does not match frozen case"
                            )
                        ),
                    )
                )

                kind = record.get(
                    "record_kind"
                )

                if kind == "unsupported_by_current_chain":
                    checks.append(
                        _check(
                            "L1-RUN",
                            "NOT_RUN",
                            (
                                "current chain does not "
                                "support prior_turns"
                            ),
                        )
                    )
                    checks.extend(
                        _not_run_later_checks(
                            case,
                            (
                                "current chain does not "
                                "support prior_turns"
                            ),
                        )
                    )

                elif kind == "harness_exception":
                    checks.append(
                        _check(
                            "L1-RUN",
                            "FAIL",
                            (
                                "harness_exception: "
                                f"{record.get('exception_type')}: "
                                f"{record.get('exception_message')}"
                            ),
                        )
                    )
                    checks.extend(
                        _not_run_later_checks(
                            case,
                            "harness exception",
                        )
                    )

                elif kind == "trace":
                    checks.append(
                        _check(
                            "L1-RUN",
                            "PASS",
                            "record_kind=trace",
                        )
                    )

                    raw_trace = record.get(
                        "trace"
                    )
                    try:
                        trace_model = (
                            BenchmarkExecutionTraceV01
                            .model_validate(
                                raw_trace
                            )
                        )
                        trace = (
                            validate_benchmark_execution_trace_v01(
                                trace_model
                            )
                        )
                    except Exception as exc:
                        checks.append(
                            _check(
                                "L1-TRACE-VALID",
                                "FAIL",
                                (
                                    "trace validation failed: "
                                    f"{type(exc).__name__}"
                                ),
                            )
                        )
                        for check_id in (
                            _later_check_ids(case)[1:]
                        ):
                            checks.append(
                                _check(
                                    check_id,
                                    "NOT_RUN",
                                    (
                                        "trace validation "
                                        "failed"
                                    ),
                                )
                            )
                    else:
                        checks.extend(
                            _evaluate_trace_checks(
                                trace=trace,
                                case=case,
                            )
                        )

                else:
                    checks.append(
                        _check(
                            "L1-RUN",
                            "FAIL",
                            (
                                "unknown record_kind="
                                f"{kind!r}"
                            ),
                        )
                    )
                    checks.extend(
                        _not_run_later_checks(
                            case,
                            "unknown record kind",
                        )
                    )

        for check in checks:
            status_counts[
                check["status"]
            ] += 1

        case_results.append(
            {
                "case_index": index,
                "case_id": case.case_id,
                "case_digest": expected_digest,
                "checks": checks,
            }
        )

    report: dict[str, object] = {
        "l1_report_version": (
            L1_REPORT_VERSION_14E_V01
        ),
        "runner_version": manifest.get(
            "runner_version"
        ),
        "benchmark_version": manifest.get(
            "benchmark_version"
        ),
        "run_id": manifest.get("run_id"),
        "candidate_version": manifest.get(
            "candidate_version"
        ),
        "model_id": manifest.get("model_id"),
        "pinned_pack_sha256": manifest.get(
            "pinned_pack_sha256"
        ),
        "objective_id": manifest.get(
            "objective_id"
        ),
        "gold_review_status": manifest.get(
            "gold_review_status"
        ),
        "status_counts": status_counts,
        "cases": case_results,
    }

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    _atomic_write_json(
        report_path,
        report,
    )

    return report_path

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate deterministic URPP 14E "
            "L1 checks for an existing run."
        )
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    report_path = evaluate_l1_run_14e_v01(
        run_dir=args.run_dir,
    )
    print(report_path)

if __name__ == "__main__":
    main()

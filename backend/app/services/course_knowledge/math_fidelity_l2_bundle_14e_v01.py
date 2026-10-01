"""URPP 14E — semantic review bundle builder v0.1.

This layer prepares human-review artifacts only. It computes no score,
fills no semantic verdict, and never treats LLM self-grading as gold.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
from typing import Sequence
from uuid import uuid4

from app.services.course_knowledge.math_fidelity_cases_14e_v01 import (
    build_math_fidelity_cases_14e_v01,
)
from app.services.course_knowledge.source_grounded_benchmark_v01 import (
    SourceGroundedBenchmarkCaseV01,
    benchmark_case_digest_v01,
    validate_source_grounded_benchmark_case_v01,
)

L2_BUNDLE_VERSION_14E_V01 = "14e-l2-bundle-v0.1"
GOLD_LABEL_14E_V01 = (
    "Gold: assistant source-image review completed; "
    "project-owner sign-off pending (not final gold)"
)
NO_SCORE_NOTICE_14E_V01 = (
    "No score has been computed. LLM self-grading, if ever used, "
    "is a pre-screen only and never gold."
)
L2_VERDICTS_14E_V01 = (
    "PASS",
    "FAIL",
    "NOT_ASSESSABLE",
)
L2_ERROR_CATEGORIES_14E_V01 = (
    "formula_structure",
    "variable_definition",
    "applicability",
    "answer_omission",
    "attribution",
    "unsupported_claim",
    "extraction_ambiguity",
)

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

def _atomic_write_text(
    path: Path,
    text: str,
) -> None:
    temporary = path.with_name(
        f".{path.name}.tmp"
    )
    temporary.write_text(
        text,
        encoding="utf-8",
    )
    os.replace(
        temporary,
        path,
    )

def _atomic_write_json(
    path: Path,
    value: dict[str, object],
) -> None:
    _atomic_write_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

def _candidate_payload(
    record: dict[str, object] | None,
) -> dict[str, object]:
    if record is None:
        return {
            "record": None,
            "note": (
                "candidate did not run because "
                "the case record is missing"
            ),
        }

    kind = record.get("record_kind")

    if kind == "trace":
        trace = record.get("trace")
        if isinstance(trace, dict):
            return {
                "record_kind": "trace",
                "final_answer": trace.get(
                    "final_answer"
                ),
                "raw_model_output": trace.get(
                    "raw_model_output"
                ),
            }

        return {
            "record": record,
            "note": (
                "candidate trace is malformed; "
                "record preserved verbatim"
            ),
        }

    if kind in {
        "unsupported_by_current_chain",
        "harness_exception",
    }:
        return {
            "record": record,
            "note": "candidate did not run",
        }

    return {
        "record": record,
        "note": (
            "candidate record kind is unrecognized; "
            "record preserved verbatim"
        ),
    }

def _bundle_payload(
    *,
    case: SourceGroundedBenchmarkCaseV01,
    case_index: int,
    record: dict[str, object] | None,
    l1_pointer: str | None,
) -> dict[str, object]:
    return {
        "bundle_version": L2_BUNDLE_VERSION_14E_V01,
        "gold_label": GOLD_LABEL_14E_V01,
        "no_score_notice": NO_SCORE_NOTICE_14E_V01,
        "case_index": case_index,
        "case_id": case.case_id,
        "case_digest": benchmark_case_digest_v01(
            case
        ),
        "question": case.question,
        "prior_turns": [
            turn.model_dump(mode="json")
            for turn in case.prior_turns
        ],
        "scope_source_ids": [
            ref.source_id
            for ref in case.source_scope_refs
        ],
        "gold": {
            "equations": [
                equation.model_dump(mode="json")
                for equation in case.gold.equations
            ],
            "required_facts": list(
                case.gold.required_facts
            ),
            "prohibited_errors": list(
                case.gold.prohibited_errors
            ),
        },
        "candidate": _candidate_payload(
            record
        ),
        "l1_report": l1_pointer,
        "review": {
            "required_fact_reviews": [
                {
                    "required_fact": fact,
                    "verdict": None,
                    "allowed_verdicts": list(
                        L2_VERDICTS_14E_V01
                    ),
                }
                for fact in case.gold.required_facts
            ],
            "prohibited_error_reviews": [
                {
                    "prohibited_error": error,
                    "observed": None,
                    "allowed_observed": [
                        True,
                        False,
                    ],
                }
                for error in case.gold.prohibited_errors
            ],
            "error_category": None,
            "allowed_error_categories": list(
                L2_ERROR_CATEGORIES_14E_V01
            ),
            "reviewer": None,
            "reviewer_notes": None,
        },
    }

def _verbatim_lines(
    value: object,
) -> list[str]:
    if value is None:
        text = "null"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    return [
        "~~~~text",
        text,
        "~~~~",
    ]

def _render_bundle_markdown(
    payload: dict[str, object],
) -> str:
    gold = payload["gold"]
    candidate = payload["candidate"]
    review = payload["review"]

    assert isinstance(gold, dict)
    assert isinstance(candidate, dict)
    assert isinstance(review, dict)

    lines = [
        GOLD_LABEL_14E_V01,
        "",
        f"# 14E L2 Review — {payload['case_id']}",
        "",
        NO_SCORE_NOTICE_14E_V01,
        "",
        f"- Case digest: `{payload['case_digest']}`",
        (
            "- Scope source IDs: "
            + ", ".join(
                f"`{item}`"
                for item in payload[
                    "scope_source_ids"
                ]
            )
        ),
        (
            "- L1 report: "
            + (
                f"`{payload['l1_report']}`"
                if payload["l1_report"]
                else "not present"
            )
        ),
        "",
        "## Question",
        "",
        str(payload["question"]),
        "",
        "## Prior turns",
        "",
    ]

    prior_turns = payload["prior_turns"]
    if prior_turns:
        for turn in prior_turns:
            lines.append(
                f"- {turn['role']}: {turn['text']}"
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Gold equations",
            "",
        ]
    )

    equations = gold["equations"]
    if equations:
        for equation in equations:
            lines.extend(
                [
                    f"- {equation['equation_label']}",
                    "",
                    "$$",
                    str(
                        equation[
                            "normalized_latex"
                        ]
                    ),
                    "$$",
                ]
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Required facts",
            "",
        ]
    )

    if gold["required_facts"]:
        for fact in gold["required_facts"]:
            lines.append(f"- {fact}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Prohibited errors",
            "",
        ]
    )

    if gold["prohibited_errors"]:
        for error in gold["prohibited_errors"]:
            lines.append(f"- {error}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Candidate",
            "",
        ]
    )

    if "final_answer" in candidate:
        lines.extend(
            [
                "### Final answer",
                "",
                *_verbatim_lines(
                    candidate["final_answer"]
                ),
                "",
                "### Raw model output",
                "",
                *_verbatim_lines(
                    candidate["raw_model_output"]
                ),
            ]
        )
    else:
        lines.extend(
            [
                (
                    "**Note:** "
                    + str(
                        candidate.get(
                            "note",
                            "candidate did not run",
                        )
                    )
                ),
                "",
                "### Preserved candidate record",
                "",
                *_verbatim_lines(
                    candidate.get("record")
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Semantic review",
            "",
            "### Required facts",
            "",
        ]
    )

    fact_reviews = review[
        "required_fact_reviews"
    ]
    if fact_reviews:
        for item in fact_reviews:
            lines.append(
                "- [ ] PASS / [ ] FAIL / "
                "[ ] NOT_ASSESSABLE — "
                + str(item["required_fact"])
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "### Prohibited errors",
            "",
        ]
    )

    error_reviews = review[
        "prohibited_error_reviews"
    ]
    if error_reviews:
        for item in error_reviews:
            lines.append(
                "- [ ] observed=true / "
                "[ ] observed=false — "
                + str(item["prohibited_error"])
            )
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "### Error category",
            "",
        ]
    )

    for category in review[
        "allowed_error_categories"
    ]:
        lines.append(
            f"- [ ] {category}"
        )

    lines.extend(
        [
            "",
            "### Reviewer",
            "",
            "- Reviewer: ____________________",
            "- Reviewer notes: ____________________",
            "",
            NO_SCORE_NOTICE_14E_V01,
            "",
        ]
    )

    return "\n".join(lines)

def _render_index_markdown(
    bundles: list[dict[str, object]],
) -> str:
    lines = [
        GOLD_LABEL_14E_V01,
        "",
        "# URPP 14E L2 Semantic Review Bundles",
        "",
        NO_SCORE_NOTICE_14E_V01,
        "",
    ]

    for payload in bundles:
        index = int(payload["case_index"])
        case_id = str(payload["case_id"])
        lines.append(
            f"- [{case_id}]"
            f"({index:02d}-{case_id}.md)"
        )

    lines.extend(
        [
            "",
            NO_SCORE_NOTICE_14E_V01,
            "",
        ]
    )
    return "\n".join(lines)

def build_l2_review_bundles_14e_v01(
    *,
    run_dir: Path,
    cases: Sequence[
        SourceGroundedBenchmarkCaseV01
    ] | None = None,
) -> Path:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"

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

    l2_dir = run_dir / "l2"
    if l2_dir.exists():
        raise FileExistsError(
            f"L2 directory already exists: {l2_dir}"
        )

    selected_cases = (
        tuple(
            build_math_fidelity_cases_14e_v01()
        )
        if cases is None
        else tuple(cases)
    )
    checked_cases = tuple(
        validate_source_grounded_benchmark_case_v01(
            case
        )
        for case in selected_cases
    )

    l1_path = (
        run_dir
        / "l1"
        / "l1_report.json"
    )
    l1_pointer = (
        "l1/l1_report.json"
        if l1_path.is_file()
        else None
    )

    temp_dir = run_dir / (
        f".l2.tmp-{uuid4().hex}"
    )
    temp_dir.mkdir(
        parents=False,
        exist_ok=False,
    )

    bundles: list[dict[str, object]] = []

    try:
        for index, case in enumerate(
            checked_cases,
            start=1,
        ):
            record_path = (
                run_dir
                / "cases"
                / f"{index:02d}-{case.case_id}.json"
            )
            record = (
                _load_json(record_path)
                if record_path.is_file()
                else None
            )

            payload = _bundle_payload(
                case=case,
                case_index=index,
                record=record,
                l1_pointer=l1_pointer,
            )
            bundles.append(payload)

            stem = (
                f"{index:02d}-{case.case_id}"
            )
            _atomic_write_json(
                temp_dir / f"{stem}.json",
                payload,
            )
            _atomic_write_text(
                temp_dir / f"{stem}.md",
                _render_bundle_markdown(
                    payload
                ),
            )

        _atomic_write_text(
            temp_dir / "index.md",
            _render_index_markdown(
                bundles
            ),
        )

        if l2_dir.exists():
            raise FileExistsError(
                f"L2 directory already exists: {l2_dir}"
            )

        os.replace(
            temp_dir,
            l2_dir,
        )

    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    return l2_dir

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build URPP 14E L2 semantic "
            "human-review bundles."
        )
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    print(
        build_l2_review_bundles_14e_v01(
            run_dir=args.run_dir,
        )
    )

if __name__ == "__main__":
    main()

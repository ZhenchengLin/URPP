"""
URPP 14C-5D-12E: Manifest-driven NanoJev Shadow Evaluation.

This module reuses the verified v0.1 local MPS model loader,
candidate-path encoder, and Choice scoring logic.

The v0.2 Manifest is pinned by SHA-256.

No Student State, Teaching Trace, or Mastery Evidence is
accessed or modified. No student-facing delivery is authorized.

Agreement with the registered LU Pilot is NOT evidence
of pedagogical effectiveness.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import time

from collections import Counter
from pathlib import Path
from typing import Any

from app.services.course_knowledge.nanojev_local_eval_v01 import (
    CHECKPOINT_REVISION,
    CHECKPOINT_SHA256,
    _load_model,
    _verify_checkpoint,
    answer_from_scores_v01,
    encode_choice_v01,
)

from app.services.course_knowledge.nanojev_shadow_adapter_v01 import (
    build_nanojev_lu_request_v01,
    parse_nanojev_lu_response_v01,
)


MANIFEST_SHA256 = (
    "6e4b982aded24aece67f5e064e76641"
    "208a28147267452c8394198052de27c8e"
)

MANIFEST_RELATIVE_PATH = (
    "evaluations/nanojev_shadow_eval_v02_manifest.json"
)

QUESTION_IDS = (
    "teaching_plan",
    "follow_up_check",
)

EXPECTED_GROUP_COUNTS = {
    "baseline": 2,
    "paraphrase": 4,
    "candidate_description": 2,
    "ambiguous": 2,
}

EXPECTED_CONTROLS = {
    "candidate_orders": ["original", "reversed"],
    "repeats_per_configuration": 2,
    "candidate_count_per_question": 2,
    "questions_per_case": 2,
}


def manifest_path_v02() -> Path:
    """Locate the committed Manifest relative to backend/."""

    return (
        Path(__file__).resolve().parents[3]
        / MANIFEST_RELATIVE_PATH
    )


def load_manifest_v02(path: Path) -> dict[str, Any]:
    """
    Verify exact Manifest bytes before using its contents.

    No inference is performed here.
    """

    if path.is_symlink() or not path.is_file():
        raise ValueError("Manifest must be a regular file.")

    raw = path.read_bytes()

    digest = hashlib.sha256(raw).hexdigest()

    if digest != MANIFEST_SHA256:
        raise ValueError("Frozen v0.2 Manifest SHA-256 mismatch.")

    def reject_constant(value: str):
        raise ValueError(f"Invalid JSON constant: {value}")

    manifest = json.loads(
        raw,
        parse_constant=reject_constant,
    )

    if manifest.get("schema_version") != (
        "urpp-nanojev-shadow-manifest-v02"
    ):
        raise ValueError("Unexpected Manifest schema.")

    if manifest.get("status") != "developer_audit_only":
        raise ValueError("Unexpected Manifest status.")

    if manifest.get("student_delivery_authorized") is not False:
        raise ValueError("Unexpected delivery authorization.")

    if manifest.get("checkpoint_revision") != CHECKPOINT_REVISION:
        raise ValueError("Unexpected checkpoint revision.")

    if manifest.get("checkpoint_sha256") != CHECKPOINT_SHA256:
        raise ValueError("Unexpected checkpoint SHA-256.")

    if manifest.get("experiment_controls") != EXPECTED_CONTROLS:
        raise ValueError("Unexpected experiment controls.")

    cases = manifest.get("cases")

    if (
        not isinstance(cases, list)
        or len(cases) != 10
        or manifest.get("distinct_case_count") != 10
    ):
        raise ValueError("Expected ten distinct Manifest cases.")

    ids = [case["case_id"] for case in cases]

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Manifest case IDs.")

    counts = Counter(case["group"] for case in cases)

    if dict(counts) != EXPECTED_GROUP_COUNTS:
        raise ValueError("Unexpected Manifest case groups.")

    for case in cases:

        if case["group"] == "ambiguous":

            if (
                case["baseline_focus_id"] is not None
                or case["reference_policy"] is not None
            ):
                raise ValueError(
                    "Ambiguous cases must have no forced reference."
                )

        elif (
            case["baseline_focus_id"]
            not in ("sign_relation", "calculation")
            or case["reference_policy"] is None
        ):
            raise ValueError(
                "Clear-need case is missing its reference policy."
            )

    # Protect exact v0.1 baseline inputs inside the v0.2 Manifest.
    indexed = {
        case["case_id"]: case
        for case in cases
    }

    for focus_id in ("sign_relation", "calculation"):

        baseline_id = f"baseline_{focus_id}_01"

        if indexed[baseline_id]["request"] != (
            build_nanojev_lu_request_v01(focus_id)
        ):
            raise ValueError(
                f"Original baseline input changed: {baseline_id}"
            )

    return manifest


def build_configurations_v02(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Create independent request copies for both candidate orders
    and both repeats. Do not mutate the frozen Manifest.
    """

    controls = manifest["experiment_controls"]
    configurations = []

    for case in manifest["cases"]:

        for order in controls["candidate_orders"]:

            for repeat in range(
                1,
                controls["repeats_per_configuration"] + 1,
            ):

                request = copy.deepcopy(case["request"])

                questions = request["states"][0]["questions"]

                if order == "reversed":

                    for question_id in QUESTION_IDS:

                        question = questions[question_id]

                        question["criteria"] = dict(
                            reversed(
                                list(question["criteria"].items())
                            )
                        )

                configurations.append(
                    {
                        "case_id": case["case_id"],
                        "group": case["group"],
                        "baseline_focus_id": case[
                            "baseline_focus_id"
                        ],
                        "candidate_order": order,
                        "repeat": repeat,
                        "reference_policy": copy.deepcopy(
                            case["reference_policy"]
                        ),
                        "request": request,
                    }
                )

    if len(configurations) != 40:
        raise ValueError(
            "Expected exactly 40 evaluation configurations."
        )

    return configurations


def record_response_v02(
    configuration: dict[str, Any],
    answers: dict[str, Any],
    durations: dict[str, float],
) -> dict[str, Any]:
    """
    Validate one model response through the existing URPP Adapter.

    Ambiguous cases must not acquire correctness labels.
    """

    source_state = configuration["request"]["states"][0]

    response = {
        "schema_version": "openjev-toy-inference-v1",
        "states": [
            {
                "id": source_state["id"],
                "answers": answers,
            }
        ],
    }

    shadow = parse_nanojev_lu_response_v01(
        json.dumps(
            response,
            ensure_ascii=False,
            allow_nan=False,
        )
    )

    if (
        shadow.execution_authority is not False
        or shadow.student_delivery_authorized is not False
        or shadow.proposal.origin != "untrusted_shadow_model"
    ):
        raise ValueError("Shadow execution boundary violated.")

    selected = {
        "plan_id": shadow.proposal.plan_id,
        "check_id": shadow.proposal.check_id,
    }

    reference = configuration["reference_policy"]

    if reference is None:

        plan_matches = None
        check_matches = None

    else:

        plan_matches = (
            selected["plan_id"] == reference["plan_id"]
        )

        check_matches = (
            selected["check_id"] == reference["check_id"]
        )

    return {
        "case_id": configuration["case_id"],
        "group": configuration["group"],
        "baseline_focus_id": configuration["baseline_focus_id"],
        "candidate_order": configuration["candidate_order"],
        "repeat": configuration["repeat"],
        "selected": selected,
        "reference_policy": copy.deepcopy(reference),
        "plan_matches_pilot": plan_matches,
        "check_matches_pilot": check_matches,
        "probabilities": {
            question_id: answers[question_id]["probabilities"]
            for question_id in QUESTION_IDS
        },
        "inference_seconds": durations,
        "status": "developer_audit_only",
        "student_delivery_authorized": False,
    }


def summarize_records_v02(
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """
    Summarize each distinct case independently.

    Repeats and candidate-order variants are not counted
    as additional student or teaching cases.
    """

    summary = {}

    for case in manifest["cases"]:

        case_id = case["case_id"]

        scoped = [
            record
            for record in records
            if record["case_id"] == case_id
        ]

        if len(scoped) != 4:
            raise ValueError(
                f"Incomplete configurations for {case_id}"
            )

        by_key = {
            (record["candidate_order"], record["repeat"]):
                record
            for record in scoped
        }

        if len(by_key) != 4:
            raise ValueError(
                f"Duplicate configuration for {case_id}"
            )

        original_1 = by_key[("original", 1)]
        original_2 = by_key[("original", 2)]
        reversed_1 = by_key[("reversed", 1)]
        reversed_2 = by_key[("reversed", 2)]

        max_repeat_difference = 0.0
        max_order_difference = 0.0

        for question_id in QUESTION_IDS:

            for candidate_id in original_1[
                "probabilities"
            ][question_id]:

                p_o1 = original_1[
                    "probabilities"
                ][question_id][candidate_id]

                p_o2 = original_2[
                    "probabilities"
                ][question_id][candidate_id]

                p_r1 = reversed_1[
                    "probabilities"
                ][question_id][candidate_id]

                p_r2 = reversed_2[
                    "probabilities"
                ][question_id][candidate_id]

                max_repeat_difference = max(
                    max_repeat_difference,
                    abs(p_o1 - p_o2),
                    abs(p_r1 - p_r2),
                )

                max_order_difference = max(
                    max_order_difference,
                    abs(p_o1 - p_r1),
                )

        summary[case_id] = {
            "group": case["group"],
            "baseline_focus_id": case["baseline_focus_id"],
            "reference_policy": case["reference_policy"],
            "original_choice": original_1["selected"],
            "reversed_choice": reversed_1["selected"],
            "candidate_order_choice_stable": (
                original_1["selected"]
                == reversed_1["selected"]
            ),
            "original_repeat_choice_stable": (
                original_1["selected"]
                == original_2["selected"]
            ),
            "reversed_repeat_choice_stable": (
                reversed_1["selected"]
                == reversed_2["selected"]
            ),
            "max_repeat_probability_difference": (
                max_repeat_difference
            ),
            "max_order_probability_difference": (
                max_order_difference
            ),
            "plan_matches_pilot": original_1[
                "plan_matches_pilot"
            ],
            "check_matches_pilot": original_1[
                "check_matches_pilot"
            ],
        }

    return summary


def run_evaluation_v02(
    manifest: dict[str, Any],
    model_dir: Path,
) -> dict[str, Any]:
    """Run the frozen 40 configurations with the v0.1 MPS model."""

    import torch
    import transformers

    configurations = build_configurations_v02(manifest)

    model_dir = model_dir.expanduser().resolve(strict=True)

    _verify_checkpoint(
        model_dir / "best.safetensors"
    )

    started = time.perf_counter()

    model, tokenizer, run_config = _load_model(model_dir)

    print(
        "PASS: Pinned NanoJev checkpoint loaded on MPS.",
        flush=True,
    )

    records = []

    for configuration in configurations:

        state = configuration["request"]["states"][0]

        answers = {}
        durations = {}

        for question_id in QUESTION_IDS:

            question = state["questions"][question_id]

            candidate_ids, paths = encode_choice_v01(
                tokenizer,
                state["state"],
                question,
                run_config["max_length"],
            )

            question_started = time.perf_counter()

            with torch.inference_mode():

                logits = model(
                    paths,
                    tokenizer.pad_token_id,
                )

                torch.mps.synchronize()

                scores = logits.float().cpu().tolist()

            answer = answer_from_scores_v01(
                candidate_ids,
                scores,
            )

            answers[question_id] = answer

            durations[question_id] = round(
                time.perf_counter() - question_started,
                4,
            )

        record = record_response_v02(
            configuration,
            answers,
            durations,
        )

        records.append(record)

        print(
            "PASS:",
            record["case_id"],
            record["candidate_order"],
            "repeat",
            record["repeat"],
            record["selected"],
            flush=True,
        )

    summary = summarize_records_v02(
        records,
        manifest,
    )

    return {
        "schema_version": "urpp-nanojev-shadow-eval-v02",
        "status": "developer_audit_only",
        "manifest_sha256": MANIFEST_SHA256,
        "checkpoint_revision": CHECKPOINT_REVISION,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "environment": {
            "device": "mps",
            "precision": "fp32",
            "torch": torch.__version__,
            "transformers": transformers.__version__,
        },
        "distinct_case_count": len(manifest["cases"]),
        "configuration_count": len(configurations),
        "records": records,
        "summary": summary,
        "wall_seconds": round(
            time.perf_counter() - started,
            3,
        ),
        "teaching_decision_quality": "unverified",
        "student_delivery_authorized": False,
    }


def main() -> None:

    parser = argparse.ArgumentParser(
        description="URPP NanoJev v0.2 developer-only evaluation."
    )

    modes = parser.add_mutually_exclusive_group(
        required=True
    )

    modes.add_argument(
        "--dry-run",
        action="store_true",
    )

    modes.add_argument(
        "--run",
        action="store_true",
    )

    args = parser.parse_args()

    manifest = load_manifest_v02(
        manifest_path_v02()
    )

    configurations = build_configurations_v02(
        manifest
    )

    if args.dry_run:

        print("PASS: Frozen Manifest SHA-256 verified.")
        print("Distinct cases:", len(manifest["cases"]))
        print("Configurations:", len(configurations))
        print("Choice questions per configuration:", len(QUESTION_IDS))

        for case in manifest["cases"]:

            print(
                case["case_id"],
                "| group:",
                case["group"],
                "| reference:",
                case["reference_policy"],
            )

        print("No model loaded. No experiment output written.")
        return

    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        raise RuntimeError(
            "MPS fallback must be explicitly disabled."
        )

    if (
        os.environ.get("HF_HUB_OFFLINE") != "1"
        or os.environ.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        raise RuntimeError(
            "Offline inference must be explicitly enabled."
        )

    cache_root = (
        Path.home()
        / "Library"
        / "Caches"
        / "URPP"
    )

    model_dir = cache_root / "nanojev-unified-games-v1"

    output_dir = cache_root / "evals"

    output_file = (
        output_dir
        / "nanojev_shadow_eval_v02.json"
    )

    if output_dir.is_symlink():
        raise RuntimeError(
            "Evaluation output directory must not be a symlink."
        )

    if output_file.exists() or output_file.is_symlink():
        raise FileExistsError(
            "v0.2 output already exists; refusing to overwrite."
        )

    result = run_evaluation_v02(
        manifest,
        model_dir,
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "x",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

        file.write("\n")

    print("OUTPUT:", output_file, flush=True)
    print("PASS: v0.2 developer-only evaluation saved.", flush=True)
    print("NOT AUTHORIZED: Student-facing delivery.", flush=True)


if __name__ == "__main__":
    main()

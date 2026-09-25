"""
URPP 14C-5D-11A: NanoJev Local Shadow Evaluation Runner.

Scope:
- Two synthetic LU learning foci.
- Two registered Choice questions.
- Original and reversed candidate orders.
- Two repetitions per configuration.
- Pinned NanoJev checkpoint.
- Developer-only shadow evaluation.

This module does not authorize teaching, access Student State,
create Teaching Trace, or create Mastery Evidence.

The original NanoJev checkpoint was trained for non-URPP
decision tasks. Agreement with the current LU Pilot is not
proof of pedagogical effectiveness.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import sys
import time

from pathlib import Path
from typing import Any

from app.services.course_knowledge.nanojev_shadow_adapter_v01 import (
    build_nanojev_lu_request_v01,
    parse_nanojev_lu_response_v01,
)

from app.services.course_knowledge.controlled_lu_teaching_v01 import (
    select_pilot_plan_v01,
)


CHECKPOINT_REVISION = (
    "047b927b30882a1138fc504821b82ac145a4b81a"
)

CHECKPOINT_SHA256 = (
    "f68c47d66998231b86b7e91b4ed5e82"
    "ae23acf104c8b7cd6d165c3ac7b7ffe1b"
)

FOCUS_IDS = (
    "sign_relation",
    "calculation",
)

QUESTION_IDS = (
    "teaching_plan",
    "follow_up_check",
)

ORDER_VARIANTS = (
    "original",
    "reversed",
)

REPEATS = 2


def build_eval_cases_v01() -> list[dict[str, Any]]:
    """
    Construct the fixed developer-only evaluation matrix.

    Each case receives its own request dictionary.
    No case may mutate another case's candidate order.
    """

    cases = []

    for focus_id in FOCUS_IDS:

        for order in ORDER_VARIANTS:

            for repeat in range(1, REPEATS + 1):

                request = build_nanojev_lu_request_v01(
                    focus_id
                )

                questions = request["states"][0]["questions"]

                if order == "reversed":

                    for question_id in QUESTION_IDS:

                        original = questions[question_id]

                        questions[question_id] = {
                            **original,
                            "criteria": dict(
                                reversed(
                                    list(
                                        original["criteria"].items()
                                    )
                                )
                            ),
                        }

                reference = select_pilot_plan_v01(
                    focus_id
                )

                cases.append(
                    {
                        "focus_id": focus_id,
                        "candidate_order": order,
                        "repeat": repeat,
                        "request": request,
                        "registered_pilot": {
                            "plan_id": reference.plan_id,
                            "check_id": reference.check_id,
                        },
                    }
                )

    return cases


def encode_choice_v01(
    tokenizer: Any,
    state_text: str,
    question: dict[str, Any],
    max_length: int,
) -> tuple[list[str], list[list[int]]]:
    """
    Match the published NanoJev candidate-path segmentation.

    State, question, and candidate segments are encoded
    separately; no input is silently truncated.
    """

    if question["type"] != "choice":
        raise ValueError("Only Choice questions are supported.")

    if (
        type(max_length) is not int
        or max_length <= 0
        or type(tokenizer.eos_token_id) is not int
    ):
        raise ValueError("Invalid tokenizer or context limit.")

    candidate_ids = list(question["criteria"])

    if len(candidate_ids) != 2:
        raise ValueError("Expected exactly two registered candidates.")

    segments = [
        f"State:\n{state_text}\n",
        (
            "Question type: choice\n"
            f"Question:\n{question['instructions']}\n"
        ),
    ]

    prefix = []

    for segment in segments:

        prefix.extend(
            tokenizer.encode(
                segment,
                add_special_tokens=False,
            )
        )

    paths = []

    for candidate_id in candidate_ids:

        candidate = (
            f"{candidate_id}: "
            f"{question['criteria'][candidate_id]}"
        )

        suffix = (
            f"Candidate:\n{candidate}\n"
            "Decision:"
        )

        path = (
            prefix
            + tokenizer.encode(
                suffix,
                add_special_tokens=False,
            )
            + [tokenizer.eos_token_id]
        )

        if len(path) > max_length:
            raise ValueError("Candidate path exceeds context limit.")

        paths.append(path)

    return candidate_ids, paths


def answer_from_scores_v01(
    candidate_ids: list[str],
    scores: list[float],
) -> dict[str, Any]:
    """Convert two finite logits into a Choice answer."""

    if len(candidate_ids) != 2 or len(scores) != 2:
        raise ValueError("Expected two candidates and two logits.")

    if not all(math.isfinite(value) for value in scores):
        raise ValueError("Nonfinite decision logits.")

    largest = max(scores)

    exponentials = [
        math.exp(value - largest)
        for value in scores
    ]

    total = math.fsum(exponentials)

    probabilities = [
        value / total
        for value in exponentials
    ]

    selected_index = max(
        range(2),
        key=probabilities.__getitem__,
    )

    selected = candidate_ids[selected_index]

    return {
        "type": "choice",
        "probabilities": dict(
            zip(candidate_ids, probabilities)
        ),
        "choice": selected,
        "value": selected,
    }


def _verify_checkpoint(weights: Path) -> None:
    """Verify the complete pinned checkpoint before model loading."""

    digest = hashlib.sha256()

    with weights.open("rb") as file:

        for block in iter(
            lambda: file.read(8 * 1024 * 1024),
            b"",
        ):
            digest.update(block)

    if digest.hexdigest() != CHECKPOINT_SHA256:
        raise ValueError("Checkpoint SHA-256 mismatch.")


def _load_model(model_dir: Path):
    """
    Load the complete NanoJev checkpoint onto Apple MPS.

    Heavy dependencies are imported only when real
    inference is explicitly requested.
    """

    import torch

    from torch import nn
    from safetensors import safe_open
    from transformers import (
        AutoConfig,
        AutoModel,
        AutoTokenizer,
    )

    if not torch.backends.mps.is_available():
        raise RuntimeError("Apple MPS is unavailable.")

    config = json.loads(
        (model_dir / "config.json").read_text(
            encoding="utf-8"
        )
    )

    if (
        config.get("set_head") != "attention"
        or config.get("model") != "Qwen/Qwen3-0.6B"
    ):
        raise ValueError("Unexpected NanoJev checkpoint configuration.")

    body_config = AutoConfig.from_pretrained(
        str(model_dir / "backbone_config"),
        local_files_only=True,
        trust_remote_code=False,
    )

    body_config.use_cache = False

    tokenizer = AutoTokenizer.from_pretrained(
        str(model_dir / "tokenizer"),
        local_files_only=True,
        trust_remote_code=False,
    )

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    if tokenizer.eos_token_id is None:
        raise ValueError("Tokenizer has no EOS token.")

    class ChoiceDecisionModel(nn.Module):
        """
        Inference-only two-candidate Choice computation.

        This is an experimental MPS implementation of the
        published Backbone + scalar + set-attention structure.
        It does not establish CUDA/MPS numerical equivalence.
        """

        def __init__(self, backbone):

            super().__init__()

            self.backbone = backbone

            hidden = backbone.config.hidden_size

            self.norm = nn.LayerNorm(hidden)
            self.scalar = nn.Linear(hidden, 1)

            self.set_project = nn.Linear(
                hidden + 1,
                128,
            )

            self.set_attention = nn.MultiheadAttention(
                128,
                4,
                dropout=0.0,
                batch_first=True,
            )

            self.set_output = nn.Linear(128, 1)

        def forward(self, paths, pad_token):

            device = self.scalar.weight.device

            lengths = torch.tensor(
                [len(path) for path in paths],
                dtype=torch.long,
                device=device,
            )

            width = int(lengths.max())

            tokens = torch.full(
                (len(paths), width),
                pad_token,
                dtype=torch.long,
                device=device,
            )

            for index, path in enumerate(paths):

                tokens[index, :len(path)] = torch.tensor(
                    path,
                    dtype=torch.long,
                    device=device,
                )

            attention = (
                torch.arange(width, device=device)[None, :]
                < lengths[:, None]
            )

            hidden = self.backbone(
                input_ids=tokens,
                attention_mask=attention,
                use_cache=False,
            ).last_hidden_state

            leaves = hidden[
                torch.arange(len(paths), device=device),
                lengths - 1,
            ]

            h = self.norm(leaves.unsqueeze(0))

            scalar_scores = (
                self.scalar(h)
                .squeeze(-1)
                .float()
            )

            count = len(paths)

            log_k = h.new_full(
                (1, count, 1),
                math.log(count),
            )

            projected = self.set_project(
                torch.cat(
                    [h, log_k],
                    dim=-1,
                )
            )

            mixed, _ = self.set_attention(
                projected,
                projected,
                projected,
                need_weights=False,
            )

            delta = self.set_output(
                torch.tanh(projected + mixed)
            ).squeeze(-1).float()

            return (scalar_scores + delta).squeeze(0)

    backbone = AutoModel.from_config(
        body_config,
        attn_implementation="sdpa",
        trust_remote_code=False,
    )

    model = ChoiceDecisionModel(backbone)

    state = model.state_dict()

    with safe_open(
        str(model_dir / "best.safetensors"),
        framework="pt",
        device="cpu",
    ) as checkpoint:

        if set(state) != set(checkpoint.keys()):
            raise ValueError("Checkpoint tensor keys mismatch.")

        with torch.no_grad():

            for name, destination in state.items():

                source = checkpoint.get_tensor(name)

                if source.shape != destination.shape:
                    raise ValueError(
                        f"Checkpoint tensor shape mismatch: {name}"
                    )

                destination.copy_(source)

                del source

    del state

    gc.collect()

    model = model.to(
        device=torch.device("mps"),
        dtype=torch.float32,
    )

    model.eval()

    torch.mps.synchronize()

    return model, tokenizer, config


def run_eval_v01(model_dir: Path) -> dict[str, Any]:
    """Execute the fixed cases and validate every shadow response."""

    import torch
    import transformers

    model_dir = model_dir.expanduser().resolve(strict=True)

    weights = model_dir / "best.safetensors"

    _verify_checkpoint(weights)

    started = time.perf_counter()

    model, tokenizer, config = _load_model(model_dir)

    print(
        "PASS: Pinned NanoJev checkpoint loaded on MPS.",
        flush=True,
    )

    records = []

    cases = build_eval_cases_v01()

    for case in cases:

        source_state = case["request"]["states"][0]

        answers = {}

        durations = {}

        for question_id in QUESTION_IDS:

            question = source_state["questions"][question_id]

            candidate_ids, paths = encode_choice_v01(
                tokenizer,
                source_state["state"],
                question,
                config["max_length"],
            )

            question_start = time.perf_counter()

            with torch.inference_mode():

                logits = model(
                    paths,
                    tokenizer.pad_token_id,
                )

                torch.mps.synchronize()

                scores = logits.float().cpu().tolist()

            durations[question_id] = round(
                time.perf_counter() - question_start,
                4,
            )

            answers[question_id] = answer_from_scores_v01(
                candidate_ids,
                scores,
            )

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
            json.dumps(response, allow_nan=False)
        )

        if (
            shadow.execution_authority is not False
            or shadow.student_delivery_authorized is not False
            or shadow.proposal.origin != "untrusted_shadow_model"
        ):
            raise RuntimeError("Shadow authorization boundary violated.")

        selected = {
            "plan_id": shadow.proposal.plan_id,
            "check_id": shadow.proposal.check_id,
        }

        records.append(
            {
                "focus_id": case["focus_id"],
                "candidate_order": case["candidate_order"],
                "repeat": case["repeat"],
                "selected": selected,
                "registered_pilot": case["registered_pilot"],
                "plan_matches_pilot": (
                    selected["plan_id"]
                    == case["registered_pilot"]["plan_id"]
                ),
                "check_matches_pilot": (
                    selected["check_id"]
                    == case["registered_pilot"]["check_id"]
                ),
                "probabilities": {
                    question_id: answers[question_id]["probabilities"]
                    for question_id in QUESTION_IDS
                },
                "inference_seconds": durations,
                "status": "developer_audit_only",
            }
        )

        print(
            "PASS:",
            case["focus_id"],
            case["candidate_order"],
            "repeat",
            case["repeat"],
            selected,
            flush=True,
        )

    summary = {}

    for focus_id in FOCUS_IDS:

        scoped = [
            record
            for record in records
            if record["focus_id"] == focus_id
        ]

        original = [
            record
            for record in scoped
            if record["candidate_order"] == "original"
        ]

        reversed_order = [
            record
            for record in scoped
            if record["candidate_order"] == "reversed"
        ]

        maximum_repeat_difference = 0.0

        for pair in (original, reversed_order):

            for question_id in QUESTION_IDS:

                first = pair[0]["probabilities"][question_id]
                second = pair[1]["probabilities"][question_id]

                for candidate_id in first:

                    maximum_repeat_difference = max(
                        maximum_repeat_difference,
                        abs(
                            first[candidate_id]
                            - second[candidate_id]
                        ),
                    )

        summary[focus_id] = {
            "original_choice": original[0]["selected"],
            "reversed_choice": reversed_order[0]["selected"],
            "candidate_order_choice_stable": (
                original[0]["selected"]
                == reversed_order[0]["selected"]
            ),
            "original_repeat_choice_stable": (
                original[0]["selected"]
                == original[1]["selected"]
            ),
            "reversed_repeat_choice_stable": (
                reversed_order[0]["selected"]
                == reversed_order[1]["selected"]
            ),
            "max_repeat_probability_difference": (
                maximum_repeat_difference
            ),
            "registered_pilot": original[0]["registered_pilot"],
        }

    return {
        "schema_version": "urpp-nanojev-shadow-eval-v01",
        "status": "developer_audit_only",
        "checkpoint_revision": CHECKPOINT_REVISION,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "environment": {
            "device": "mps",
            "precision": "fp32",
            "torch": torch.__version__,
            "transformers": transformers.__version__,
        },
        "case_count": len(cases),
        "records": records,
        "summary": summary,
        "wall_seconds": round(
            time.perf_counter() - started,
            3,
        ),
        "student_delivery_authorized": False,
        "teaching_decision_quality": "unverified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="URPP NanoJev developer-only local evaluation."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixed cases without loading a model.",
    )

    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the pinned checkpoint using Apple MPS.",
    )

    args = parser.parse_args()

    if args.dry_run == args.run:
        parser.error("Choose exactly one of --dry-run or --run.")

    cases = build_eval_cases_v01()

    if args.dry_run:

        assert len(cases) == 8

        print("PASS: Eight fixed evaluation configurations.")

        print(
            json.dumps(
                [
                    {
                        "focus_id": case["focus_id"],
                        "candidate_order": case["candidate_order"],
                        "repeat": case["repeat"],
                        "registered_pilot": case["registered_pilot"],
                    }
                    for case in cases
                ],
                indent=2,
            )
        )

        print("No model loaded. No file written.")
        return

    if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        raise RuntimeError("MPS fallback must be explicitly disabled.")

    if (
        os.environ.get("HF_HUB_OFFLINE") != "1"
        or os.environ.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        raise RuntimeError("Offline inference must be explicitly enabled.")

    cache_root = Path.home() / "Library" / "Caches" / "URPP"

    model_dir = cache_root / "nanojev-unified-games-v1"

    output_dir = cache_root / "evals"

    output_file = output_dir / "nanojev_shadow_eval_v01.json"

    if output_dir.is_symlink():
        raise RuntimeError("Evaluation output directory is a symlink.")

    if output_file.exists() or output_file.is_symlink():
        raise FileExistsError(
            "Evaluation output already exists; it will not be overwritten."
        )

    result = run_eval_v01(model_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Exclusive creation prevents accidental replacement.
    with output_file.open("x", encoding="utf-8") as file:

        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

        file.write("\n")

    print(
        "\nEVALUATION SUMMARY:\n"
        + json.dumps(
            result["summary"],
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    print("OUTPUT:", output_file, flush=True)

    print("PASS: Developer-only evaluation saved.", flush=True)


if __name__ == "__main__":
    main()

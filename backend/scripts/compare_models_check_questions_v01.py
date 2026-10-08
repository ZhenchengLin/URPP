"""Compare local models on course-workspace check questions (docs/34).

For every topic of a saved course path, generate check questions with each
model, keep only those that pass the re-solve check, and write every kept item
(question, choices, answer key, model) to a JSON file for hand-checking.

Usage (from backend/):
    python scripts/compare_models_check_questions_v01.py \
        --data-root <workspace data root> --course <course-id> \
        --models qwen3.5:4b qwen3.5:9b --out results.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.services.course_workspace.llm_json_v01 import (
    CourseGenerationErrorV01,
    LocalJsonModelV01,
)
from app.services.course_workspace.practice_v01 import generate_items_v01
from app.services.course_workspace.service_v01 import CourseWorkspaceServiceV01


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--course", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--topics", nargs="*", help="Only these topic IDs (default: all).")
    args = parser.parse_args()

    # Read-only use of the workspace: no items are stored.
    reader = CourseWorkspaceServiceV01(data_root=args.data_root, model=None)
    outline = reader.store.latest_outline(args.course)
    results = []
    for model_id in args.models:
        model = LocalJsonModelV01(model=model_id)
        for topic in outline["topics"]:
            if args.topics and topic["topic_id"] not in args.topics:
                continue
            sources = reader._topic_sources(args.course, topic)
            started = time.time()
            try:
                generated = generate_items_v01(model, topic, sources)
                error = None
            except CourseGenerationErrorV01 as exc:
                generated, error = {"items": [], "rejected": {}}, str(exc)
            results.append({
                "model": model_id,
                "topic_id": topic["topic_id"],
                "topic": topic["title"],
                "seconds": round(time.time() - started, 1),
                "error": error,
                "rejected": generated["rejected"],
                "kept": [
                    {k: item.get(k) for k in
                     ("kind", "question", "choices", "answer_value", "answer_letter")}
                    for item in generated["items"]
                ],
            })
            print(model_id, topic["topic_id"], "kept", len(generated["items"]),
                  "rejected", generated["rejected"], error or "")
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

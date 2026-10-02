"""Read-only, server-free diagnostic of one existing URPP Professor turn.

The original SQLite file and pinned pack are read into a disposable private
workspace. Generated messages cannot be appended even to that copy. All output
is metadata unless --show-answer is explicitly set. Not a semantic fact check.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.llm.local_ollama_professor_gateway_v01 import LocalOllamaProfessorGatewayV01
from app.local_learning_web_v01 import DEFAULT_DATA_ROOT
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01


class _InputCaptured(Exception):
    pass


class _WriteBlocked(Exception):
    pass


def _copy_workspace(original: Path, destination: Path, digest: str) -> None:
    original = original.expanduser().absolute()
    if original.is_symlink() or not original.is_dir():
        raise ValueError("Original local workspace is missing or a symlink.")
    database = original / "chat.sqlite3"
    pack = original / "packs" / f"{digest}.json"
    if (original / "packs").is_symlink():
        raise ValueError("Original packs directory is a symlink.")
    for path in (database, pack):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Original database or digest-pinned Course Pack missing.")
    destination.mkdir(mode=0o700)
    (destination / "packs").mkdir(mode=0o700)
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination / "chat.sqlite3") as copy:
            source.backup(copy)  # Snapshot in SQLite, including any committed WAL rows.
    (destination / "chat.sqlite3").chmod(0o600)
    shutil.copyfile(pack, destination / "packs" / pack.name)
    (destination / "packs" / pack.name).chmod(0o600)


def _response_metadata(response: dict, *, selected_ids: set[str], show_answer: bool) -> None:
    print("MODEL: done=", response.get("done"), "reason=", response.get("done_reason"),
          "prompt_tokens=", response.get("prompt_eval_count"),
          "generated_tokens=", response.get("eval_count"), flush=True)
    raw = (response.get("message") or {}).get("content", "")
    print("MODEL: raw_response_chars=", len(raw) if isinstance(raw, str) else "invalid", flush=True)
    try:
        parsed = LocalOllamaProfessorGatewayV01._decode_json(raw)
    except Exception as exc:
        print("CONTRACT: JSON decode failure:", type(exc).__name__, flush=True)
        return
    if type(parsed) is not dict:
        print("CONTRACT: JSON root:", type(parsed).__name__, flush=True)
        return
    actual = set(parsed)
    required = {"content", "source_ids", "answer_status"}
    print("CONTRACT: returned_fields=", sorted(actual), "missing=", sorted(required - actual),
          "unexpected=", sorted(actual - required), flush=True)
    status = parsed.get("answer_status")
    claims = parsed.get("source_ids")
    print("CONTRACT: answer_status=", repr(status), "source_ids_type=", type(claims).__name__,
          "claimed_count=", len(claims) if type(claims) is list else "invalid", flush=True)
    if type(claims) is list:
        print("CONTRACT: all_citations_in_selected_sources=",
              all(type(item) is str and item in selected_ids for item in claims), flush=True)
        if status == "insufficient_evidence" and claims:
            print("CONTRACT: STATUS/CITATION CONFLICT — expected adapter rejection", flush=True)
    answer = parsed.get("content")
    print("CONTRACT: answer_chars=", len(answer) if type(answer) is str else "invalid", flush=True)
    if show_answer and type(answer) is str:
        print("ANSWER (untrusted model output):\n" + answer, flush=True)


def probe(*, data_root: Path, session_id: str, pack_sha256: str, question: str,
          input_only: bool = False, show_answer: bool = False, transport=None) -> str:
    """Run the real teaching pipeline on an isolated disposable DB copy.

    Optional transport is for synthetic tests only; the default calls local Ollama.
    Return INPUT_ONLY, VALIDATED_NOT_SAVED, REJECTED, or FAILED_BEFORE_MODEL.
    """
    if not isinstance(pack_sha256, str) or len(pack_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in pack_sha256
    ):
        raise ValueError("Invalid Course Pack SHA-256.")
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 128:
        raise ValueError("Invalid Session ID.")
    if not isinstance(question, str) or not question.strip() or len(question) > 1500:
        raise ValueError("Invalid bounded student question.")

    with tempfile.TemporaryDirectory(prefix="urpp-professor-cli-") as folder:
        root = Path(folder) / "workspace"
        _copy_workspace(Path(data_root), root, pack_sha256)
        captured = {"model_called": False}

        def instrument(request: dict) -> dict:
            payload = json.loads(request["messages"][1]["content"])
            sources = payload["sources"]
            selected_ids = {source["source_id"] for source in sources}
            print("INPUT: selected_excerpts=", len(sources), "input_characters=",
                  len(request["messages"][1]["content"]),
                  "num_ctx=", request["options"].get("num_ctx"), flush=True)
            for item in sources:
                locator = urlsplit(item["source_locator"])
                pages = parse_qs(locator.query).get("pages", ["not-declared"])[0]
                print("INPUT: excerpt=", item["source_id"].rsplit("-excerpt-", 1)[-1],
                      "pages=", pages, "characters=", len(item["content"]), flush=True)
            if input_only:
                raise _InputCaptured()
            captured["model_called"] = True
            response = (LocalOllamaProfessorGatewayV01._post_local(request)
                        if transport is None else transport(request))
            _response_metadata(response, selected_ids=selected_ids, show_answer=show_answer)
            return response

        workspace = LocalLearningWorkspaceV01(
            data_root=root,
            gateway_factory=lambda: LocalOllamaProfessorGatewayV01(
                model="qwen3.5:4b", transport=instrument,
            ),
        )
        before = workspace.resume(pack_sha256=pack_sha256, session_id=session_id)
        print("SESSION: saved_turns=", before.turn_count, "saved_messages=", len(before.messages), flush=True)

        def block_write(**kwargs):
            print("VALIDATION: passed; SQLite append deliberately blocked", flush=True)
            raise _WriteBlocked()

        workspace.store.append_exchange = block_write
        outcome = "UNKNOWN"
        try:
            workspace.explain(
                pack_sha256=pack_sha256,
                session_id=session_id,
                question=question,
                expected_message_count=len(before.messages),
            )
        except _InputCaptured:
            outcome = "INPUT_ONLY"
        except _WriteBlocked:
            outcome = "VALIDATED_NOT_SAVED"
        except Exception as exc:
            outcome = "REJECTED" if captured["model_called"] else "FAILED_BEFORE_MODEL"
            print("FAILURE: stage=", outcome, "exception=", type(exc).__name__,
                  "message=", str(exc)[:200], flush=True)
            cause = exc.__cause__
            if cause is not None:
                print("FAILURE: cause=", type(cause).__name__, str(cause)[:200], flush=True)

        after = workspace.resume(pack_sha256=pack_sha256, session_id=session_id)
        if after.messages != before.messages:
            raise RuntimeError("Isolation failure: disposable Session mutated unexpectedly.")
        print("RESULT:", outcome, "| disposable session unchanged | original DB never opened for write",
              flush=True)
        return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI URPP Professor diagnostic (no URPP web server, no saved turns).")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--pack-sha256", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--input-only", action="store_true", help="Print actual selected excerpts; do not call Ollama.")
    parser.add_argument("--show-answer", action="store_true", help="Explicitly print private model answer to terminal.")
    args = parser.parse_args()
    outcome = probe(
        data_root=args.data_root, session_id=args.session_id,
        pack_sha256=args.pack_sha256, question=args.question,
        input_only=args.input_only, show_answer=args.show_answer,
    )
    if outcome == "FAILED_BEFORE_MODEL":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

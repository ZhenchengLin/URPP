"""URPP 14D-2B: bounded loopback-only HTTP adapter for LocalLearningWorkspaceV01.

Developer-only: no student authentication, multi-user support, or mastery updates.
The workspace owns files, Course Pack integrity, and durable chat; routes do
not duplicate those responsibilities. No server is started on import.
"""

from __future__ import annotations

import base64
import binascii
import re
import threading

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal

from app.services.course_knowledge.local_learning_workspace_v01 import (
    LocalLearningWorkspaceV01,
)
from app.services.course_knowledge.local_material_import_v01 import MAX_FILE_BYTES
from app.services.course_knowledge.local_pdf_import_v01 import MAX_PDF_BYTES

# 8 MiB binary -> 11.18 MiB Base64 + a small JSON envelope. Stream reads stop
# at this bound even when Content-Length is missing or dishonest.
MAX_UPLOAD_BODY_BYTES = 11_300_000
MAX_CHAT_BODY_BYTES = 12_000
_SHA256 = r"[0-9a-f]{64}"
_ALLOWED_HOST = re.compile(r"(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?\Z", re.I)
_TEST_HOST = re.compile(r"testserver(?::[0-9]{1,5})?\Z", re.I)


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Upload(_Input):
    filename: str = Field(min_length=1, max_length=255)
    file_base64: str = Field(min_length=1)
    objective_description: str = Field(min_length=1, max_length=1000)
    allow_local_teaching: bool


class _Chat(_Input):
    mode: Literal["course", "general"] = "course"
    session_id: str = Field(min_length=1, max_length=128)
    pack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    student_text: str = Field(min_length=1, max_length=1500)
    expected_message_count: int = Field(ge=0)


def _snapshot(snapshot) -> dict:
    return {
        "session_id": snapshot.session_id,
        "course_id": snapshot.course_id,
        "objective_id": snapshot.objective_id,
        "pack_sha256": snapshot.pack_sha256,
        "turn_count": snapshot.turn_count,
        "message_count": len(snapshot.messages),
        "messages": [message.model_dump(mode="json") for message in snapshot.messages],
    }


async def _bounded_json(request: Request, model, *, limit: int):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "application/json is required.")
    if request.headers.get("x-urpp-local-request") != "1":
        raise HTTPException(403, "Local request header is required.")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) < 0 or int(length) > limit:
                raise HTTPException(413, "Request body exceeds the local limit.")
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length.") from exc
    parts = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(413, "Request body exceeds the local limit.")
        parts.append(chunk)
    try:
        return model.model_validate_json(b"".join(parts))
    except ValidationError as exc:
        raise HTTPException(400, "Invalid request fields.") from exc


def create_local_learning_api_v01(
    *, workspace: LocalLearningWorkspaceV01, allow_test_host: bool = False
) -> FastAPI:
    """Create a local API around an already initialized single-user workspace.

    For tests only, allow_test_host accepts TestClient's synthetic host. It
    MUST remain False in a real local server. This is not authentication.
    """
    if not isinstance(workspace, LocalLearningWorkspaceV01):
        raise TypeError("Expected LocalLearningWorkspaceV01.")
    if type(allow_test_host) is not bool:
        raise TypeError("allow_test_host must be bool.")
    app = FastAPI(
        title="URPP Local Learning API", docs_url=None, redoc_url=None,
        openapi_url=None, debug=False,
    )
    # Single-user pilot: one bounded lock also avoids an unbounded map of
    # attacker-supplied or abandoned Session IDs. Not cross-process locking.
    chat_lock = threading.Lock()

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        hosts = request.headers.getlist("host")
        if len(hosts) != 1:
            return JSONResponse({"detail": "Local Host required."}, status_code=403)
        host = hosts[0].lower()
        if not (_ALLOWED_HOST.fullmatch(host) or
                (allow_test_host and _TEST_HOST.fullmatch(host))):
            return JSONResponse({"detail": "Local Host required."}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin.lower() != "http://" + host:
            return JSONResponse({"detail": "Cross-origin request denied."}, status_code=403)
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            return JSONResponse({"detail": "Cross-site request denied."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "local-demo-ready"}

    @app.post("/api/upload")
    async def upload(request: Request):
        data = await _bounded_json(request, _Upload, limit=MAX_UPLOAD_BODY_BYTES)
        if data.allow_local_teaching is not True:
            raise HTTPException(400, "Explicit local-teaching permission is required.")
        extension = data.filename.lower().rsplit(".", 1)[-1]
        if extension not in {"pdf", "txt", "md", "markdown"}:
            raise HTTPException(400, "Unsupported document format.")
        binary_limit = MAX_PDF_BYTES if extension == "pdf" else MAX_FILE_BYTES
        if len(data.file_base64) > 4 * ((binary_limit + 2) // 3):
            raise HTTPException(413, "Document exceeds the format limit.")
        try:
            document = base64.b64decode(data.file_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(400, "Invalid Base64 document.") from exc
        if not 0 < len(document) <= binary_limit:
            raise HTTPException(413, "Document is empty or exceeds the format limit.")
        try:
            imported = workspace.import_document(
                filename=data.filename,
                content=document,
                objective_description=data.objective_description,
                allow_local_teaching=True,
            )
        except PermissionError as exc:
            raise HTTPException(403, "Local teaching permission denied.") from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "Document cannot be imported.") from exc
        except RuntimeError as exc:
            raise HTTPException(503, "Local PDF parser is unavailable.") from exc
        response = _snapshot(imported.snapshot)
        response.update({
            "filename": imported.filename,
            "source_count": imported.source_count,
            "pages_without_text": list(imported.pages_without_text),
        })
        return response

    @app.get("/api/session/{session_id}")
    def resume(
        session_id: str,
        pack_sha256: str = Query(min_length=64, max_length=64, pattern="^" + _SHA256 + "$"),
    ):
        if not 1 <= len(session_id) <= 128:
            raise HTTPException(400, "Invalid Session ID.")
        try:
            snapshot = workspace.resume(pack_sha256=pack_sha256, session_id=session_id)
        except LookupError as exc:
            raise HTTPException(404, "Exact local Session not found.") from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "Saved Session could not be validated.") from exc
        return _snapshot(snapshot)

    @app.post("/api/chat")
    async def chat(request: Request):
        data = await _bounded_json(request, _Chat, limit=MAX_CHAT_BODY_BYTES)
        # A normal synchronous route operates in a worker thread, but we use
        # this async route for the bounded request stream. Run blocking model
        # generation in a worker, NOT in the event loop.
        from starlette.concurrency import run_in_threadpool

        def complete_turn():
            with chat_lock:
                arguments = dict(
                    pack_sha256=data.pack_sha256,
                    session_id=data.session_id,
                    question=data.student_text,
                    expected_message_count=data.expected_message_count,
                )
                if data.mode == "general":
                    return workspace.explain_general(**arguments)
                return workspace.explain(**arguments).snapshot
        try:
            snapshot = await run_in_threadpool(complete_turn)
        except LookupError as exc:
            raise HTTPException(404, "Exact local Session not found.") from exc
        except ValueError as exc:
            if "advanced since" in str(exc):
                raise HTTPException(409, "Session changed. Reload saved history.") from exc
            raise HTTPException(400, "Question or Course Pack is invalid.") from exc
        except Exception as exc:
            # Do not reflect private document text, model output or paths.
            raise HTTPException(502, "Local Professor turn failed; reload Session.") from exc
        return _snapshot(snapshot)

    return app

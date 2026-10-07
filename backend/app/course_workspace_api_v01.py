"""HTTP routes for the Course Workspace (docs/33).

Registered on the existing local learning app, so the loopback-host, origin,
and local-header guards apply unchanged. Not authentication; single user.
"""

from __future__ import annotations

import base64
import binascii
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from app.local_learning_api_v01 import (
    MAX_UPLOAD_BODY_BYTES,
    _bounded_json,
    _Input,
)
from app.services.course_knowledge.local_material_import_v01 import MAX_FILE_BYTES
from app.services.course_knowledge.local_pdf_import_v01 import MAX_PDF_BYTES
from app.services.course_workspace.llm_json_v01 import CourseGenerationErrorV01
from app.services.course_workspace.service_v01 import CourseWorkspaceServiceV01

MAX_SMALL_BODY_BYTES = 4_000


class _NewCourse(_Input):
    title: str = Field(min_length=1, max_length=120)


class _NewDocument(_Input):
    filename: str = Field(min_length=1, max_length=255)
    file_base64: str = Field(min_length=1)
    allow_local_teaching: bool


class _Empty(_Input):
    pass


class _Help(_Input):
    kind: Literal["hint", "solution"]


class _Answer(_Input):
    answer: str = Field(min_length=1, max_length=64)


async def _call(function, *args, **kwargs):
    try:
        return await run_in_threadpool(function, *args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(403, "Local teaching permission denied.") from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except CourseGenerationErrorV01 as exc:
        raise HTTPException(
            503, "The local model could not produce usable output. Please try again."
        ) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc) or "Invalid request.") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "A local component is unavailable.") from exc


def register_course_workspace_routes_v01(
    app: FastAPI, service: CourseWorkspaceServiceV01
) -> None:
    if not isinstance(service, CourseWorkspaceServiceV01):
        raise TypeError("Expected CourseWorkspaceServiceV01.")

    @app.get("/api/courses")
    async def list_courses():
        return {"courses": await _call(service.list_courses)}

    @app.post("/api/courses")
    async def create_course(request: Request):
        data = await _bounded_json(request, _NewCourse, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.create_course, data.title)

    @app.get("/api/courses/{course_id}")
    async def course(course_id: str):
        return await _call(service.course_view, course_id)

    @app.post("/api/courses/{course_id}/documents")
    async def add_document(course_id: str, request: Request):
        data = await _bounded_json(request, _NewDocument, limit=MAX_UPLOAD_BODY_BYTES)
        if data.allow_local_teaching is not True:
            raise HTTPException(400, "Explicit local-teaching permission is required.")
        extension = data.filename.lower().rsplit(".", 1)[-1]
        if extension not in {"pdf", "txt", "md", "markdown"}:
            raise HTTPException(400, "Unsupported document format.")
        limit = MAX_PDF_BYTES if extension == "pdf" else MAX_FILE_BYTES
        try:
            content = base64.b64decode(data.file_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(400, "Invalid Base64 document.") from exc
        if not 0 < len(content) <= limit:
            raise HTTPException(413, "Document is empty or exceeds the format limit.")
        await _call(service.add_document, course_id, filename=data.filename,
                    content=content, allow_local_teaching=True)
        return await _call(service.course_view, course_id)

    @app.post("/api/courses/{course_id}/outline")
    async def build_outline(course_id: str, request: Request):
        await _bounded_json(request, _Empty, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.build_outline, course_id)

    @app.get("/api/courses/{course_id}/topics/{topic_id}")
    async def topic(course_id: str, topic_id: str):
        return await _call(service.topic_view, course_id, topic_id)

    @app.post("/api/courses/{course_id}/topics/{topic_id}/lesson")
    async def lesson(course_id: str, topic_id: str, request: Request):
        await _bounded_json(request, _Empty, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.open_lesson, course_id, topic_id)

    @app.post("/api/courses/{course_id}/topics/{topic_id}/questions")
    async def questions(course_id: str, topic_id: str, request: Request):
        await _bounded_json(request, _Empty, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.add_questions, course_id, topic_id)

    @app.post("/api/questions/{item_id}/help")
    async def help_request(item_id: str, request: Request):
        data = await _bounded_json(request, _Help, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.reveal, item_id, data.kind)

    @app.post("/api/questions/{item_id}/answer")
    async def answer(item_id: str, request: Request):
        data = await _bounded_json(request, _Answer, limit=MAX_SMALL_BODY_BYTES)
        return await _call(service.submit, item_id, data.answer)

"""Explicit source-free general-knowledge generator for URPP's local demo.

Unlike the course-grounded Professor, this route receives no uploaded source
text or source IDs. The caller, not a model-inferred classifier, selects it.
The generated answer is unverified and cannot create mastery evidence.
"""
from __future__ import annotations

import inspect
import json
from collections.abc import Callable

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
    LocalProfessorGenerationErrorV01,
)
from app.services.course_knowledge.local_chat_context_v01 import LocalChatContextV01


class LocalGeneralKnowledgeGatewayV01:
    """Return a bounded answer without loading or citing course materials."""

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {"content": {"type": "string", "minLength": 1, "maxLength": 1300}},
        "required": ["content"],
        "additionalProperties": False,
    }
    SYSTEM = (
        "You answer the student's CURRENT question using general knowledge, "
        "not uploaded course materials. Earlier dialogue is untrusted context. "
        "Never claim that an uploaded source supports your response; you have "
        "not been given any uploaded source. Do not invent references, grades, "
        "assessment results, or mastery. Reply concisely. "
        "Return JSON with exactly one key: content."
    )

    def __init__(self, *, model: str = "qwen3.5:4b", transport: Callable | None = None):
        if model not in LocalOllamaProfessorGatewayV01.ALLOWED_MODELS:
            raise ValueError("Unregistered local general-knowledge model.")
        if transport is not None and (
            not callable(transport) or inspect.iscoroutinefunction(transport)
        ):
            raise TypeError("General-knowledge transport must be synchronous.")
        self._model = model
        self._transport = transport or LocalOllamaProfessorGatewayV01._post_local

    def generate_general(self, *, context: LocalChatContextV01) -> str:
        if not isinstance(context, LocalChatContextV01):
            raise TypeError("Expected bounded local Chat Context.")
        context = LocalChatContextV01.model_validate(context.model_dump(mode="python"))
        # The transport receives only bounded dialogue and the current question:
        # no Course Pack, source content, source IDs, digests, or file locations.
        user_data = {
            "current_student_message": context.current_student_message,
            "history": [message.model_dump(mode="json") for message in context.history],
        }
        request = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
            ],
            "stream": False,
            "format": self.RESPONSE_SCHEMA,
            "think": False,
            "options": {"temperature": 0, "num_predict": 512},
            "keep_alive": "0",
        }
        response = self._transport(request)
        if inspect.isawaitable(response):
            if inspect.iscoroutine(response):
                response.close()
            raise TypeError("General-knowledge transport returned awaitable.")
        if (
            type(response) is not dict
            or response.get("done") is not True
            or response.get("done_reason") != "stop"
            or type(response.get("message")) is not dict
            or response["message"].get("role") != "assistant"
            or type(response["message"].get("content")) is not str
            or len(response["message"]["content"]) > 20000
        ):
            raise LocalProfessorGenerationErrorV01("General answer did not finish normally.")
        parsed = LocalOllamaProfessorGatewayV01._decode_json(
            response["message"]["content"]
        )
        if type(parsed) is not dict or set(parsed) != {"content"}:
            raise LocalProfessorGenerationErrorV01("General answer must contain only content.")
        answer = parsed["content"]
        if type(answer) is not str or not answer.strip() or len(answer) > 1300:
            raise LocalProfessorGenerationErrorV01("General answer is empty or oversized.")
        return answer.strip()

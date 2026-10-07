"""Schema-constrained JSON generation through the local Ollama server.

Reuses the Professor gateway's fixed 127.0.0.1 transport (no proxies, no
redirects). Generated content is untrusted: callers validate every field.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
    LocalProfessorGenerationErrorV01,
)

DEFAULT_MODEL_V01 = "qwen3.5:4b"

# Scan escapes left to right so "\\" pairs stay intact; a backslash that does not
# start a valid JSON escape (e.g. "\|" or "\alpha" with a forgotten doubling) is
# doubled.
_ESCAPE = re.compile(r'\\(["\\/bfnrtu])|\\')


def _double_invalid_escapes(raw: str) -> str:
    return _ESCAPE.sub(
        lambda match: match.group(0) if match.group(1) else "\\\\", raw
    )
# A valid JSON escape that almost certainly began a LaTeX command:
# "\frac" decodes to form-feed + "rac", "\theta" to tab + "heta".
_LATEX_DAMAGE = (
    (re.compile("\x0c"), r"\\f"),
    (re.compile("\x08"), r"\\b"),
    (re.compile(r"\t(?=[a-zA-Z]{2,})"), r"\\t"),
    (re.compile(r"\r(?=[a-zA-Z]{2,})"), r"\\r"),
)


class CourseGenerationErrorV01(RuntimeError):
    """The local model did not return usable structured output."""


def decode_model_json_v01(raw: str) -> Any:
    """Parse model JSON, repairing the backslash mistakes small models make."""
    if type(raw) is not str or not raw.strip():
        raise CourseGenerationErrorV01("Empty model output.")
    raw = _strip_fence(raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(_double_invalid_escapes(raw))
        except json.JSONDecodeError as exc:
            raise CourseGenerationErrorV01("Model output is not valid JSON.") from exc
    return _repair_strings(parsed)


def _strip_fence(raw: str) -> str:
    """Small models often wrap JSON in ```json fences or add a sentence around it."""
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    if text[:1] not in "{[":
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if 0 <= start < end:
            return text[start:end + 1]
    return text


def _repair_strings(value: Any) -> Any:
    if isinstance(value, str):
        for pattern, replacement in _LATEX_DAMAGE:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, list):
        return [_repair_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_strings(item) for key, item in value.items()}
    return value


class LocalJsonModelV01:
    """One structured call per generate(); the transport is injectable for tests."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL_V01,
        transport: Callable[[dict], dict] | None = None,
        num_ctx: int = 16384,
    ) -> None:
        if model not in LocalOllamaProfessorGatewayV01.ALLOWED_MODELS:
            raise ValueError("Unsupported local model.")
        self.model = model
        self._transport = transport or LocalOllamaProfessorGatewayV01._post_local
        self._num_ctx = num_ctx

    def generate(
        self, *, system: str, user: str, schema: dict, max_tokens: int = 2048
    ) -> Any:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema,
            "think": False,
            "options": {
                "temperature": 0,
                "num_ctx": self._num_ctx,
                "num_predict": max_tokens,
            },
            "keep_alive": "5m",
        }
        try:
            response = self._transport(payload)
        except LocalProfessorGenerationErrorV01 as exc:
            raise CourseGenerationErrorV01("Local model request failed.") from exc
        if (
            type(response) is not dict
            or response.get("done") is not True
            or response.get("done_reason") != "stop"
        ):
            raise CourseGenerationErrorV01("Local model did not finish normally.")
        message = response.get("message")
        if type(message) is not dict or type(message.get("content")) is not str:
            raise CourseGenerationErrorV01("Local model returned no content.")
        return decode_model_json_v01(message["content"])

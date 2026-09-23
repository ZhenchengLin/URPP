"""
URPP 14C-6C1 offline provider tests.

Fake Responses API client only.
No API key, network request, real model inference, database,
student account, or student-facing delivery.
"""

import json
from types import SimpleNamespace

import pytest

from app.llm.openai_structured_gateway_v01 import (
    OpenAIStructuredProfessorGatewayV01,
    ProfessorProviderResponseErrorV01,
)


PROMPT = "urpp-course-grounded-professor-v0.1"

PAYLOAD = {
    "contract_version": "structured-professor-v0.1",
    "instructions": "Synthetic test instructions.",
    "objective": {
        "course_id": "synthetic-course",
        "objective_id": "synthetic-objective",
        "description": "Explain a synthetic factorization.",
    },
    "teaching_action": "conceptual_review",
    "student_request_kind": "request_explanation",
    "sources": [
        {
            "source_id": "synthetic-source",
            "source_revision": "revision-1",
            "source_locator": "synthetic:section-1",
            "content": "A synthetic example about factors.",
        },
    ],
}

VALID_OUTPUT = {
    "content": "A short synthetic explanation.",
    "source_ids": ["synthetic-source"],
}


class FakeResponses:

    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:

    def __init__(self, response):
        self.responses = FakeResponses(response)


def make_response(
    *,
    status="completed",
    output_text=None,
):
    if output_text is None:
        output_text = json.dumps(VALID_OUTPUT)

    return SimpleNamespace(
        status=status,
        output_text=output_text,
    )


def make_gateway(response=None):
    if response is None:
        response = make_response()

    client = FakeClient(response)

    gateway = OpenAIStructuredProfessorGatewayV01(
        client=client,
        model="synthetic-model",
    )

    return gateway, client


def generate(gateway, *, payload=None, prompt_name=PROMPT):
    return gateway.generate_structured(
        prompt_name=prompt_name,
        payload=PAYLOAD if payload is None else payload,
    )


def test_sync_responses_api_contract():
    gateway, client = make_gateway()

    result = generate(gateway)

    assert result == VALID_OUTPUT
    assert len(client.responses.calls) == 1

    call = client.responses.calls[0]

    assert call["model"] == "synthetic-model"
    assert call["store"] is False

    assert call["max_output_tokens"] == 1500

    assert call["input"][0]["role"] == "system"
    assert call["input"][1]["role"] == "user"

    sent_payload = json.loads(
        call["input"][1]["content"]
    )

    assert sent_payload == PAYLOAD
    assert "student_id" not in sent_payload

    format_spec = call["text"]["format"]

    assert format_spec["type"] == "json_schema"
    assert format_spec["strict"] is True

    schema = format_spec["schema"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "content",
        "source_ids",
    }


@pytest.mark.parametrize(
    "status",
    [
        "failed",
        "incomplete",
        "cancelled",
        "in_progress",
        None,
    ],
)
def test_noncompleted_response_fails_closed(status):
    gateway, client = make_gateway(
        make_response(status=status)
    )

    with pytest.raises(
        ProfessorProviderResponseErrorV01,
        match="not completed",
    ):
        generate(gateway)

    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "output_text",
    [
        "",
        "   ",
        "not-json",
        "[]",
        "null",
        '{"content":"one","content":"two","source_ids":[]}',
        '{"content":NaN,"source_ids":[]}',
        "X" * 20001,
    ],
)
def test_invalid_provider_output_fails_closed(output_text):
    gateway, client = make_gateway(
        make_response(output_text=output_text)
    )

    with pytest.raises(
        ProfessorProviderResponseErrorV01
    ):
        generate(gateway)

    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    "bad_payload",
    [
        {},
        {
            **PAYLOAD,
            "contract_version": "unsupported-version",
        },
        {
            **PAYLOAD,
            "student_id": "client-supplied-student",
        },
        {
            **PAYLOAD,
            "sources": object(),
        },
    ],
)
def test_bad_payload_rejected_before_api_call(bad_payload):
    gateway, client = make_gateway()

    with pytest.raises((TypeError, ValueError)):
        generate(
            gateway,
            payload=bad_payload,
        )

    assert client.responses.calls == []


def test_wrong_prompt_rejected_before_api_call():
    gateway, client = make_gateway()

    with pytest.raises(
        ValueError,
        match="Unsupported Professor prompt",
    ):
        generate(
            gateway,
            prompt_name="arbitrary-prompt",
        )

    assert client.responses.calls == []


def test_async_client_rejected():
    class AsyncResponses:

        async def create(self, **kwargs):
            return make_response()

    class AsyncClient:
        responses = AsyncResponses()

    with pytest.raises(
        TypeError,
        match="must use synchronous",
    ):
        OpenAIStructuredProfessorGatewayV01(
            client=AsyncClient(),
            model="synthetic-model",
        )


def test_environment_factory_rejects_missing_key(monkeypatch):
    monkeypatch.delenv(
        "OPENAI_API_KEY",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="OPENAI_API_KEY is not configured",
    ):
        OpenAIStructuredProfessorGatewayV01.from_environment(
            model="synthetic-model",
        )


def test_sdk_not_imported_by_fake_client_path():
    gateway, client = make_gateway()

    assert generate(gateway) == VALID_OUTPUT

    assert len(client.responses.calls) == 1

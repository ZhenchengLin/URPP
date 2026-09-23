"""
URPP 14C-6C2-L2 offline gateway tests.

All inputs and model responses are synthetic.
No local Ollama request or real inference is performed.
"""

import json

import pytest

from app.llm.local_ollama_professor_gateway_v01 import (
    LocalOllamaProfessorGatewayV01,
    LocalProfessorGenerationErrorV01,
)


PROMPT = "urpp-course-grounded-professor-v0.1"

SOURCE = "synthetic-source"

PAYLOAD = {
    "contract_version": "structured-professor-v0.1",
    "instructions": "Synthetic teaching instructions.",
    "objective": {
        "course_id": "synthetic-course",
        "objective_id": "synthetic-objective",
        "description": "Explain a synthetic matrix factorization.",
    },
    "teaching_action": "conceptual_review",
    "student_request_kind": "request_explanation",
    "sources": [
        {
            "source_id": SOURCE,
            "source_revision": "revision-1",
            "source_locator": "synthetic:section-1",
            "content": "A synthetic example about matrix factors.",
        },
    ],
}

VALID_OUTPUT = {
    "content": "A short synthetic explanation.",
    "source_ids": [SOURCE],
}


def make_response(
    output=None,
    *,
    done=True,
    done_reason="stop",
):

    if output is None:
        output = VALID_OUTPUT

    return {
        "model": "qwen3.5:4b",
        "done": done,
        "done_reason": done_reason,
        "message": {
            "role": "assistant",
            "content": json.dumps(output),
        },
    }


class FakeTransport:

    def __init__(self, response=None):

        self.calls = []

        self.response = (
            make_response()
            if response is None
            else response
        )

    def __call__(self, request):

        self.calls.append(request)

        return self.response


def make_gateway(response=None):

    transport = FakeTransport(response)

    gateway = LocalOllamaProfessorGatewayV01(
        model="qwen3.5:4b",
        transport=transport,
    )

    return gateway, transport


def generate(
    gateway,
    *,
    payload=None,
    prompt_name=PROMPT,
):

    return gateway.generate_structured(
        prompt_name=prompt_name,
        payload=PAYLOAD if payload is None else payload,
    )


def test_local_gateway_request_contract():

    gateway, transport = make_gateway()

    result = generate(gateway)

    assert result == VALID_OUTPUT

    assert len(transport.calls) == 1

    request = transport.calls[0]

    assert request["model"] == "qwen3.5:4b"

    assert request["stream"] is False

    assert request["think"] is False

    assert request["format"]["additionalProperties"] is False

    assert set(request["format"]["required"]) == {
        "content",
        "source_ids",
    }

    assert request["options"]["temperature"] == 0

    assert request["keep_alive"] == "0"

    assert request["messages"][0]["role"] == "system"

    assert request["messages"][1]["role"] == "user"

    assert json.loads(
        request["messages"][1]["content"]
    ) == PAYLOAD


@pytest.mark.parametrize(
    "model",
    [
        "",
        "unknown-model",
        "qwen3.5:4b-cloud",
        None,
    ],
)
def test_unregistered_model_rejected(model):

    with pytest.raises(ValueError):

        LocalOllamaProfessorGatewayV01(
            model=model,
            transport=FakeTransport(),
        )


@pytest.mark.parametrize(
    "bad_payload",
    [
        {},
        {
            **PAYLOAD,
            "contract_version": "wrong-version",
        },
        {
            **PAYLOAD,
            "student_id": "client-supplied",
        },
        {
            **PAYLOAD,
            "sources": [],
        },
        {
            **PAYLOAD,
            "sources": [
                {
                    "source_id": SOURCE,
                    "content": "Incomplete source.",
                }
            ],
        },
    ],
)
def test_invalid_payload_rejected_before_transport(bad_payload):

    gateway, transport = make_gateway()

    with pytest.raises((TypeError, ValueError)):

        generate(
            gateway,
            payload=bad_payload,
        )

    assert transport.calls == []


def test_wrong_prompt_rejected_before_transport():

    gateway, transport = make_gateway()

    with pytest.raises(ValueError):

        generate(
            gateway,
            prompt_name="unknown-prompt",
        )

    assert transport.calls == []


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"done": False},
        make_response(done=False),
        make_response(done_reason="length"),
        make_response(done_reason=None),
        {
            **make_response(),
            "message": {
                "role": "user",
                "content": "{}",
            },
        },
        {
            **make_response(),
            "message": {
                "role": "assistant",
                "content": "",
            },
        },
        {
            **make_response(),
            "message": {
                "role": "assistant",
                "content": "not-json",
            },
        },
        {
            **make_response(),
            "message": {
                "role": "assistant",
                "content": "[]",
            },
        },
        {
            **make_response(),
            "message": {
                "role": "assistant",
                "content": (
                    '{"content":"one","content":"two",'
                    '"source_ids":[]}'
                ),
            },
        },
        {
            **make_response(),
            "message": {
                "role": "assistant",
                "content": (
                    '{"content":NaN,"source_ids":[]}'
                ),
            },
        },
        make_response({
            "content": "Some content.",
            "source_ids": [SOURCE],
            "authorized": True,
        }),
    ],
)
def test_invalid_response_fails_closed(response):

    gateway, transport = make_gateway(response)

    with pytest.raises(
        LocalProfessorGenerationErrorV01
    ):

        generate(gateway)

    assert len(transport.calls) == 1


def test_fake_transport_requires_no_local_server():

    gateway, transport = make_gateway()

    result = generate(gateway)

    assert result["source_ids"] == [SOURCE]

    assert len(transport.calls) == 1


def test_async_transport_rejected():

    async def async_transport(request):

        return make_response()

    with pytest.raises(
        TypeError,
        match="must be synchronous",
    ):

        LocalOllamaProfessorGatewayV01(
            transport=async_transport,
        )

from typing import Protocol


class LLMClient(Protocol):
    """
    Provider-neutral LLM boundary.
    """

    async def generate_json(
        self,
        *,
        prompt_name: str,
        payload: dict,
    ) -> dict:
        ...

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...

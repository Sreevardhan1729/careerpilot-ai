from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient(Protocol):
    model: str

    async def complete(self, messages: list[dict[str, str]], *, prompt_id: str, json_mode: bool,
                       json_schema: dict[str, Any] | None = None) -> LLMResponse: ...

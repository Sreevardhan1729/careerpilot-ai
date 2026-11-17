"""Deterministic fake LLM for tests only (LLM_PROVIDER=fake is rejected in production)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.integrations.llm.base import LLMResponse

Responder = str | Callable[[list[dict[str, str]]], str]


class FakeLLMClient:
    model = "fake-llm"

    def __init__(self) -> None:
        self.responses: dict[str, list[Responder]] = defaultdict(list)
        self.calls: list[dict[str, Any]] = []

    def queue(self, prompt_id: str, *responses: Responder) -> None:
        self.responses[prompt_id].extend(responses)

    async def complete(self, messages: list[dict[str, str]], *, prompt_id: str, json_mode: bool,
                       json_schema: dict[str, Any] | None = None) -> LLMResponse:
        self.calls.append({"prompt_id": prompt_id, "messages": messages})
        queue = self.responses.get(prompt_id) or []
        if not queue:
            raise AssertionError(f"FakeLLMClient: no response queued for {prompt_id}")
        r = queue.pop(0) if len(queue) > 1 else queue[0]
        return LLMResponse(text=r(messages) if callable(r) else r, model=self.model, prompt_tokens=10, completion_tokens=10)

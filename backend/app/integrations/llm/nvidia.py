"""NVIDIA inference endpoint (OpenAI-compatible) via langchain-nvidia-ai-endpoints."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from app.core.errors import LLMUnavailable, UpstreamError
from app.integrations.llm.base import LLMResponse

_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "timeout", "timed out", "rate limit", "connection")


class NvidiaLLMClient:
    def __init__(self, model: str, api_key: str, base_url: str, temperature: float, timeout: int, max_retries: int):
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        self.model = model
        self.max_retries = max_retries
        self._chat = ChatNVIDIA(model=model, api_key=api_key, base_url=base_url, temperature=temperature,
                                max_completion_tokens=4096, timeout=timeout)

    async def complete(self, messages: list[dict[str, str]], *, prompt_id: str, json_mode: bool,
                       json_schema: dict[str, Any] | None = None) -> LLMResponse:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc = []
        for m in messages:
            cls = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}[m["role"]]
            lc.append(cls(content=m["content"]))
        chat = self._chat.bind(response_format={"type": "json_object"}) if json_mode else self._chat
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                msg = await chat.ainvoke(lc)
                usage = getattr(msg, "usage_metadata", None) or {}
                return LLMResponse(text=str(msg.content), model=self.model,
                                   prompt_tokens=usage.get("input_tokens"), completion_tokens=usage.get("output_tokens"))
            except Exception as exc:  # provider SDKs raise many types
                last = exc
                text = str(exc).lower()
                if not any(marker in text for marker in _TRANSIENT_MARKERS) or attempt == self.max_retries:
                    break
                await asyncio.sleep(min(30.0, 2 ** attempt) * (0.8 + 0.4 * random.random()))
        if last and any(marker in str(last).lower() for marker in _TRANSIENT_MARKERS):
            raise LLMUnavailable("The LLM provider is unavailable.", details={"error": str(last)[:300]})
        raise UpstreamError("The LLM provider returned an error.", details={"error": str(last)[:300]})

"""Structured LLM calls with caching, budget, single repair attempt and call logging (docs/AGENT_DESIGN.md §2.3)."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import system_session
from app.core.errors import InvalidLLMOutput, LLMQuotaExhausted, LLMUnavailable
from app.core.logging import get_logger
from app.domain.text import sha256_hex
from app.integrations.llm.base import LLMClient
from app.integrations.llm.prompts import get_prompt
from app.models import LLMCall

T = TypeVar("T", bound=BaseModel)
log = get_logger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_client: LLMClient | None = None
_semaphore: asyncio.Semaphore | None = None


def set_llm_client(client: LLMClient | None) -> None:
    """Override the provider (tests)."""
    global _client
    _client = client


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        s = get_settings()
        if s.llm_provider == "nvidia":
            from app.integrations.llm.nvidia import NvidiaLLMClient

            assert s.nvidia_api_key
            _client = NvidiaLLMClient(s.nvidia_model, s.nvidia_api_key.get_secret_value(), s.nvidia_base_url,
                                      s.llm_temperature, s.llm_timeout_seconds, s.llm_max_retries)
        elif s.llm_provider == "fake":
            from app.integrations.llm.fake import FakeLLMClient

            _client = FakeLLMClient()
        else:
            raise LLMUnavailable("No LLM provider is configured (LLM_PROVIDER=none).")
    return _client


def llm_enabled() -> bool:
    return get_settings().llm_enabled or _client is not None


def extract_json(text: str) -> Any:
    cleaned = _THINK.sub("", text).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("No JSON object found in model output.")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(cleaned[start:])
    return obj


@dataclass
class StructuredResult[T]:
    value: T
    model_id: str
    prompt_ref: str
    cached: bool


async def _record(**fields: Any) -> None:
    async with system_session() as s:
        s.add(LLMCall(**fields))


async def _used_today(user_id: uuid.UUID | None) -> int:
    if user_id is None:
        return 0
    since = datetime.now(tz=UTC) - timedelta(hours=24)
    async with system_session() as s:
        return int((await s.execute(
            select(func.count()).select_from(LLMCall).where(
                LLMCall.user_id == user_id, LLMCall.created_at >= since, LLMCall.status != "cache_hit")
        )).scalar_one())


async def structured(
    prompt_id: str,
    output_model: type[T],
    *,
    variables: dict[str, Any],
    untrusted: dict[str, str],
    user_id: uuid.UUID | None,
    agent_run_id: uuid.UUID | None = None,
    node: str | None = None,
    version: int | None = None,
) -> StructuredResult[T]:
    global _semaphore
    settings = get_settings()
    client = get_llm_client()
    prompt = get_prompt(prompt_id, version)
    schema = output_model.model_json_schema()
    messages = prompt.render(variables, untrusted, json.dumps(schema, separators=(",", ":")))
    input_hash = sha256_hex(json.dumps({"m": client.model, "p": prompt.ref, "msg": messages}, sort_keys=True))
    base = {"user_id": user_id, "agent_run_id": agent_run_id, "node": node, "prompt_id": prompt.id,
            "prompt_version": f"v{prompt.version}", "model_id": client.model, "input_hash": input_hash}

    async with system_session() as s:
        cached = (await s.execute(
            select(LLMCall.output).where(LLMCall.input_hash == input_hash, LLMCall.status.in_(("ok", "repaired")),
                                         LLMCall.output.is_not(None))
            .order_by(LLMCall.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if cached is not None:
        try:
            value = output_model.model_validate(cached)
            await _record(**base, status="cache_hit", output=None)
            return StructuredResult(value, client.model, prompt.ref, True)
        except ValidationError:
            pass

    if await _used_today(user_id) >= settings.llm_daily_call_budget:
        raise LLMQuotaExhausted()

    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
    json_mode = settings.llm_structured_output_mode == "native"
    started = time.monotonic()
    async with _semaphore:
        resp = await client.complete(messages, prompt_id=prompt.id, json_mode=json_mode, json_schema=schema)
        try:
            value = output_model.model_validate(extract_json(resp.text))
            status = "ok"
        except (ValueError, ValidationError) as first_error:
            repair = messages + [
                {"role": "assistant", "content": resp.text[:8000]},
                {"role": "user", "content": "Your previous reply did not validate against the schema. Errors:\n"
                 f"{str(first_error)[:2000]}\nReturn only the corrected JSON object, with no other text."},
            ]
            resp = await client.complete(repair, prompt_id=prompt.id, json_mode=json_mode, json_schema=schema)
            try:
                value = output_model.model_validate(extract_json(resp.text))
                status = "repaired"
            except (ValueError, ValidationError) as second_error:
                await _record(**base, status="invalid_output", latency_ms=int((time.monotonic() - started) * 1000),
                              error={"message": str(second_error)[:2000]})
                raise InvalidLLMOutput(details={"prompt": prompt.ref}) from second_error
    await _record(**base, status=status, prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
                  latency_ms=int((time.monotonic() - started) * 1000), output=value.model_dump(mode="json"))
    log.info("llm_call", prompt=prompt.ref, model=client.model, status=status, node=node)
    return StructuredResult(value, client.model, prompt.ref, False)

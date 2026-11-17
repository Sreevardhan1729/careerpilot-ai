"""Verify the NVIDIA endpoint, list models, and probe structured output (spec §5.4: never assume a model id).

    uv run python -m scripts.check_llm            # uses NVIDIA_API_KEY / NVIDIA_BASE_URL / NVIDIA_MODEL from backend/.env
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings  # noqa: E402


async def main() -> int:
    try:
        s = Settings(llm_provider="none", embedding_provider="hashing")
    except Exception as exc:
        print(f"Settings error: {exc}")
        return 2
    key = s.nvidia_api_key.get_secret_value() if s.nvidia_api_key else ""
    if not key:
        print("NVIDIA_API_KEY is not set in backend/.env — the app runs in rule-based mode until you add one.")
        return 1
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(s.nvidia_base_url.rstrip("/") + "/models", headers=headers)
        if r.status_code != 200:
            print(f"GET /models failed: HTTP {r.status_code} {r.text[:200]}")
            return 1
        models = sorted(m["id"] for m in r.json().get("data", []))
        nemotron = [m for m in models if "nemotron" in m.lower()]
        embed = [m for m in models if "embed" in m.lower()]
        print(f"{len(models)} models available. Nemotron chat candidates:")
        for m in nemotron:
            print("  -", m)
        print("Embedding candidates:", ", ".join(embed[:10]) or "(none listed)")
        model = s.nvidia_model or (nemotron[0] if nemotron else None)
        if not model:
            print("Set NVIDIA_MODEL to one of the ids above.")
            return 1
        probe = {"model": model, "temperature": 0, "max_tokens": 200, "messages": [
            {"role": "system", "content": "Reply with JSON only."},
            {"role": "user", "content": 'Return {"ok": true, "skills": ["Python"]} exactly.'}]}
        results = {}
        for mode, extra in (("prompt", {}), ("native", {"response_format": {"type": "json_object"}})):
            resp = await client.post(s.nvidia_base_url.rstrip("/") + "/chat/completions", headers=headers, json={**probe, **extra})
            if resp.status_code != 200:
                results[mode] = f"HTTP {resp.status_code}"
                continue
            content = resp.json()["choices"][0]["message"]["content"] or ""
            if "<think>" in content:
                content = content.split("</think>")[-1]
            try:
                json.loads(content.strip().strip("`").removeprefix("json"))
                results[mode] = "ok"
            except ValueError:
                results[mode] = "invalid JSON"
        print(f"Model {model}: structured output probe → {results}")
        best = "native" if results.get("native") == "ok" else "prompt"
        print(f"\nSet in backend/.env:\n  LLM_PROVIDER=nvidia\n  NVIDIA_MODEL={model}\n  LLM_STRUCTURED_OUTPUT_MODE={best}")
        if embed:
            print(f"  EMBEDDING_PROVIDER=nvidia\n  NVIDIA_EMBEDDING_MODEL={embed[0]}   # then set EMBEDDING_DIMENSIONS to its size before migrating")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

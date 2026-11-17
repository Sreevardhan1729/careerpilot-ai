"""Embedding providers: local feature hashing (default, no key) or NVIDIA (EMBEDDING_PROVIDER=nvidia)."""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import Counter
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import UpstreamError

_STOP = set(
    "a an and are as at be by for from has have in is it its of on or our that the their this to was we were will with "
    "you your they them i me my he she his her not but if into than then so such can could should would also etc".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*[a-z0-9+#]|[a-z0-9]")


class EmbeddingClient(Protocol):
    model: str
    provider: str
    dimensions: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class HashingEmbeddings:
    """Deterministic bag-of-features vectors (unigrams, bigrams, canonical skills) via signed feature hashing.

    Not semantic like a neural model, but stable, offline, and good at lexical/skill overlap. Similarity scale
    for this provider is calibrated separately in scoring_config.yaml.
    """

    provider = "hashing"

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        self.model = f"hashing-v1-{dimensions}"

    def _features(self, text: str) -> Counter[str]:
        from app.domain.skills import get_taxonomy

        low = text.lower()
        tokens = [t for t in _TOKEN.findall(low) if t not in _STOP]
        feats: Counter[str] = Counter(tokens)
        feats.update(f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False))
        for entry in get_taxonomy().skills_in(text):
            feats[f"skill:{entry.slug}"] += 2
        return feats

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for feat, tf in self._features(text).items():
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            idx = h % self.dimensions
            sign = 1.0 if (h >> 63) & 1 else -1.0
            vec[idx] += sign * (1.0 + math.log(tf))
        norm = math.sqrt(sum(v * v for v in vec))
        return [round(v / norm, 6) for v in vec] if norm else vec

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class NvidiaEmbeddings:
    provider = "nvidia"

    def __init__(self, model: str, api_key: str, base_url: str, dimensions: int):
        from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

        self.model = model
        self.dimensions = dimensions
        self._client = NVIDIAEmbeddings(model=model, api_key=api_key, base_url=base_url, truncate="END")

    def _check(self, vectors: list[list[float]]) -> list[list[float]]:
        for v in vectors:
            if len(v) != self.dimensions:
                raise UpstreamError(
                    f"Embedding model returned {len(v)} dims; EMBEDDING_DIMENSIONS is {self.dimensions}.")
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._check(await asyncio.to_thread(self._client.embed_documents, texts))

    async def embed_query(self, text: str) -> list[float]:
        return self._check([await asyncio.to_thread(self._client.embed_query, text)])[0]


@lru_cache
def get_embeddings() -> EmbeddingClient:
    s = get_settings()
    if s.embedding_provider == "nvidia":
        assert s.nvidia_api_key
        return NvidiaEmbeddings(s.nvidia_embedding_model, s.nvidia_api_key.get_secret_value(), s.nvidia_base_url,
                                s.embedding_dimensions)
    return HashingEmbeddings(s.embedding_dimensions)

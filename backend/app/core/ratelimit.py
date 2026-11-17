"""In-process token-bucket rate limiter (single API instance; docs/API_SPEC.md §1.7)."""

from __future__ import annotations

import math
import threading
import time

from app.core.errors import RateLimited


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, bucket: str, capacity: int, per_seconds: float) -> None:
        if capacity <= 0:
            return
        rate = capacity / per_seconds
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get((key, bucket), (float(capacity), now))
            tokens = min(float(capacity), tokens + (now - last) * rate)
            if tokens < 1:
                raise RateLimited(retry_after=max(1, math.ceil((1 - tokens) / rate)))
            self._buckets[(key, bucket)] = (tokens - 1, now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = RateLimiter()

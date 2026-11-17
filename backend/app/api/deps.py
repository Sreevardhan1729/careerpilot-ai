"""FastAPI dependencies: auth, rate limits, idempotency header, request ids."""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Callable

from fastapi import Depends, Header, Request

from app.core.config import get_settings
from app.core.errors import Unauthorized
from app.core.ratelimit import limiter
from app.core.security import Principal, verify_token
from app.services.users import ensure_user

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_known_users: set[uuid.UUID] = set()


async def get_principal(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized()
    principal = verify_token(authorization.split(" ", 1)[1].strip())
    if principal.user_id not in _known_users:
        await ensure_user(principal)
        _known_users.add(principal.user_id)
    request.state.user_id = principal.user_id
    limiter.hit(str(principal.user_id), "default", get_settings().rate_limit_default_per_minute, 60)
    return principal


def rate_limit(bucket: str, capacity: int | None = None, per_seconds: float = 3600) -> Callable:
    async def dep(principal: Principal = Depends(get_principal)) -> Principal:
        cap = capacity if capacity is not None else get_settings().rate_limit_llm_enqueue_per_hour
        limiter.hit(str(principal.user_id), bucket, cap, per_seconds)
        return principal

    return dep


def idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str | None:
    return idempotency_key[:200] if idempotency_key else None


def forget_user(user_id: uuid.UUID) -> None:
    _known_users.discard(user_id)

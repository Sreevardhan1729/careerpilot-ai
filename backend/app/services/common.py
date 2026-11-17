"""Shared service helpers: ownership lookups, audit, pagination cursors, idempotency."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import IdempotencyConflict, NotFound
from app.domain.text import sha256_hex
from app.models import AuditEvent, IdempotencyKey

M = TypeVar("M")


async def get_owned(session: AsyncSession, model: type[M], obj_id: uuid.UUID | str, user_id: uuid.UUID) -> M:
    """Fetch a user-owned row or raise 404 (never 403, so ids can't be probed)."""
    try:
        oid = uuid.UUID(str(obj_id))
    except ValueError as exc:
        raise NotFound() from exc
    obj = (await session.execute(select(model).where(model.id == oid, model.user_id == user_id))).scalar_one_or_none()  # type: ignore[attr-defined]
    if obj is None:
        raise NotFound()
    return obj


async def audit(session: AsyncSession, user_id: uuid.UUID | None, action: str, target_type: str | None = None,
                target_id: uuid.UUID | None = None, actor: str = "user", request_id: str | None = None,
                **metadata: Any) -> None:
    session.add(AuditEvent(user_id=user_id, actor=actor, action=action, target_type=target_type, target_id=target_id,
                           metadata_=metadata, request_id=request_id))


def encode_cursor(values: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode()


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, json.JSONDecodeError):
        return None


def request_hash(body: Any) -> str:
    return sha256_hex(json.dumps(body, sort_keys=True, default=str))


async def idempotent_lookup(session: AsyncSession, user_id: uuid.UUID, key: str | None, endpoint: str,
                            body_hash: str) -> tuple[int, Any] | None:
    if not key:
        return None
    row = await session.get(IdempotencyKey, (user_id, key))
    if row is None or row.expires_at < datetime.now(tz=UTC):
        return None
    if row.request_hash != body_hash or row.endpoint != endpoint:
        raise IdempotencyConflict()
    return (row.response_status or 200, row.response_body)


async def idempotent_store(session: AsyncSession, user_id: uuid.UUID, key: str | None, endpoint: str, body_hash: str,
                           status: int, response: Any) -> None:
    if not key:
        return
    existing = await session.get(IdempotencyKey, (user_id, key))
    if existing:
        await session.delete(existing)
        await session.flush()
    session.add(IdempotencyKey(user_id=user_id, key=key, endpoint=endpoint, request_hash=body_hash, response_status=status,
                               response_body=json.loads(json.dumps(response, default=str)),
                               expires_at=datetime.now(tz=UTC) + timedelta(hours=24)))

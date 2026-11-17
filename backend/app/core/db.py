"""Database engine and sessions.

Two session kinds (docs/ARCHITECTURE.md §4):
- system_session(): the backend login role (migrations, task queue, shared tables).
- user_session(user_id): every transaction runs `SET LOCAL ROLE authenticated` with the caller's JWT
  claims, so Postgres RLS (`user_id = auth.uid()`) applies even if a query forgets its filter.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_resolved_url: str | None = None

RLS_USER_KEY = "rls_user_id"


def resolve_database_url(settings: Settings | None = None) -> str:
    global _resolved_url
    if _resolved_url:
        return _resolved_url
    settings = settings or get_settings()
    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.split("://", 1)[1]
    elif settings.app_env in ("local", "test"):
        from app.core.embedded_db import ensure_embedded_database

        url = ensure_embedded_database(settings.embedded_pg_dir, "careerpilot")
    else:
        raise RuntimeError("DATABASE_URL is required outside local/test")
    _resolved_url = url
    return url


def set_database_url(url: str) -> None:
    """Override the resolved URL (tests)."""
    global _resolved_url, _engine, _sessionmaker
    _resolved_url = url
    _engine = None
    _sessionmaker = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            resolve_database_url(settings),
            pool_size=settings.db_pool_size,
            max_overflow=2,
            pool_pre_ping=True,
            # Supabase poolers don't support server-side prepared statements reliably.
            connect_args={"prepare_threshold": None},
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


@event.listens_for(Session, "after_begin")
def _apply_rls_claims(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    user_id = session.info.get(RLS_USER_KEY)
    if not user_id:
        return
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"})
    connection.exec_driver_sql("SET LOCAL ROLE authenticated")
    connection.exec_driver_sql("SELECT set_config('request.jwt.claims', %s, true)", (claims,))


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


@asynccontextmanager
async def user_session(user_id: uuid.UUID | str) -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()(info={RLS_USER_KEY: str(user_id)}) as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def session_user_id(session: AsyncSession) -> str | None:
    value: Any = session.info.get(RLS_USER_KEY)
    return str(value) if value else None

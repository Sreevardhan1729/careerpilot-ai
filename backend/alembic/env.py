"""Alembic environment (async, psycopg). URL comes from app settings (embedded Postgres if unset locally)."""

import asyncio

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.db import resolve_database_url
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    # LangGraph checkpoint tables live in schema "langgraph" and are not managed here.
    return not (type_ == "table" and getattr(obj, "schema", None) == "langgraph")


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    url = config.attributes.get("database_url") or resolve_database_url()
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args={"prepare_threshold": None})
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
    else:
        asyncio.run(_run_async())


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported; run against a database.")
run_migrations_online()

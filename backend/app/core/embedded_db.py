"""Embedded PostgreSQL 16 + pgvector for local/test use when DATABASE_URL is not set.

Uses the `pgserver` package (Postgres binaries shipped as a Python wheel), so no system database,
Docker, or Supabase project is needed for development. Never used in production.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import psycopg

_servers: dict[str, Any] = {}
_lock = threading.Lock()


def _to_sqlalchemy_url(libpq_uri: str, dbname: str) -> str:
    # pgserver returns e.g. postgresql://postgres:@/postgres?host=/tmp/xyz
    head, _, query = libpq_uri.partition("?")
    base = head.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+psycopg://', 1)}/{dbname}?{query}"


def ensure_embedded_database(pgdata: Path, dbname: str, cleanup_mode: str | None = "stop") -> str:
    """Start (or reuse) an embedded server in `pgdata` and make sure `dbname` exists."""
    import pgserver  # imported lazily: optional at runtime in production images

    key = str(pgdata.resolve())
    with _lock:
        srv = _servers.get(key)
        if srv is None:
            pgdata.mkdir(parents=True, exist_ok=True)
            srv = pgserver.get_server(pgdata, cleanup_mode=cleanup_mode)
            _servers[key] = srv
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')
    return _to_sqlalchemy_url(uri, dbname)


def drop_embedded_database(pgdata: Path, dbname: str) -> None:
    srv = _servers.get(str(pgdata.resolve()))
    if srv is None:
        return
    with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')

"""Run `alembic upgrade head` while holding a Postgres advisory lock (safe for concurrent container starts)."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.db import resolve_database_url  # noqa: E402

LOCK_ID = 727172


def main() -> int:
    url = resolve_database_url().replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            env = {**os.environ, "DATABASE_URL": resolve_database_url()}
            return subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env).returncode
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    sys.exit(main())

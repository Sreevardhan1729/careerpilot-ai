"""Test harness: embedded Postgres per session, real migrations, dev auth, no LLM, local storage."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="careerpilot-test-"))
os.environ.update({
    "APP_ENV": "test", "AUTH_MODE": "dev", "STORAGE_BACKEND": "local", "LOCAL_STORAGE_DIR": str(_TMP / "storage"),
    "LLM_PROVIDER": "none", "EMBEDDING_PROVIDER": "hashing", "TASK_RUNNER_ENABLED": "false", "SEARCH_PROVIDER": "none",
    "RATE_LIMIT_DEFAULT_PER_MINUTE": "10000", "RATE_LIMIT_LLM_ENQUEUE_PER_HOUR": "10000", "DATABASE_URL": "",
    "TOKEN_ENCRYPTION_KEYS": "", "CHECKPOINTER": "memory",
})

import httpx  # noqa: E402
import pytest  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def database_url() -> str:
    from app.core.embedded_db import ensure_embedded_database

    url = ensure_embedded_database(_TMP / "pg", f"test_{uuid.uuid4().hex[:8]}", cleanup_mode="delete")
    env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(BACKEND)}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-3000:]
    return url


@pytest.fixture(scope="session")
async def app(database_url):
    from app.core.db import set_database_url

    set_database_url(database_url)
    from app.graphs import register_all
    from app.main import create_app
    from app.services.seed import seed_taxonomy

    register_all()
    await seed_taxonomy()
    yield create_app()
    from app.core.db import dispose_engine

    await dispose_engine()


@pytest.fixture
async def client(app):
    from app.core.ratelimit import limiter

    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture
def auth():
    from app.core.security import issue_dev_token

    def make(email: str | None = None) -> dict[str, str]:
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        return {"Authorization": f"Bearer {issue_dev_token(email)}"}

    return make


@pytest.fixture
def run_tasks():
    from app.tasks.runner import TaskRunner

    async def go(max_tasks: int = 50) -> int:
        return await TaskRunner(concurrency=1, poll_seconds=0, lease_seconds=60).run_until_empty(max_tasks=max_tasks)

    return go


def make_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for line in text.split("\n"):
        if y > 800:
            page, y = doc.new_page(), 50
        page.insert_text((40, y), line, fontsize=9)
        y += 13
    return doc.tobytes()


def make_docx(text: str) -> bytes:
    import io

    import docx

    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES

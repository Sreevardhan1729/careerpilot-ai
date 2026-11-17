from __future__ import annotations

import uuid
from typing import Any

from app.core.db import user_session
from app.models import Notification


async def notify(user_id: uuid.UUID, type_: str, title: str, body: str | None = None, link: str | None = None) -> None:
    async with user_session(user_id) as s:
        s.add(Notification(user_id=user_id, type=type_, title=title[:200], body=(body or "")[:2000] or None, link=link))


async def notify_run_failed(user_id: uuid.UUID, run_id: uuid.UUID, task_type: str, error: dict[str, Any]) -> None:
    await notify(user_id, "run_failed", f"{task_type.replace('_', ' ').capitalize()} failed",
                 error.get("message"), f"/runs/{run_id}")

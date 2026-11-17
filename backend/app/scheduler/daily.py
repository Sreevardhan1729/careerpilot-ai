"""Daily worker entry point (GitHub Actions cron; spec §10.2). Usage:

    python -m app.scheduler.daily [--date YYYY-MM-DD] [--time-budget-minutes 100] [--email you@example.com]

Creates (idempotently) one daily_pipeline task per user with an active search config, then drains the queue for
those users within the time budget. Exit code 1 if any pipeline failed (GitHub emails a failure alert).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import dispose_engine, system_session
from app.core.logging import configure_logging, get_logger
from app.models import AgentRun, SearchConfig, User
from app.tasks import queue
from app.tasks.runner import TaskRunner

log = get_logger("daily")


async def main(run_date: date | None, budget_minutes: float, email: str | None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    from app.graphs import register_all
    from app.services.seed import seed_taxonomy

    register_all()
    await seed_taxonomy()
    day = run_date or __import__("datetime").datetime.now(tz=ZoneInfo(settings.default_timezone)).date()
    async with system_session() as s:
        q = select(User.id).join(SearchConfig, SearchConfig.user_id == User.id).where(SearchConfig.is_active).distinct()
        if email:
            q = q.where(User.email == email.lower())
        user_ids = list((await s.execute(q)).scalars().all())
    run_ids = []
    for uid in user_ids:
        run, _, created = await queue.enqueue(user_id=uid, task_type="daily_pipeline", payload={"date": day.isoformat()}, priority=5,
                                              idempotency_key=f"daily_pipeline:{uid}:{day.isoformat()}", max_attempts=2)
        run_ids.append(run.id)
        log.info("daily_task", user=str(uid), created=created, run=str(run.id))
    processed = await TaskRunner(concurrency=1, poll_seconds=0).run_until_empty(user_ids or None, budget_minutes * 60)
    async with system_session() as s:
        statuses = [r.status for r in (await s.execute(select(AgentRun).where(AgentRun.id.in_(run_ids)))).scalars()]
    await dispose_engine()
    log.info("daily_done", users=len(user_ids), tasks=processed, statuses=statuses)
    return 1 if any(st == "failed" for st in statuses) else 0


def cli() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default="")
    p.add_argument("--time-budget-minutes", type=float, default=100)
    p.add_argument("--email", default=None)
    a = p.parse_args()
    sys.exit(asyncio.run(main(date.fromisoformat(a.date) if a.date else None, a.time_budget_minutes, a.email)))


if __name__ == "__main__":
    cli()

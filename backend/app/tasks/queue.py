"""Durable Postgres task queue with leases (docs/ARCHITECTURE.md §5). System sessions only."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update

from app.core.db import system_session
from app.models import AgentRun, ScheduledTask

WORKFLOW_VERSION = "1"
TASK_WORKFLOWS = {
    "parse_resume": "resume_ingestion",
    "analyze_job": "job_extraction",
    "match_resumes": "resume_matching",
    "discover_jobs": "job_discovery",
    "discover_people": "people_discovery",
    "generate_outreach": "outreach_generation",
    "optimize_resume": "resume_optimization",
    "prepare_application": "application_preparation",
    "daily_pipeline": "daily_pipeline",
    "export_account": "account_export",
}
BACKOFF_BASE_SECONDS = 30


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def enqueue(
    *,
    user_id: uuid.UUID,
    task_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    priority: int = 5,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> tuple[AgentRun, ScheduledTask, bool]:
    """Create (or return the existing) task + agent run. Returns (run, task, created)."""
    key = idempotency_key or f"{task_type}:{uuid.uuid4()}"
    async with system_session() as s:
        existing = (await s.execute(select(ScheduledTask).where(ScheduledTask.idempotency_key == key))).scalar_one_or_none()
        if existing is not None:
            run = await s.get(AgentRun, existing.agent_run_id) if existing.agent_run_id else None
            if run is not None:
                return run, existing, False
        run = AgentRun(user_id=user_id, workflow_name=TASK_WORKFLOWS[task_type], workflow_version=WORKFLOW_VERSION,
                       parent_run_id=parent_run_id, subject_type=subject_type, subject_id=subject_id, status="queued")
        s.add(run)
        await s.flush()
        task = ScheduledTask(user_id=user_id, task_type=task_type, idempotency_key=key, payload=payload, status="queued",
                             priority=priority, run_after=run_after or _now(), agent_run_id=run.id, max_attempts=max_attempts)
        s.add(task)
        await s.flush()
        run.task_id = task.id
        return run, task, True


async def claim(worker_id: str, lease_seconds: int, user_ids: list[uuid.UUID] | None = None) -> ScheduledTask | None:
    user_filter = "AND user_id = ANY(:user_ids)" if user_ids else ""
    sql = text(f"""
        UPDATE scheduled_tasks SET status = 'running', locked_by = :worker, attempts = attempts + 1,
               locked_until = now() + make_interval(secs => :lease)
        WHERE id = (
            SELECT id FROM scheduled_tasks
            WHERE status = 'queued' AND run_after <= now() {user_filter}
            ORDER BY priority, run_after
            FOR UPDATE SKIP LOCKED LIMIT 1)
        RETURNING id
    """)
    params: dict[str, Any] = {"worker": worker_id, "lease": lease_seconds}
    if user_ids:
        params["user_ids"] = list(user_ids)
    async with system_session() as s:
        row = (await s.execute(sql, params)).first()
        if row is None:
            return None
        return await s.get(ScheduledTask, row[0])


async def heartbeat(task_id: uuid.UUID, worker_id: str, lease_seconds: int) -> None:
    async with system_session() as s:
        await s.execute(text("UPDATE scheduled_tasks SET locked_until = now() + make_interval(secs => :lease) "
                             "WHERE id = :id AND locked_by = :worker AND status = 'running'"),
                        {"id": task_id, "worker": worker_id, "lease": lease_seconds})


async def complete(task_id: uuid.UUID, status: str = "completed") -> None:
    async with system_session() as s:
        await s.execute(update(ScheduledTask).where(ScheduledTask.id == task_id).values(
            status=status, locked_by=None, locked_until=None, completed_at=_now(), last_error=None))


async def fail(task: ScheduledTask, error: dict[str, Any], retryable: bool, delay_seconds: float | None = None) -> str:
    """Re-queue with exponential backoff, or mark failed/dead. Returns the new status."""
    if retryable and task.attempts < task.max_attempts:
        delay = delay_seconds if delay_seconds is not None else BACKOFF_BASE_SECONDS * (2 ** (task.attempts - 1)) * (0.8 + 0.4 * random.random())
        status, run_after = "queued", _now() + timedelta(seconds=delay)
    else:
        status, run_after = ("dead" if retryable else "failed"), task.run_after
    async with system_session() as s:
        await s.execute(update(ScheduledTask).where(ScheduledTask.id == task.id).values(
            status=status, run_after=run_after, locked_by=None, locked_until=None, last_error=error,
            completed_at=None if status == "queued" else _now()))
    return status


async def defer(task: ScheduledTask, until: datetime, error: dict[str, Any]) -> None:
    """Re-queue without consuming an attempt (e.g. LLM quota window)."""
    async with system_session() as s:
        await s.execute(update(ScheduledTask).where(ScheduledTask.id == task.id).values(
            status="queued", run_after=until, attempts=max(0, task.attempts - 1), locked_by=None, locked_until=None,
            last_error=error))


async def sweep_expired() -> int:
    """Re-queue tasks whose lease expired (crashed or slept worker)."""
    async with system_session() as s:
        result = await s.execute(text(
            "UPDATE scheduled_tasks SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'queued' END, "
            "locked_by = NULL, locked_until = NULL, last_error = jsonb_build_object('code', 'lease_expired') "
            "WHERE status = 'running' AND locked_until < now() RETURNING id"))
        return len(result.fetchall())


async def retry_run(agent_run_id: uuid.UUID, user_id: uuid.UUID) -> ScheduledTask | None:
    async with system_session() as s:
        task = (await s.execute(select(ScheduledTask).where(
            ScheduledTask.agent_run_id == agent_run_id, ScheduledTask.user_id == user_id))).scalar_one_or_none()
        if task is None or task.status not in ("failed", "dead", "cancelled", "partially_completed"):
            return None
        task.status, task.attempts, task.run_after, task.last_error = "queued", 0, _now(), None
        task.completed_at = None
        run = await s.get(AgentRun, agent_run_id)
        if run is not None:
            run.status, run.error, run.completed_at = "queued", None, None
        return task

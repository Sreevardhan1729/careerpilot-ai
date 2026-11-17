"""Task runner: claims leased tasks and executes registered handlers (in-process in the API, or in the worker)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.core.db import system_session
from app.core.errors import AppError, LLMQuotaExhausted
from app.core.logging import get_logger
from app.models import AgentRun, ScheduledTask
from app.tasks import queue

log = get_logger(__name__)


@dataclass
class TaskContext:
    task_id: uuid.UUID | None
    agent_run_id: uuid.UUID
    user_id: uuid.UUID
    payload: dict[str, Any]
    _progress: list[dict[str, Any]] = field(default_factory=list)

    async def progress(self, node: str, status: str, detail: dict[str, Any] | None = None) -> None:
        await record_progress(self.agent_run_id, node, status, detail)

    async def set_subject(self, subject_type: str, subject_id: uuid.UUID) -> None:
        async with system_session() as s:
            run = await s.get(AgentRun, self.agent_run_id)
            if run:
                run.subject_type, run.subject_id = subject_type, subject_id


Handler = Callable[[TaskContext], Awaitable[dict[str, Any] | None]]
HANDLERS: dict[str, Handler] = {}


def handler(task_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[task_type] = fn
        return fn

    return deco


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def record_progress(run_id: uuid.UUID, node: str, status: str, detail: dict[str, Any] | None = None) -> None:
    async with system_session() as s:
        run = await s.get(AgentRun, run_id)
        if run is None:
            return
        progress = [dict(item) for item in (run.progress or [])]  # copy: in-place edits would look unchanged to the ORM
        stamp = _now().isoformat()
        for item in reversed(progress):
            if item.get("node") == node and item.get("status") == "running":
                item.update({"status": status, "finished_at": stamp, **({"detail": detail} if detail else {})})
                break
        else:
            entry = {"node": node, "status": status, "started_at": stamp}
            if status != "running":
                entry["finished_at"] = stamp
            if detail:
                entry["detail"] = detail
            progress.append(entry)
        run.progress = progress
        run.current_node = node if status == "running" else run.current_node


async def set_run_status(run_id: uuid.UUID, status: str, *, output: dict[str, Any] | None = None,
                         error: dict[str, Any] | None = None) -> None:
    async with system_session() as s:
        run = await s.get(AgentRun, run_id)
        if run is None:
            return
        run.status = status
        if status == "running" and run.started_at is None:
            run.started_at = _now()
        if status in ("completed", "partially_completed", "failed", "cancelled"):
            run.completed_at = _now()
            run.current_node = None
        if output is not None:
            run.output = output
        if error is not None or status == "running":
            run.error = error


class TaskRunner:
    def __init__(self, concurrency: int | None = None, poll_seconds: float | None = None, lease_seconds: int | None = None):
        s = get_settings()
        self.concurrency = concurrency or s.task_runner_concurrency
        self.poll_seconds = poll_seconds if poll_seconds is not None else s.task_poll_seconds
        self.lease_seconds = lease_seconds or s.task_lease_seconds
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task | None = None
        self._last_sweep = 0.0

    async def start(self) -> None:
        self._stop.clear()
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._loop_task:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._loop_task, timeout=10)

    async def _loop(self) -> None:
        sem = asyncio.Semaphore(self.concurrency)
        running: set[asyncio.Task] = set()
        while not self._stop.is_set():
            try:
                await self._maybe_sweep()
                if sem.locked():
                    await asyncio.sleep(self.poll_seconds)
                    continue
                task = await queue.claim(self.worker_id, self.lease_seconds)
                if task is None:
                    await asyncio.sleep(self.poll_seconds)
                    continue
                await sem.acquire()
                t = asyncio.create_task(self._execute(task))
                running.add(t)
                t.add_done_callback(lambda fut: (running.discard(fut), sem.release()))
            except Exception as exc:  # keep the loop alive (DB blips, host wake-up)
                log.warning("task_runner_loop_error", error=str(exc)[:300])
                await asyncio.sleep(max(1.0, self.poll_seconds))
        for t in list(running):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(t, timeout=30)

    async def _maybe_sweep(self) -> None:
        if time.monotonic() - self._last_sweep > 30:
            self._last_sweep = time.monotonic()
            await queue.sweep_expired()

    async def run_until_empty(self, user_ids: list[uuid.UUID] | None = None, time_budget_seconds: float | None = None,
                              max_tasks: int | None = None) -> int:
        """Process queued tasks sequentially until none are ready (tests, worker)."""
        started, done = time.monotonic(), 0
        await queue.sweep_expired()
        while True:
            if time_budget_seconds and time.monotonic() - started > time_budget_seconds:
                break
            if max_tasks is not None and done >= max_tasks:
                break
            task = await queue.claim(self.worker_id, self.lease_seconds, user_ids)
            if task is None:
                break
            await self._execute(task)
            done += 1
        return done

    async def _heartbeat(self, task_id: uuid.UUID) -> None:
        while True:
            await asyncio.sleep(max(5, self.lease_seconds / 3))
            await queue.heartbeat(task_id, self.worker_id, self.lease_seconds)

    async def _execute(self, task: ScheduledTask) -> None:
        assert task.agent_run_id and task.user_id
        ctx = TaskContext(task.id, task.agent_run_id, task.user_id, task.payload or {})
        fn = HANDLERS.get(task.task_type)
        beat = asyncio.create_task(self._heartbeat(task.id))
        try:
            if fn is None:
                raise AppError(f"No handler for task type {task.task_type}", code="internal_error")
            await set_run_status(ctx.agent_run_id, "running")
            output = await fn(ctx) or {}
            status = output.pop("_status", "completed")
            await set_run_status(ctx.agent_run_id, status, output=output)
            await queue.complete(task.id, "partially_completed" if status == "partially_completed" else "completed")
            log.info("task_completed", task_type=task.task_type, task_id=str(task.id), status=status)
        except LLMQuotaExhausted as exc:
            until = _now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            await queue.defer(task, until, {"code": exc.code, "message": exc.message})
            await set_run_status(ctx.agent_run_id, "queued", error={"code": exc.code, "message": exc.message, "retryable": True})
        except Exception as exc:
            retryable = bool(getattr(exc, "retryable", False))
            err = {"code": getattr(exc, "code", "internal_error"), "message": getattr(exc, "message", str(exc))[:500],
                   "retryable": retryable, "details": getattr(exc, "details", {})}
            if not isinstance(exc, AppError):
                log.exception("task_failed", task_type=task.task_type, task_id=str(task.id))
            new_status = await queue.fail(task, err, retryable)
            await set_run_status(ctx.agent_run_id, "queued" if new_status == "queued" else "failed", error=err)
            if new_status != "queued":
                from app.services.notifications import notify_run_failed

                with contextlib.suppress(Exception):
                    await notify_run_failed(task.user_id, ctx.agent_run_id, task.task_type, err)
        finally:
            beat.cancel()


async def run_inline(user_id: uuid.UUID, task_type: str, payload: dict[str, Any], parent_run_id: uuid.UUID | None,
                     subject_type: str | None = None, subject_id: uuid.UUID | None = None) -> tuple[uuid.UUID, dict[str, Any] | None, str]:
    """Run a handler synchronously as a child run (daily pipeline). Returns (run_id, output, status)."""
    async with system_session() as s:
        run = AgentRun(user_id=user_id, workflow_name=queue.TASK_WORKFLOWS[task_type], workflow_version=queue.WORKFLOW_VERSION,
                       parent_run_id=parent_run_id, subject_type=subject_type, subject_id=subject_id, status="running",
                       started_at=_now())
        s.add(run)
        await s.flush()
        run_id = run.id
    ctx = TaskContext(None, run_id, user_id, payload)
    try:
        output = await HANDLERS[task_type](ctx) or {}
        status = output.pop("_status", "completed")
        await set_run_status(run_id, status, output=output)
        return run_id, output, status
    except Exception as exc:
        err = {"code": getattr(exc, "code", "internal_error"), "message": getattr(exc, "message", str(exc))[:500]}
        if not isinstance(exc, AppError):
            log.exception("inline_task_failed", task_type=task_type)
        await set_run_status(run_id, "failed", error=err)
        return run_id, None, "failed"

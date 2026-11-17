"""LangGraph runtime: typed context, progress-tracked nodes, retry policy, checkpointer, resume (docs/AGENT_DESIGN.md §2)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy

from app.core.config import get_settings
from app.tasks.runner import TaskContext

_memory_saver = InMemorySaver()
_pg_saver: Any = None
_pg_pool: Any = None


@dataclass
class WorkflowContext:
    user_id: uuid.UUID
    run_id: uuid.UUID
    task: TaskContext


NodeFn = Callable[[dict[str, Any], WorkflowContext], Awaitable[dict[str, Any]]]

TRANSIENT_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0, jitter=True,
                              retry_on=lambda exc: bool(getattr(exc, "retryable", False)))


def tracked(name: str, fn: NodeFn) -> Callable[[dict[str, Any], Runtime[WorkflowContext]], Awaitable[dict[str, Any]]]:
    async def node(state: dict[str, Any], runtime: Runtime[WorkflowContext]) -> dict[str, Any]:
        ctx = runtime.context
        await ctx.task.progress(name, "running")
        try:
            update = await fn(state, ctx) or {}
        except Exception as exc:
            await ctx.task.progress(name, "failed", {"error": getattr(exc, "code", type(exc).__name__)})
            raise
        detail = update.pop("_detail", None) if isinstance(update, dict) else None
        await ctx.task.progress(name, "completed", detail)
        return update

    node.__name__ = name
    return node


def add_nodes(builder: StateGraph, nodes: list[tuple[str, NodeFn]], retry: bool = True) -> None:
    for name, fn in nodes:
        builder.add_node(name, tracked(name, fn), retry_policy=TRANSIENT_RETRY if retry else None)


async def get_checkpointer() -> Any:
    global _pg_saver, _pg_pool
    if get_settings().checkpointer != "postgres":
        return _memory_saver
    if _pg_saver is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        from app.core.db import resolve_database_url

        conninfo = resolve_database_url().replace("postgresql+psycopg://", "postgresql://", 1)
        _pg_pool = AsyncConnectionPool(conninfo, max_size=3, open=False,
                                       kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None,
                                               "options": "-c search_path=langgraph"})
        await _pg_pool.open()
        _pg_saver = AsyncPostgresSaver(_pg_pool)
        await _pg_saver.setup()
    return _pg_saver


async def close_checkpointer() -> None:
    global _pg_saver, _pg_pool
    if _pg_pool is not None:
        await _pg_pool.close()
    _pg_saver = _pg_pool = None


async def delete_thread(run_id: uuid.UUID) -> None:
    saver = await get_checkpointer()
    if hasattr(saver, "adelete_thread"):
        await saver.adelete_thread(str(run_id))


async def run_graph(builder: StateGraph, state: dict[str, Any], ctx: WorkflowContext) -> dict[str, Any]:
    """Run a workflow; if a checkpoint exists for this run (crash/lease expiry), resume from it instead."""
    graph = builder.compile(checkpointer=await get_checkpointer())
    config = {"configurable": {"thread_id": str(ctx.run_id)}, "recursion_limit": 100}
    snapshot = await graph.aget_state(config)
    if snapshot and snapshot.next and not snapshot.interrupts:
        return await graph.ainvoke(None, config, context=ctx)
    if snapshot and snapshot.values and not snapshot.next:
        return dict(snapshot.values)  # already finished (idempotent re-run)
    return await graph.ainvoke(state, config, context=ctx)


async def resume_graph(builder: StateGraph, ctx: WorkflowContext, resume_value: Any) -> dict[str, Any] | None:
    """Resume an interrupted run with a recorded decision. Returns None if no checkpoint is available."""
    graph = builder.compile(checkpointer=await get_checkpointer())
    config = {"configurable": {"thread_id": str(ctx.run_id)}}
    snapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.next:
        return None
    return await graph.ainvoke(Command(resume=resume_value), config, context=ctx)

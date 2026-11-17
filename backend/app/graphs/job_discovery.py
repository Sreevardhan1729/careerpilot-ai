"""Job Discovery Graph (AGENT_DESIGN §9): fan out one isolated branch per source, then aggregate."""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import user_session
from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.models import CrawlSource
from app.services import discovery as svc
from app.tasks import queue
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    source_ids: list[str]
    only_ids: list[str] | None
    enqueue_analysis: bool
    results: Annotated[list[dict[str, Any]], operator.add]
    new_job_ids: list[str]
    status: str


async def load_sources(state: State, ctx: WorkflowContext) -> dict:
    limit = get_settings().discovery_max_sources_per_run
    async with user_session(ctx.user_id) as s:
        q = select(CrawlSource.id).where(CrawlSource.user_id == ctx.user_id, CrawlSource.enabled)
        if state.get("only_ids"):
            q = q.where(CrawlSource.id.in_([uuid.UUID(i) for i in state["only_ids"]]))
        ids = [str(i) for i in (await s.execute(q.order_by(CrawlSource.created_at).limit(limit))).scalars().all()]
    return {"source_ids": ids, "_detail": {"sources": len(ids)}}


def fan_out(state: State):
    return [Send("run_source", {"source_id": sid}) for sid in state.get("source_ids", [])] or "aggregate"


async def run_source(state: dict[str, Any], runtime) -> dict:
    ctx: WorkflowContext = runtime.context
    sid = state["source_id"]
    result = await svc.run_source(ctx.user_id, uuid.UUID(sid), ctx.run_id, get_settings().discovery_max_listings_per_source)
    await ctx.task.progress(f"source:{result['source_type']}:{sid[:8]}", result["status"],
                            {k: result[k] for k in ("found", "new", "merged", "filtered_out")})
    return {"results": [result]}


async def aggregate(state: State, ctx: WorkflowContext) -> dict:
    results = state.get("results", [])
    statuses = {r["status"] for r in results}
    if not results:
        status = "completed"
    elif statuses == {"failed"}:
        status = "failed"
    elif "failed" in statuses or "partially_completed" in statuses:
        status = "partially_completed"
    else:
        status = "completed"
    new_ids = [j for r in results for j in r.get("new_job_ids", [])]
    return {"new_job_ids": new_ids, "status": status,
            "_detail": {"sources": len(results), "new_jobs": len(new_ids), "failed_sources": sum(r["status"] == "failed" for r in results)}}


async def enqueue_analysis(state: State, ctx: WorkflowContext) -> dict:
    if not state.get("enqueue_analysis", True):
        return {}
    cap = get_settings().discovery_max_new_jobs_analyzed_per_run
    for job_id in state.get("new_job_ids", [])[:cap]:
        await queue.enqueue(user_id=ctx.user_id, task_type="analyze_job", payload={"job_id": job_id}, priority=5,
                            idempotency_key=f"analyze_job:{job_id}", subject_type="job", subject_id=uuid.UUID(job_id),
                            parent_run_id=ctx.run_id)
    return {"_detail": {"queued": min(cap, len(state.get("new_job_ids", [])))}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("load_sources", load_sources), ("aggregate", aggregate), ("enqueue_analysis", enqueue_analysis)])
    g.add_node("run_source", run_source)  # each branch isolates its own failures inside svc.run_source
    g.add_edge(START, "load_sources")
    g.add_conditional_edges("load_sources", fan_out, ["run_source", "aggregate"])
    g.add_edge("run_source", "aggregate")
    g.add_edge("aggregate", "enqueue_analysis")
    g.add_edge("enqueue_analysis", END)
    return g


@handler("discover_jobs")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), {"only_ids": ctx.payload.get("source_ids"), "enqueue_analysis": ctx.payload.get("enqueue_analysis", True),
                                    "results": []}, WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    return {"_status": out.get("status", "completed"), "new_job_ids": out.get("new_job_ids", []),
            "sources": [{k: r[k] for k in ("source_id", "source_type", "status", "found", "new", "merged", "filtered_out", "errors")}
                        for r in out.get("results", [])]}

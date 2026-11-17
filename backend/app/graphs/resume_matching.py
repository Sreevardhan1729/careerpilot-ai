"""Resume Matching Graph (AGENT_DESIGN §5): deterministic scoring, optional LLM explanation, job ranking."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.services import matching
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    job_id: str
    result: dict[str, Any]


async def score_and_rank(state: State, ctx: WorkflowContext) -> dict:
    result = await matching.match_job(ctx.user_id, uuid.UUID(state["job_id"]), ctx.run_id)
    return {"result": result, "_detail": result}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("score_and_rank", score_and_rank)])
    g.add_edge(START, "score_and_rank")
    g.add_edge("score_and_rank", END)
    return g


@handler("match_resumes")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), {"job_id": ctx.payload["job_id"]}, WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    return {"job_id": ctx.payload["job_id"], **(out.get("result") or {})}

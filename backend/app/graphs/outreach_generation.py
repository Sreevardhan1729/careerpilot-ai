"""Outreach Generation Graph (AGENT_DESIGN §8): verified facts → drafts → claim check (→ one regeneration) → persist."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.services import outreach as svc
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    job_id: str
    person_ids: list[str] | None
    message_types: list[str]
    resume_id: str | None
    result: dict[str, Any]


async def generate_and_check(state: State, ctx: WorkflowContext) -> dict:
    result = await svc.generate(ctx.user_id, ctx.run_id, uuid.UUID(state["job_id"]),
                                [uuid.UUID(p) for p in state.get("person_ids") or []] or None,
                                state.get("message_types") or ["linkedin_connection", "recruiter_email"],
                                uuid.UUID(state["resume_id"]) if state.get("resume_id") else None)
    return {"result": result, "_detail": {"drafts": result["drafts"], "with_blocking_issues": result["with_blocking_issues"]}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("generate_and_check", generate_and_check)])
    g.add_edge(START, "generate_and_check")
    g.add_edge("generate_and_check", END)
    return g


@handler("generate_outreach")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), dict(ctx.payload), WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    return {"job_id": ctx.payload["job_id"], **(out.get("result") or {})}

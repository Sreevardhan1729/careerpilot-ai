"""Resume Ingestion Graph (AGENT_DESIGN §4)."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app import agents
from app.core.db import user_session
from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.integrations.parsing.documents import extract_document
from app.integrations.storage import get_storage
from app.models import Resume, ResumeVersion
from app.schemas.llm.resume import ResumeParsed
from app.services import resumes as svc
from app.services.common import get_owned
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    resume_id: str
    version_id: str
    text: str
    page_count: int | None
    parsed: dict[str, Any]
    warnings: list[str]
    method: str


async def extract_text(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        version = await get_owned(s, ResumeVersion, state["version_id"], ctx.user_id)
        resume = await get_owned(s, Resume, state["resume_id"], ctx.user_id)
        resume.status = "parsing"
        key, mime, existing = version.storage_key, version.mime_type, version.extracted_text
    if existing:
        return {"text": existing, "page_count": None}
    data = await get_storage().get(key)
    doc = extract_document(data, "pdf" if mime == "application/pdf" else "docx")
    return {"text": doc.text, "page_count": doc.page_count, "_detail": {"chars": len(doc.text), "pages": doc.page_count}}


async def structure(state: State, ctx: WorkflowContext) -> dict:
    parsed, meta = await agents.parse_resume(state["text"], user_id=ctx.user_id, run_id=ctx.run_id)
    return {"parsed": parsed.model_dump(mode="json"), "method": meta.prompt_ref,
            "_detail": {"model_id": meta.model_id, "prompt": meta.prompt_ref}}


async def verify(state: State, ctx: WorkflowContext) -> dict:
    parsed, warnings = svc.verify_parsed(ResumeParsed.model_validate(state["parsed"]), state["text"])
    return {"parsed": parsed.model_dump(mode="json"), "warnings": warnings, "_detail": {"warnings": len(warnings)}}


async def persist(state: State, ctx: WorkflowContext) -> dict:
    parsed = ResumeParsed.model_validate(state["parsed"])
    await svc.persist_ingestion(ctx.user_id, uuid.UUID(state["resume_id"]), uuid.UUID(state["version_id"]), state["text"],
                                state.get("page_count"), parsed, state.get("warnings", []), state.get("method", ""),
                                origin="heuristic" if state.get("method", "").startswith("heuristic") else "llm")
    return {"_detail": {"skills": len(parsed.skills), "projects": len(parsed.projects), "experience": len(parsed.experience)}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("extract_text", extract_text), ("structure", structure), ("verify", verify), ("persist", persist)])
    g.add_edge(START, "extract_text")
    g.add_edge("extract_text", "structure")
    g.add_edge("structure", "verify")
    g.add_edge("verify", "persist")
    g.add_edge("persist", END)
    return g


@handler("parse_resume")
async def handle(ctx: TaskContext) -> dict:
    try:
        await run_graph(build(), {"resume_id": ctx.payload["resume_id"], "version_id": ctx.payload["version_id"]},
                        WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    except Exception:
        async with user_session(ctx.user_id) as s:
            resume = await s.get(Resume, uuid.UUID(ctx.payload["resume_id"]))
            if resume:
                resume.status = "failed"
        raise
    return {"resume_id": ctx.payload["resume_id"]}

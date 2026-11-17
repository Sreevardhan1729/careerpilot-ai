"""Resume Optimisation Graph (AGENT_DESIGN §10.1): suggestions only, each validated against cited evidence."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app import agents
from app.core.db import user_session
from app.core.errors import NotFound
from app.domain.claims import ClaimContext, check_claims
from app.domain.matching import load_scoring_config
from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.models import Job, JobSkill, Resume, ResumeChunk, ResumeMatch, ResumeVersion
from app.schemas.llm.resume import ResumeParsed
from app.services.common import get_owned
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    resume_id: str
    job_id: str
    improvement: dict[str, Any]


async def suggest(state: State, ctx: WorkflowContext) -> dict:
    cfg = load_scoring_config()
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        resume = await get_owned(s, Resume, state["resume_id"], ctx.user_id)
        version = await s.get(ResumeVersion, resume.current_version_id)
        match = (await s.execute(select(ResumeMatch).where(ResumeMatch.job_id == job.id, ResumeMatch.resume_version_id == version.id,
                                                           ResumeMatch.scoring_config_version == cfg.version))).scalars().first()
        if match is None:
            raise NotFound("Match this resume against the job first.")
        chunks = (await s.execute(select(ResumeChunk).where(ResumeChunk.resume_version_id == version.id))).scalars().all()
        keywords = (await s.execute(select(JobSkill.normalized_name).where(JobSkill.job_id == job.id))).scalars().all()
        parsed = ResumeParsed.model_validate(version.parsed_data)
        breakdown, title, jd = match.skill_breakdown, job.title or "this role", job.description_text
    evidence = "\n".join(f"[chunk:{c.id}] {c.content}" for c in chunks)
    by_id = {f"chunk:{c.id}": c.content for c in chunks}
    imp, meta = await agents.improve_resume(match={"skill_breakdown": breakdown}, parsed=parsed, job_title=title, job_text=jd,
                                            keywords=list(keywords), resume_evidence=evidence, user_id=ctx.user_id, run_id=ctx.run_id)
    skills = {s.name for s in parsed.skills}
    kept, dropped = [], []
    for change in imp.suggested_changes:
        texts = [change.before or "", *(by_id.get(r, "") for r in change.evidence_refs)]
        result = check_claims(change.after, None, None, ClaimContext(evidence_texts=texts, candidate_skills=skills,
                                                                     has_relationship_history=True, recipient_verified_email=None))
        (kept if result.passed else dropped).append(change.model_dump() | ({"rejected": result.blocking} if not result.passed else {}))
    out = imp.model_dump()
    out["suggested_changes"], out["dropped_changes"], out["method"] = kept, dropped, meta.method
    async with user_session(ctx.user_id) as s:
        m = (await s.execute(select(ResumeMatch).where(ResumeMatch.job_id == uuid.UUID(state["job_id"]),
                                                       ResumeMatch.resume_id == uuid.UUID(state["resume_id"]),
                                                       ResumeMatch.scoring_config_version == cfg.version))).scalars().first()
        if m:
            m.suggestions = {**(m.suggestions or {}), "improvement": out}
    return {"improvement": out, "_detail": {"kept": len(kept), "dropped": len(dropped), "model_id": meta.model_id}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("suggest", suggest)])
    g.add_edge(START, "suggest")
    g.add_edge("suggest", END)
    return g


@handler("optimize_resume")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), dict(ctx.payload), WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    return {"resume_id": ctx.payload["resume_id"], "job_id": ctx.payload["job_id"], "improvement": out.get("improvement")}

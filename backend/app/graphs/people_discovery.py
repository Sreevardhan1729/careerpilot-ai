"""People Discovery Graph (AGENT_DESIGN §7): collect evidence → classify → validate → score → persist."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app import agents
from app.core.db import user_session
from app.core.errors import NotFound
from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.heuristics.people import EvidenceItem
from app.integrations.fetch import SafeFetcher
from app.integrations.search import get_search_provider
from app.models import Company, Job, PersonEvidence
from app.schemas.llm.job import PosterInfo
from app.services import people as svc
from app.services.common import get_owned
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    job_id: str
    evidence_ids: list[str]
    classified: list[dict[str, Any]]
    verified_count: int
    unavailable_count: int
    coverage_note: str | None


async def collect(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        if not job.company_id:
            raise NotFound("This job has no company yet; analyse it first.")
        company = await s.get(Company, job.company_id)
    raw: list[dict[str, Any]] = []
    if job.posted_by and job.posted_by.get("name"):
        raw.append({"source_type": "job_post", "provider": "user", "source_url": job.source_url or job.application_url or "user-provided:job-post",
                    "source_title": None, "snippet": f"{job.posted_by['name']}\n{job.posted_by.get('headline') or ''}".strip()})
    raw += await svc.collect_company_pages(company, SafeFetcher())
    raw += await svc.collect_search(company, job)
    stored = await svc.store_evidence(ctx.user_id, job.id, company.id, raw)
    # include earlier evidence for this company (incl. user-provided) so repeat runs keep verified contacts
    async with user_session(ctx.user_id) as s:
        prior = (await s.execute(select(PersonEvidence.id).where(PersonEvidence.user_id == ctx.user_id,
                                                                 PersonEvidence.company_id == company.id))).scalars().all()
    ids = list(dict.fromkeys([str(e.id) for e in stored] + [str(i) for i in prior]))
    return {"evidence_ids": ids, "_detail": {"evidence_items": len(ids), "search_provider": get_search_provider().name}}


async def classify(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        company = await s.get(Company, job.company_id)
        rows = (await s.execute(select(PersonEvidence).where(PersonEvidence.id.in_([uuid.UUID(i) for i in state["evidence_ids"]])))).scalars().all()
    items = [EvidenceItem(id=str(e.id), source_type=e.source_type, url=e.source_url, title=e.source_title, snippet=e.snippet)
             for e in rows if e.source_type != "user_provided"]
    poster = PosterInfo.model_validate(job.posted_by) if job.posted_by else None
    result, meta = await agents.classify_people(items, company=company.name, domain=company.domain, job_title=job.title,
                                                department=job.department, poster=poster, user_id=ctx.user_id, run_id=ctx.run_id)
    return {"classified": [p.model_dump() for p in result.people], "_detail": {"candidates": len(result.people), "model_id": meta.model_id}}


async def validate_and_persist(state: State, ctx: WorkflowContext) -> dict:
    from app.schemas.llm.other import ClassifiedPerson

    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        company = await s.get(Company, job.company_id)
        rows = (await s.execute(select(PersonEvidence).where(PersonEvidence.id.in_([uuid.UUID(i) for i in state["evidence_ids"]])))).scalars().all()
    evidence = {str(e.id): e for e in rows}
    people = [ClassifiedPerson.model_validate(p) for p in state.get("classified", [])]
    verified, rejected = await svc.upsert_people(ctx.user_id, job, company, people, evidence)
    notes = []
    if not get_search_provider().enabled:
        notes.append("No search provider configured; results limited to company pages, the job post and people you add.")
    if not company.domain:
        notes.append("Company website unknown, so team pages could not be checked.")
    return {"verified_count": verified, "unavailable_count": max(0, svc.TARGET - verified),
            "coverage_note": " ".join(notes) or None, "_detail": {"verified": verified, "rejected": rejected}}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("collect", collect), ("classify", classify), ("validate_and_persist", validate_and_persist)])
    g.add_edge(START, "collect")
    g.add_edge("collect", "classify")
    g.add_edge("classify", "validate_and_persist")
    g.add_edge("validate_and_persist", END)
    return g


@handler("discover_people")
async def handle(ctx: TaskContext) -> dict:
    out = await run_graph(build(), {"job_id": ctx.payload["job_id"]}, WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    return {"job_id": ctx.payload["job_id"], "verified_count": out.get("verified_count", 0),
            "unavailable_count": out.get("unavailable_count", 0), "coverage_note": out.get("coverage_note")}

"""Job Extraction Graph (AGENT_DESIGN §3): fetch → clean → dedup → extract → verify → persist → match."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app import agents
from app.core.db import user_session
from app.domain.dedup import ListingKey, normalize_title
from app.domain.job_verify import verify_extraction
from app.domain.text import clean_text, description_hash
from app.domain.urls import canonical_job_key, canonicalize_url
from app.graphs.runtime import WorkflowContext, add_nodes, run_graph
from app.integrations.fetch import SafeFetcher
from app.integrations.parsing.html import extract_jsonld_jobposting, html_to_text
from app.integrations.sources import resolve_ats_posting
from app.models import Job, JobSourceRecord
from app.schemas.llm.job import JobExtraction
from app.services import jobs as jobs_svc
from app.services.common import get_owned
from app.tasks import queue
from app.tasks.runner import TaskContext, handler


class State(TypedDict, total=False):
    job_id: str
    company_hint: str | None
    chain_match: bool
    text: str
    source_salary: dict[str, Any] | None
    source_posted_at: str | None
    duplicate_of: str | None
    extraction: dict[str, Any]
    model_id: str
    prompt_ref: str
    analyzed: bool


def _listing_text(title: str | None, company: str | None, location: str | None, body: str | None) -> str:
    head = "\n".join(filter(None, [title and f"Role: {title}", company and f"Company: {company}", location and f"Location: {location}"]))
    return clean_text(f"{head}\n\n{body or ''}")


async def fetch_content(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        job.status = "analyzing"
        url, text, input_type = job.source_url, job.description_text, job.input_type
    if text or input_type != "url" or not url:
        salary, posted = None, None
        if input_type == "discovery":
            async with user_session(ctx.user_id) as s:
                rec = (await s.execute(select(JobSourceRecord).where(JobSourceRecord.job_id == uuid.UUID(state["job_id"]))
                                       .order_by(JobSourceRecord.collected_at))).scalars().first()
                if rec:
                    salary, posted = (rec.metadata_ or {}).get("salary"), rec.posted_at
        return {"text": text, "source_salary": salary, "source_posted_at": posted.isoformat() if posted else None}
    fetcher = SafeFetcher()
    listing = await resolve_ats_posting(url, fetcher)
    salary, posted, source_name, listing_id, app_url = None, None, "url", None, None
    if listing:
        body = _listing_text(listing.job_title, listing.company, listing.location, listing.raw_description)
        salary, posted = listing.source_metadata.get("salary"), listing.posted_date
        source_name, listing_id, app_url = listing.source_name, listing.source_listing_id, listing.application_url
    else:
        res = await fetcher.get(url)
        jp = extract_jsonld_jobposting(res.text, res.url) if "html" in res.content_type else None
        if jp:
            body = _listing_text(jp.get("title"), jp.get("company"), jp.get("location"), jp.get("description"))
            salary = jp.get("salary")
            if salary:
                salary = {**salary}
            from app.integrations.sources.base import parse_iso

            posted = parse_iso(jp.get("date_posted"))
        elif "html" in res.content_type:
            body = html_to_text(res.text)[1]
        else:
            body = clean_text(res.text)
    if len(body) < jobs_svc.MIN_TEXT_CHARS:
        from app.core.errors import FetchFailed

        raise FetchFailed("The page had no readable job description. Paste the text instead.")
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        job.description_text, job.description_sha256 = body, description_hash(body)
        if posted:
            job.posted_at, job.posted_at_source = posted, "source_api"
        job.application_url = app_url or job.application_url
        s.add(JobSourceRecord(user_id=ctx.user_id, job_id=job.id, source_name=source_name, source_listing_id=listing_id,
                              source_url=url, canonical_url=canonical_job_key(url), application_url=canonicalize_url(app_url),
                              posted_at=posted, collected_at=datetime.now(tz=UTC), raw_description=body,
                              content_sha256=job.description_sha256, dedup_signal="new"))
    return {"text": body, "source_salary": salary, "source_posted_at": posted.isoformat() if posted else None,
            "_detail": {"source": source_name, "chars": len(body)}}


async def dedup_check(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        key = ListingKey(canonical_url=job.canonical_url, source_name=None, source_listing_id=None, application_url=None,
                         description_hash=job.description_sha256, company_id=None, normalized_title=None, location_key=None,
                         posted_at=None)
        hit = await jobs_svc.find_db_duplicate(s, ctx.user_id, key, exclude=job.id)
        if not hit:
            return {"duplicate_of": None}
        existing_id, signal = hit
        records = (await s.execute(select(JobSourceRecord).where(JobSourceRecord.job_id == job.id))).scalars().all()
        for r in records:
            r.job_id, r.dedup_signal = existing_id, signal
        await s.flush()
        await s.delete(job)
    await ctx.task.set_subject("job", existing_id)
    return {"duplicate_of": str(existing_id), "_detail": {"merged_into": str(existing_id), "signal": signal}}


async def extract(state: State, ctx: WorkflowContext) -> dict:
    x, meta = await agents.extract_job(state["text"], company_hint=state.get("company_hint"), source_url=None,
                                       user_id=ctx.user_id, run_id=ctx.run_id)
    return {"extraction": x.model_dump(mode="json"), "model_id": meta.model_id, "prompt_ref": meta.prompt_ref,
            "_detail": {"model_id": meta.model_id, "prompt": meta.prompt_ref}}


async def verify_and_persist(state: State, ctx: WorkflowContext) -> dict:
    async with user_session(ctx.user_id) as s:
        job = await get_owned(s, Job, state["job_id"], ctx.user_id)
        source_url, application_url = job.source_url, job.application_url
    x = JobExtraction.model_validate(state["extraction"])
    posted = datetime.fromisoformat(state["source_posted_at"]) if state.get("source_posted_at") else None
    v = verify_extraction(x, state["text"], source_url=source_url or application_url, source_salary=state.get("source_salary"),
                          source_posted_at=posted, company_hint=state.get("company_hint"))
    await jobs_svc.persist_verified(ctx.user_id, uuid.UUID(state["job_id"]), v, extraction=state["extraction"],
                                    model_id=state["model_id"], prompt_ref=state["prompt_ref"],
                                    company_url_hint=application_url or source_url)
    return {"analyzed": True, "_detail": {"skills": len(v.skills), "missing": v.missing_information,
                                          "normalized_title": normalize_title(v.title)}}


async def enqueue_match(state: State, ctx: WorkflowContext) -> dict:
    if state.get("chain_match", True):
        await queue.enqueue(user_id=ctx.user_id, task_type="match_resumes", payload={"job_id": state["job_id"]}, priority=1,
                            idempotency_key=f"match_resumes:{state['job_id']}:{ctx.run_id}", subject_type="job",
                            subject_id=uuid.UUID(state["job_id"]), parent_run_id=ctx.run_id)
    return {}


def build() -> StateGraph:
    g = StateGraph(State, context_schema=WorkflowContext)
    add_nodes(g, [("fetch_content", fetch_content), ("dedup_check", dedup_check), ("extract", extract),
                  ("verify_and_persist", verify_and_persist), ("enqueue_match", enqueue_match)])
    g.add_edge(START, "fetch_content")
    g.add_edge("fetch_content", "dedup_check")
    g.add_conditional_edges("dedup_check", lambda st: END if st.get("duplicate_of") else "extract")
    g.add_edge("extract", "verify_and_persist")
    g.add_edge("verify_and_persist", "enqueue_match")
    g.add_edge("enqueue_match", END)
    return g


@handler("analyze_job")
async def handle(ctx: TaskContext) -> dict:
    job_id = ctx.payload["job_id"]
    try:
        out = await run_graph(build(), {"job_id": job_id, "company_hint": ctx.payload.get("company_hint"),
                                        "chain_match": ctx.payload.get("chain_match", True)},
                              WorkflowContext(ctx.user_id, ctx.agent_run_id, ctx))
    except Exception:
        async with user_session(ctx.user_id) as s:
            job = await s.get(Job, uuid.UUID(job_id))
            if job and job.status != "analyzed":
                job.status = "failed"
        raise
    if out.get("duplicate_of"):
        return {"job_id": out["duplicate_of"], "deduplicated": True}
    return {"job_id": job_id, "deduplicated": False}

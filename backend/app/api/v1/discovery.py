"""Sources, discovery and scheduler endpoints."""

from __future__ import annotations

import hmac
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import get_principal, rate_limit
from app.core.config import get_settings
from app.core.db import system_session, user_session
from app.core.errors import Unauthorized
from app.core.security import Principal
from app.integrations.fetch import SafeFetcher
from app.integrations.sources import SourceConfig, get_adapter
from app.models import AgentRun, CrawlRun, CrawlSource, SearchConfig, User
from app.schemas import api as S
from app.services import discovery as svc
from app.services.common import audit, get_owned
from app.tasks import queue

router = APIRouter(tags=["discovery"])


@router.get("/sources", response_model=list[S.SourceOut])
async def list_sources(p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        rows = (await s.execute(select(CrawlSource).where(CrawlSource.user_id == p.user_id).order_by(CrawlSource.created_at))).scalars().all()
        return [S.SourceOut.model_validate(r) for r in rows]


@router.post("/sources", response_model=S.SourceOut, status_code=201)
async def add_source(body: S.SourceIn, p: Principal = Depends(get_principal)):
    ident = await svc.validate_identifier(body.source_type, body.identifier)
    async with user_session(p.user_id) as s:
        cfg = {**body.config, **({"company_name": body.company_name} if body.company_name else {})}
        src = CrawlSource(user_id=p.user_id, source_type=body.source_type, identifier=ident, enabled=body.enabled, config=cfg,
                          name=body.name or f"{body.company_name or ident} ({body.source_type})",
                          terms_note=body.terms_note, terms_reviewed_at=datetime.now(tz=UTC) if body.terms_note else None,
                          rate_limit_per_minute=get_adapter(body.source_type, SafeFetcher()).default_rate_limit_per_minute)
        s.add(src)
        await s.flush()
        await audit(s, p.user_id, "source.added", "crawl_source", src.id, source_type=body.source_type)
        return S.SourceOut.model_validate(src)


@router.patch("/sources/{source_id}", response_model=S.SourceOut)
async def patch_source(source_id: uuid.UUID, body: S.SourcePatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        src = await get_owned(s, CrawlSource, source_id, p.user_id)
        data = body.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(src, k, v)
        if data.get("enabled"):
            src.consecutive_failures = 0
        if "terms_note" in data:
            src.terms_reviewed_at = datetime.now(tz=UTC)
        if "enabled" in data:
            await audit(s, p.user_id, "source.enabled" if data["enabled"] else "source.disabled", "crawl_source", src.id)
        await s.flush()
        return S.SourceOut.model_validate(src)


@router.delete("/sources/{source_id}", response_model=S.OkOut)
async def delete_source(source_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        await s.delete(await get_owned(s, CrawlSource, source_id, p.user_id))
    return S.OkOut()


@router.post("/sources/{source_id}/health-check")
async def health_check(source_id: uuid.UUID, p: Principal = Depends(get_principal)) -> dict:
    async with user_session(p.user_id) as s:
        src = await get_owned(s, CrawlSource, source_id, p.user_id)
        stype, ident, cfg = src.source_type, src.identifier, src.config or {}
    health = await get_adapter(stype, SafeFetcher()).health_check(SourceConfig(identifier=ident, company_name=cfg.get("company_name")))
    async with user_session(p.user_id) as s:
        src = await get_owned(s, CrawlSource, source_id, p.user_id)
        src.last_status, src.last_error = ("healthy" if health.ok else "unhealthy"), (None if health.ok else health.detail)
    return health.model_dump(mode="json")


@router.post("/jobs/discover", status_code=202, response_model=S.Accepted)
async def discover(body: S.DiscoverIn, p: Principal = Depends(rate_limit("discover", capacity=6))):
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="discover_jobs", priority=3,
                                    payload={"source_ids": [str(i) for i in body.source_ids] if body.source_ids else None})
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}")


async def _daily_for(user_id: uuid.UUID, day) -> tuple[AgentRun, bool]:
    run, _, created = await queue.enqueue(user_id=user_id, task_type="daily_pipeline", payload={"date": day.isoformat()},
                                          idempotency_key=f"daily_pipeline:{user_id}:{day.isoformat()}", priority=5, max_attempts=2)
    return run, created


@router.post("/scheduler/run")
async def scheduler_run(body: S.SchedulerRunIn, request: Request, x_scheduler_token: str | None = Header(default=None)):
    """Trigger the daily pipeline. Accepts a user bearer token, or X-Scheduler-Token for an external cron."""
    settings = get_settings()
    day = body.date or datetime.now(tz=ZoneInfo(settings.default_timezone)).date()
    if x_scheduler_token:
        expected = settings.scheduler_token.get_secret_value() if settings.scheduler_token else ""
        if not expected or not hmac.compare_digest(x_scheduler_token, expected):
            raise Unauthorized("Invalid scheduler token.")
        async with system_session() as s:
            ids = (await s.execute(select(User.id).join(SearchConfig, SearchConfig.user_id == User.id)
                                   .where(SearchConfig.is_active).distinct())).scalars().all()
        runs = [str((await _daily_for(uid, day))[0].id) for uid in ids]
        return JSONResponse({"queued": runs}, status_code=202)
    p = await get_principal(request, request.headers.get("authorization"))
    run, created = await _daily_for(p.user_id, day)
    payload = S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}").model_dump(mode="json")
    return JSONResponse(payload, status_code=202 if created else 200)


@router.get("/scheduler/runs")
async def scheduler_runs(p: Principal = Depends(get_principal)) -> dict:
    async with user_session(p.user_id) as s:
        daily = (await s.execute(select(AgentRun).where(AgentRun.user_id == p.user_id, AgentRun.workflow_name.in_(("daily_pipeline", "job_discovery")))
                                 .order_by(AgentRun.created_at.desc()).limit(20))).scalars().all()
        crawls = (await s.execute(select(CrawlRun, CrawlSource.name).join(CrawlSource, CrawlSource.id == CrawlRun.crawl_source_id)
                                  .where(CrawlRun.user_id == p.user_id).order_by(CrawlRun.created_at.desc()).limit(50))).all()
    return {
        "runs": [{"id": str(r.id), "workflow_name": r.workflow_name, "status": r.status, "created_at": r.created_at.isoformat(),
                  "completed_at": r.completed_at.isoformat() if r.completed_at else None, "output": r.output} for r in daily],
        "crawl_runs": [{"id": str(c.id), "source": name, "status": c.status, "found": c.listings_found, "new": c.listings_new,
                        "merged": c.listings_merged, "filtered_out": c.listings_filtered_out, "errors": c.errors,
                        "created_at": c.created_at.isoformat()} for c, name in crawls],
    }

"""Health, auth/me, profile, facts, search configs, settings, dashboard, agent runs, notifications."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text

from app.api.deps import get_principal
from app.core.config import get_settings
from app.core.db import system_session, user_session
from app.core.errors import NotFound
from app.core.security import Principal, issue_dev_token
from app.models import (
    AgentRun,
    Approval,
    CandidateProfileFact,
    Notification,
    OAuthConnection,
    SearchConfig,
    User,
)
from app.schemas import api as S
from app.services import dashboard as dashboard_svc
from app.services import matching as matching_svc
from app.services import users as users_svc
from app.services.common import get_owned
from app.tasks import queue

router = APIRouter()


@router.get("/health", tags=["health"])
async def health() -> dict:
    db, migration = "ok", None
    try:
        async with system_session() as s:
            migration = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception:
        db = "error"
    from fastapi.responses import JSONResponse

    body = {"status": "ok" if db == "ok" else "degraded", "version": "0.1.0", "db": db, "migration": migration,
            "time": datetime.now(tz=UTC).isoformat()}
    return body if db == "ok" else JSONResponse(body, status_code=503)  # type: ignore[return-value]


@router.post("/dev/login", response_model=S.TokenOut, tags=["auth"])
async def dev_login(body: S.DevLoginIn) -> S.TokenOut:
    """Local development sign-in (AUTH_MODE=dev only; disabled in production)."""
    return S.TokenOut(access_token=issue_dev_token(body.email))


def _provider_info() -> tuple[dict, dict]:
    s = get_settings()
    llm = {"provider": s.llm_provider, "model": s.llm_model_label, "enabled": s.llm_enabled,
           "mode": "llm" if s.llm_enabled else "heuristic"}
    emb = {"provider": s.embedding_provider, "model": s.embedding_model_label, "dimensions": s.embedding_dimensions}
    return llm, emb


@router.get("/me", response_model=S.MeOut, tags=["auth"])
async def me(p: Principal = Depends(get_principal)) -> S.MeOut:
    async with user_session(p.user_id) as s:
        user = await s.get(User, p.user_id)
        profile = await users_svc.get_profile(s, p.user_id)
        google = (await s.execute(select(OAuthConnection).where(OAuthConnection.user_id == p.user_id,
                                                                 OAuthConnection.provider == "google"))).scalar_one_or_none()
    llm, emb = _provider_info()
    return S.MeOut(id=p.user_id, email=user.email, timezone=user.timezone, auth_mode=get_settings().auth_mode, llm=llm,
                   embeddings=emb, profile_complete=bool(profile.full_name and profile.preferred_locations),
                   integrations={"google": {"connected": bool(google and google.status == "active"),
                                            "status": google.status if google else None,
                                            "account_email": google.account_email if google else None,
                                            "configured": bool(get_settings().google_oauth_client_id)}})


# ------------------------------------------------------------------------------------------------ profile
@router.get("/profile", response_model=S.ProfileOut, tags=["profile"])
async def get_profile(p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        return S.ProfileOut.model_validate(await users_svc.get_profile(s, p.user_id))


@router.put("/profile", response_model=S.ProfileOut, tags=["profile"])
async def put_profile(body: S.ProfileUpdate, p: Principal = Depends(get_principal)):
    changes = body.model_dump(exclude_unset=True)
    if "salary_preference" in changes and body.salary_preference is not None:
        changes["salary_preference"] = body.salary_preference.model_dump()
    async with user_session(p.user_id) as s:
        out = S.ProfileOut.model_validate(await users_svc.update_profile(s, p.user_id, changes))
    await matching_svc.rerank_all(p.user_id)
    return out


@router.get("/profile/facts", response_model=list[S.FactOut], tags=["profile"])
async def list_facts(fact_type: str | None = None, status: str | None = None, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(CandidateProfileFact).where(CandidateProfileFact.user_id == p.user_id)
        if fact_type:
            q = q.where(CandidateProfileFact.fact_type == fact_type)
        if status:
            q = q.where(CandidateProfileFact.status == status)
        rows = (await s.execute(q.order_by(CandidateProfileFact.fact_type, CandidateProfileFact.created_at))).scalars().all()
        return [S.FactOut.model_validate(r) for r in rows]


@router.post("/profile/facts", response_model=S.FactOut, status_code=201, tags=["profile"])
async def create_fact(body: S.FactCreate, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        fact = await users_svc.add_fact(s, p.user_id, body.fact_type, body.data)
        return S.FactOut.model_validate(fact)


@router.patch("/profile/facts/{fact_id}", response_model=S.FactOut, tags=["profile"])
async def patch_fact(fact_id: uuid.UUID, body: S.FactUpdate, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        fact = await get_owned(s, CandidateProfileFact, fact_id, p.user_id)
        if body.data is not None:
            fact.data, fact.source = body.data, "user_entered"
        if body.status is not None:
            fact.status = body.status
            fact.confirmed_at = datetime.now(tz=UTC) if body.status == "confirmed" else None
        out = S.FactOut.model_validate(fact)
    if out.fact_type == "skill":
        await matching_svc.rerank_all(p.user_id)
    return out


@router.delete("/profile/facts/{fact_id}", response_model=S.OkOut, tags=["profile"])
async def delete_fact(fact_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        await s.delete(await get_owned(s, CandidateProfileFact, fact_id, p.user_id))
    return S.OkOut()


# ------------------------------------------------------------------------------------------------ search configs
@router.get("/search-configs", response_model=list[S.SearchConfigOut], tags=["profile"])
async def list_search_configs(p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        rows = (await s.execute(select(SearchConfig).where(SearchConfig.user_id == p.user_id).order_by(SearchConfig.created_at))).scalars().all()
        return [S.SearchConfigOut.model_validate(r) for r in rows]


@router.post("/search-configs", response_model=S.SearchConfigOut, status_code=201, tags=["profile"])
async def create_search_config(body: S.SearchConfigIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        cfg = SearchConfig(user_id=p.user_id, **body.model_dump())
        s.add(cfg)
        await s.flush()
        return S.SearchConfigOut.model_validate(cfg)


@router.patch("/search-configs/{config_id}", response_model=S.SearchConfigOut, tags=["profile"])
async def patch_search_config(config_id: uuid.UUID, body: S.SearchConfigPatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        cfg = await get_owned(s, SearchConfig, config_id, p.user_id)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(cfg, k, v)
        await s.flush()
        return S.SearchConfigOut.model_validate(cfg)


@router.delete("/search-configs/{config_id}", response_model=S.OkOut, tags=["profile"])
async def delete_search_config(config_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        await s.delete(await get_owned(s, SearchConfig, config_id, p.user_id))
    return S.OkOut()


# ------------------------------------------------------------------------------------------------ settings
async def _settings_out(user: User) -> S.SettingsOut:
    s = get_settings()
    merged = {**users_svc.DEFAULT_SETTINGS, **(user.settings or {})}
    llm, emb = _provider_info()
    return S.SettingsOut(timezone=user.timezone, scheduler_local_time=merged["scheduler_local_time"],
                         auto_generate_outreach=bool(merged["auto_generate_outreach"]), notifications=merged["notifications"],
                         llm={**llm, "daily_call_budget": s.llm_daily_call_budget, "base_url": s.nvidia_base_url if s.llm_provider == "nvidia" else None},
                         embeddings=emb, search_provider=s.search_provider if s.search_api_key else "none",
                         scheduler={"trigger": "GitHub Actions cron 30 2 * * * (08:00 Asia/Kolkata)",
                                    "note": "Change the cron in .github/workflows/daily-discovery.yml to move the run."})


@router.get("/settings", response_model=S.SettingsOut, tags=["settings"])
async def get_settings_route(p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        return await _settings_out(await s.get(User, p.user_id))


@router.put("/settings", response_model=S.SettingsOut, tags=["settings"])
async def put_settings(body: S.SettingsIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        user = await s.get(User, p.user_id)
        data = body.model_dump(exclude_unset=True)
        if "timezone" in data and data["timezone"]:
            user.timezone = data.pop("timezone")
        user.settings = {**(user.settings or {}), **{k: v for k, v in data.items() if v is not None}}
        await s.flush()
        return await _settings_out(user)


# ------------------------------------------------------------------------------------------------ dashboard
@router.get("/dashboard/summary", tags=["dashboard"])
async def dashboard(p: Principal = Depends(get_principal)) -> dict:
    async with user_session(p.user_id) as s:
        return await dashboard_svc.summary(s, p.user_id)


# ------------------------------------------------------------------------------------------------ agent runs
def run_out(run: AgentRun, children: list[AgentRun] | None = None, approval: Approval | None = None) -> S.AgentRunOut:
    return S.AgentRunOut(
        id=run.id, workflow_name=run.workflow_name, status=run.status, current_node=run.current_node,
        progress=run.progress or [], output=run.output, error=run.error, created_at=run.created_at,
        started_at=run.started_at, completed_at=run.completed_at,
        subject=S.Subject(type=run.subject_type, id=run.subject_id) if run.subject_type and run.subject_id else None,
        children=[S.RunRef(workflow_id=c.id, workflow_name=c.workflow_name, status=c.status) for c in children or []],
        approval={"approval_id": str(approval.id), "action_type": approval.action_type, "payload_hash": approval.payload_hash,
                  "payload_preview": approval.payload_preview, "expires_at": approval.expires_at.isoformat()} if approval else None,
    )


@router.get("/agent-runs/{run_id}", response_model=S.AgentRunOut, tags=["runs"])
async def get_run(run_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        run = await get_owned(s, AgentRun, run_id, p.user_id)
        children = (await s.execute(select(AgentRun).where(AgentRun.parent_run_id == run.id).order_by(AgentRun.created_at))).scalars().all()
        approval = None
        if run.status == "awaiting_approval":
            approval = (await s.execute(select(Approval).where(Approval.agent_run_id == run.id, Approval.status == "pending")
                                        .order_by(Approval.created_at.desc()))).scalars().first()
        return run_out(run, list(children), approval)


@router.get("/agent-runs", response_model=list[S.AgentRunOut], tags=["runs"])
async def list_runs(status: str | None = None, workflow_name: str | None = None, limit: int = Query(25, le=100),
                    p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(AgentRun).where(AgentRun.user_id == p.user_id)
        if status:
            q = q.where(AgentRun.status == status)
        if workflow_name:
            q = q.where(AgentRun.workflow_name == workflow_name)
        rows = (await s.execute(q.order_by(AgentRun.created_at.desc()).limit(limit))).scalars().all()
        return [run_out(r) for r in rows]


@router.post("/agent-runs/{run_id}/retry", response_model=S.Accepted, status_code=202, tags=["runs"])
async def retry_run(run_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        run = await get_owned(s, AgentRun, run_id, p.user_id)
        subject = S.Subject(type=run.subject_type, id=run.subject_id) if run.subject_id else None
    task = await queue.retry_run(run_id, p.user_id)
    if task is None:
        raise NotFound("This run cannot be retried (it is not failed, or it was a child of a pipeline).")
    return S.Accepted(workflow_id=run_id, status="queued", status_url=f"/api/v1/agent-runs/{run_id}", subject=subject)


# ------------------------------------------------------------------------------------------------ notifications
@router.get("/notifications", response_model=list[S.NotificationOut], tags=["notifications"])
async def list_notifications(unread: bool = False, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(Notification).where(Notification.user_id == p.user_id)
        if unread:
            q = q.where(Notification.read_at.is_(None))
        rows = (await s.execute(q.order_by(Notification.created_at.desc()).limit(50))).scalars().all()
        return [S.NotificationOut.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=S.OkOut, tags=["notifications"])
async def read_notification(notification_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        n = await get_owned(s, Notification, notification_id, p.user_id)
        n.read_at = datetime.now(tz=UTC)
    return S.OkOut()

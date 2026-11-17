"""Data export and account deletion (FR-PROF-07; docs/SECURITY.md §9)."""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import system_session, user_session
from app.core.logging import get_logger
from app.integrations.storage import get_storage
from app.models import AgentRun, AuditEvent, Base, DeletedUser, ResumeVersion, User
from app.services import oauth as oauth_svc
from app.services.notifications import notify
from app.tasks.runner import TaskContext, handler

log = get_logger(__name__)
EXPORT_TTL = timedelta(hours=24)
_SKIP = {"scheduled_tasks", "oauth_states", "oauth_connections", "idempotency_keys", "companies", "skills"}


def _rowdict(obj) -> dict:
    out = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.key if hasattr(obj, col.key) else col.name, None)
        if col.name == "embedding":
            continue
        out[col.name] = val.isoformat() if hasattr(val, "isoformat") else (str(val) if isinstance(val, uuid.UUID | bytes) else val)
    return out


@handler("export_account")
async def export(ctx: TaskContext) -> dict:
    buf = io.BytesIO()
    storage = get_storage()
    async with user_session(ctx.user_id) as s:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for mapper in Base.registry.mappers:
                cls = mapper.class_
                table = cls.__table__.name
                if table in _SKIP or "user_id" not in cls.__table__.columns and table != "users":
                    continue
                q = select(cls).where(cls.id == ctx.user_id) if table == "users" else select(cls).where(cls.user_id == ctx.user_id)
                rows = (await s.execute(q)).scalars().all()
                z.writestr(f"data/{table}.json", json.dumps([_rowdict(r) for r in rows], indent=1, default=str))
            for v in (await s.execute(select(ResumeVersion).where(ResumeVersion.user_id == ctx.user_id))).scalars():
                try:
                    z.writestr(f"resumes/{v.resume_id}/v{v.version_number}-{v.original_filename}", await storage.get(v.storage_key))
                except Exception:
                    z.writestr(f"resumes/{v.resume_id}/v{v.version_number}-MISSING.txt", "File unavailable in storage.")
            z.writestr("README.txt", "CareerPilot AI export. data/*.json are your records; resumes/ are your original files.")
    key = f"{ctx.user_id}/exports/{ctx.agent_run_id}.zip"
    await storage.put(key, buf.getvalue(), "application/zip")
    async with user_session(ctx.user_id) as s:
        from app.services.common import audit

        await audit(s, ctx.user_id, "account.exported", "agent_run", ctx.agent_run_id)
    await notify(ctx.user_id, "daily_summary", "Your data export is ready", None, f"/api/v1/account/exports/{ctx.agent_run_id}")
    return {"export_key": key, "bytes": len(buf.getvalue())}


async def export_bytes(user_id: uuid.UUID, run_id: uuid.UUID) -> bytes:
    async with user_session(user_id) as s:
        run = await s.get(AgentRun, run_id)
        from app.core.errors import NotFound

        if run is None or run.user_id != user_id or run.workflow_name != "account_export" or run.status != "completed":
            raise NotFound()
        if run.completed_at and run.completed_at < datetime.now(tz=UTC) - EXPORT_TTL:
            raise NotFound("This export link expired. Create a new export.")
    return await get_storage().get(f"{user_id}/exports/{run_id}.zip")


async def delete_account(user_id: uuid.UUID, request_id: str | None) -> None:
    settings = get_settings()
    await oauth_svc.disconnect(user_id)
    async with user_session(user_id) as s:
        keys = list((await s.execute(select(ResumeVersion.storage_key).where(ResumeVersion.user_id == user_id))).scalars())
        runs = list((await s.execute(select(AgentRun.id).where(AgentRun.user_id == user_id))).scalars())
    storage = get_storage()
    try:  # everything the user ever stored lives under "<user_id>/" (resumes, exports — including old ones)
        await storage.delete_prefix(f"{user_id}/")
        await storage.delete(keys)
    except Exception as exc:
        log.warning("account_storage_delete_failed", error=type(exc).__name__)
    from app.graphs.runtime import delete_thread

    for r in runs:
        try:
            await delete_thread(r)
        except Exception as exc:
            log.warning("account_checkpoint_delete_failed", error=type(exc).__name__)
    async with system_session() as s:
        user = await s.get(User, user_id)
        if user is not None:
            await s.delete(user)
        if await s.get(DeletedUser, user_id) is None:
            s.add(DeletedUser(id=user_id))
        s.add(AuditEvent(user_id=None, actor="user", action="account.deleted", metadata_={"deleted_at": datetime.now(tz=UTC).isoformat()},
                         request_id=request_id))
    if settings.auth_mode == "supabase" and settings.supabase_url and settings.supabase_secret_key:
        key = settings.supabase_secret_key.get_secret_value()
        async with httpx.AsyncClient(timeout=15) as client:
            await client.delete(f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
                                headers={"Authorization": f"Bearer {key}", "apikey": key})

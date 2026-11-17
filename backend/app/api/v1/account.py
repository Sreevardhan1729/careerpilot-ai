"""Google integration and account data endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app.api.deps import forget_user, get_principal, request_id_var
from app.core.db import user_session
from app.core.security import Principal
from app.models import OAuthConnection
from app.schemas import api as S
from app.services import account as account_svc
from app.services import oauth as oauth_svc
from app.tasks import queue

router = APIRouter(tags=["account"])


@router.get("/integrations")
async def integrations(p: Principal = Depends(get_principal)) -> dict:
    from app.core.config import get_settings

    async with user_session(p.user_id) as s:
        c = (await s.execute(select(OAuthConnection).where(OAuthConnection.user_id == p.user_id))).scalars().first()
    return {"google": {"configured": bool(get_settings().google_oauth_client_id), "connected": bool(c and c.status == "active"),
                       "status": c.status if c else None, "account_email": c.account_email if c else None,
                       "scopes": c.scopes if c else []}}


@router.get("/integrations/google/authorize")
async def google_authorize(p: Principal = Depends(get_principal)) -> dict:
    return {"url": await oauth_svc.authorize_url(p.user_id)}


@router.get("/integrations/google/callback", include_in_schema=False)
async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error or not code or not state:
        return RedirectResponse(oauth_svc.frontend_redirect("denied"))
    try:
        await oauth_svc.callback(code, state)
    except Exception:
        return RedirectResponse(oauth_svc.frontend_redirect("error"))
    return RedirectResponse(oauth_svc.frontend_redirect("connected"))


@router.delete("/integrations/google", response_model=S.OkOut)
async def google_disconnect(p: Principal = Depends(get_principal)):
    await oauth_svc.disconnect(p.user_id)
    return S.OkOut()


@router.post("/account/export", status_code=202, response_model=S.Accepted)
async def export(p: Principal = Depends(get_principal)):
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="export_account", payload={}, priority=3)
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}")


@router.get("/account/exports/{run_id}")
async def download_export(run_id: uuid.UUID, p: Principal = Depends(get_principal)):
    data = await account_svc.export_bytes(p.user_id, run_id)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="careerpilot-export-{run_id}.zip"'})


@router.delete("/account", response_model=S.OkOut)
async def delete_account(body: S.AccountDeleteIn, p: Principal = Depends(get_principal)):
    await account_svc.delete_account(p.user_id, request_id_var.get())
    forget_user(p.user_id)
    return S.OkOut()

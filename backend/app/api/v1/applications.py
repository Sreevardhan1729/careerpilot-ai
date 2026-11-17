"""Application preparation & tracking endpoints (Phase 5)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import get_principal, idempotency_key
from app.core.db import user_session
from app.core.errors import ValidationFailed
from app.core.security import Principal
from app.graphs import application_preparation as prep
from app.models import Application, Company, Job
from app.schemas import api as S
from app.services import applications as svc
from app.services.common import get_owned, idempotent_lookup, idempotent_store, request_hash
from app.tasks import queue

router = APIRouter(prefix="/applications", tags=["applications"])


async def _out(s, app: Application) -> S.ApplicationOut:
    job = await s.get(Job, app.job_id)
    company = await s.get(Company, app.company_id) if app.company_id else None
    out = S.ApplicationOut.model_validate(app)
    out.job_title, out.company_name = (job.title if job else None), (company.name if company else None)
    return out


@router.post("/prepare", status_code=202, response_model=S.Accepted)
async def prepare(body: S.PrepareIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        app = await svc.get_or_create(s, p.user_id, body.job_id)
        app_id = app.id
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="prepare_application", priority=1,
                                    subject_type="application", subject_id=app_id,
                                    payload={"application_id": str(app_id),
                                             "resume_version_id": str(body.resume_version_id) if body.resume_version_id else None,
                                             "questions": body.questions})
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type="application", id=app_id))


@router.get("", response_model=list[S.ApplicationOut])
async def list_applications(status: str | None = None, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(Application).where(Application.user_id == p.user_id)
        if status:
            q = q.where(Application.status == status)
        return [await _out(s, a) for a in (await s.execute(q.order_by(Application.updated_at.desc()))).scalars().all()]


@router.get("/{application_id}", response_model=S.ApplicationOut)
async def get_application(application_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        return await _out(s, await get_owned(s, Application, application_id, p.user_id))


@router.patch("/{application_id}", response_model=S.ApplicationOut)
async def patch_application(application_id: uuid.UUID, body: S.ApplicationPatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        app = await get_owned(s, Application, application_id, p.user_id)
        data = body.model_dump(exclude_unset=True)
        if "status" in data and data["status"]:
            await svc.set_status(s, app, data["status"])
        if "notes" in data:
            app.notes = data["notes"]
        if "follow_up_date" in data:
            app.follow_up_date = data["follow_up_date"]
            await svc.event(s, app, "follow_up_set", None, None, date=str(data["follow_up_date"]))
        await s.flush()
        return await _out(s, app)


@router.post("/{application_id}/approve")
async def approve(application_id: uuid.UUID, body: S.ApproveIn, p: Principal = Depends(get_principal),
                  key: str | None = Depends(idempotency_key)) -> dict:
    if not key:
        raise ValidationFailed("Idempotency-Key header is required for approvals.")
    raw = body.model_dump(mode="json")
    async with user_session(p.user_id) as s:
        await get_owned(s, Application, application_id, p.user_id)
        hit = await idempotent_lookup(s, p.user_id, key, "applications.approve", request_hash(raw))
    if hit:
        return hit[1]
    result = await prep.approve(p.user_id, application_id, body.approval_id, body.payload_hash)
    async with user_session(p.user_id) as s:
        await idempotent_store(s, p.user_id, key, "applications.approve", request_hash(raw), 200, result)
    return result


@router.post("/{application_id}/confirm-submission", response_model=S.ApplicationOut)
async def confirm(application_id: uuid.UUID, body: S.ConfirmSubmissionIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        app = await get_owned(s, Application, application_id, p.user_id)
        await svc.confirm_submission(s, p.user_id, app, body.evidence_type, body.detail)
        await s.flush()
        return await _out(s, app)

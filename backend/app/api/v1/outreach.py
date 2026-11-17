"""Outreach, approvals and resume-optimisation endpoints (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import get_principal, idempotency_key, rate_limit
from app.core.db import user_session
from app.core.errors import ValidationFailed
from app.core.security import Principal
from app.models import Approval, Job, Outreach, Person, Resume
from app.schemas import api as S
from app.services import approvals as approvals_svc
from app.services import outreach as svc
from app.services.common import audit, get_owned, idempotent_lookup, idempotent_store, request_hash
from app.tasks import queue

router = APIRouter(tags=["outreach"])


@router.post("/outreach/generate", status_code=202, response_model=S.Accepted)
async def generate(body: S.OutreachGenerateIn, p: Principal = Depends(rate_limit("llm_enqueue"))):
    async with user_session(p.user_id) as s:
        await get_owned(s, Job, body.job_id, p.user_id)
        for pid in body.person_ids or []:
            await get_owned(s, Person, pid, p.user_id)
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="generate_outreach", priority=1, subject_type="job", subject_id=body.job_id,
                                    payload={"job_id": str(body.job_id), "person_ids": [str(i) for i in body.person_ids or []] or None,
                                             "message_types": list(body.message_types), "resume_id": str(body.resume_id) if body.resume_id else None})
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type="job", id=body.job_id))


@router.get("/outreach", response_model=list[S.OutreachOut])
async def list_outreach(job_id: uuid.UUID | None = None, person_id: uuid.UUID | None = None, status: str | None = None,
                        p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(Outreach).where(Outreach.user_id == p.user_id)
        if job_id:
            q = q.where(Outreach.job_id == job_id)
        if person_id:
            q = q.where(Outreach.person_id == person_id)
        q = q.where(Outreach.status == status) if status else q.where(Outreach.status != "discarded")
        return [S.OutreachOut.model_validate(o) for o in (await s.execute(q.order_by(Outreach.created_at.desc()).limit(200))).scalars()]


@router.post("/outreach/drafts", response_model=S.OutreachOut, status_code=201)
async def save_draft(body: S.OutreachDraftIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        o = await svc.create_manual(s, p.user_id, body.job_id, body.person_id, body.message_type, body.subject, body.body)
        return S.OutreachOut.model_validate(o)


@router.patch("/outreach/{outreach_id}", response_model=S.OutreachOut)
async def patch_outreach(outreach_id: uuid.UUID, body: S.OutreachPatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, p.user_id)
        if o.status in svc.SENT_STATUSES:
            raise ValidationFailed("Sent messages can't be edited.")
        if body.discard:
            o.status = "discarded"
        else:
            if body.subject is not None:
                o.subject = body.subject
            if body.body is not None:
                o.body = body.body
            o.status = "edited"
            await svc.recheck(s, p.user_id, o)
        await s.flush()
        return S.OutreachOut.model_validate(o)


@router.post("/outreach/{outreach_id}/gmail-draft", response_model=S.OutreachOut)
async def gmail_draft(outreach_id: uuid.UUID, p: Principal = Depends(get_principal)):
    return S.OutreachOut.model_validate(await svc.create_gmail_draft(p.user_id, outreach_id))


@router.post("/outreach/{outreach_id}/request-approval", response_model=S.ApprovalOut)
async def request_approval(outreach_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, p.user_id)
        a = await svc.request_send_approval(s, p.user_id, o)
        return S.ApprovalOut(approval_id=a.id, action_type=a.action_type, status=a.status, expires_at=a.expires_at,
                             payload_hash=a.payload_hash, payload_preview=a.payload_preview, reference_type=a.reference_type,
                             reference_id=a.reference_id)


@router.post("/outreach/{outreach_id}/approve")
async def approve(outreach_id: uuid.UUID, body: S.ApproveIn, p: Principal = Depends(get_principal),
                  key: str | None = Depends(idempotency_key)) -> dict:
    if not key:
        raise ValidationFailed("Idempotency-Key header is required for approvals.")
    raw = body.model_dump(mode="json")
    async with user_session(p.user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, p.user_id)
        if o.channel != "email":
            from app.core.errors import ApprovalRequired

            raise ApprovalRequired("LinkedIn messages are sent manually.", details={"reason": "manual_channel"})
        hit = await idempotent_lookup(s, p.user_id, key, "outreach.approve", request_hash(raw))
    if hit:
        return hit[1]
    result = await svc.approve_and_send(p.user_id, outreach_id, body.approval_id, body.payload_hash)
    out = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in result.items()}
    async with user_session(p.user_id) as s:
        await idempotent_store(s, p.user_id, key, "outreach.approve", request_hash(raw), 200, out)
    return out


@router.post("/outreach/{outreach_id}/mark-sent", response_model=S.OutreachOut)
async def mark_sent(outreach_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, p.user_id)
        if o.channel != "linkedin":
            raise ValidationFailed("Only LinkedIn messages are marked as sent manually; email uses the approval flow.")
        o.status, o.sent_at = "manually_sent", datetime.now(tz=UTC)
        if o.person_id:
            person = await s.get(Person, o.person_id)
            if person and person.contact_status == "new":
                person.contact_status = "contacted"
        await audit(s, p.user_id, "outreach.manually_sent", "outreach", o.id)
        await s.flush()
        return S.OutreachOut.model_validate(o)


@router.get("/approvals", response_model=list[S.ApprovalOut])
async def list_approvals(status: str | None = None, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(Approval).where(Approval.user_id == p.user_id)
        if status:
            q = q.where(Approval.status == status)
        rows = (await s.execute(q.order_by(Approval.created_at.desc()).limit(100))).scalars().all()
        return [S.ApprovalOut(approval_id=a.id, action_type=a.action_type, status=a.status, expires_at=a.expires_at,
                              payload_hash=a.payload_hash, payload_preview=a.payload_preview, reference_type=a.reference_type,
                              reference_id=a.reference_id) for a in rows]


@router.post("/approvals/{approval_id}/reject", response_model=S.OkOut)
async def reject(approval_id: uuid.UUID, p: Principal = Depends(get_principal)):
    """Reject a pending approval and settle what it was gating (version → rejected, application → back to draft)."""
    from app.models import AgentRun, Application, ResumeVersion
    from app.services import applications as app_svc

    async with user_session(p.user_id) as s:
        a = await get_owned(s, Approval, approval_id, p.user_id)
        await approvals_svc.decide(s, p.user_id, approval_id, a.payload_hash, approve=False)
        if a.action_type == "activate_resume_version":
            version = await s.get(ResumeVersion, a.reference_id)
            if version is not None and version.approval_status == "pending_approval":
                version.approval_status = "rejected"
        elif a.action_type == "submit_application":
            app = await s.get(Application, a.reference_id)
            if app is not None and app.status == "awaiting_approval":
                await app_svc.set_status(s, app, "draft_prepared", system=True)
            run = await s.get(AgentRun, a.agent_run_id) if a.agent_run_id else None
            if run is not None and run.status == "awaiting_approval":
                run.status = "cancelled"
    return S.OkOut()


@router.post("/resumes/{resume_id}/optimize", status_code=202, response_model=S.Accepted)
async def optimize(resume_id: uuid.UUID, job_id: uuid.UUID, p: Principal = Depends(rate_limit("llm_enqueue"))):
    async with user_session(p.user_id) as s:
        await get_owned(s, Resume, resume_id, p.user_id)
        await get_owned(s, Job, job_id, p.user_id)
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="optimize_resume", priority=1, subject_type="resume", subject_id=resume_id,
                                    payload={"resume_id": str(resume_id), "job_id": str(job_id)})
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type="resume", id=resume_id))

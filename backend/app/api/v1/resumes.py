"""Resume library endpoints (spec §8)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import get_principal, idempotency_key, rate_limit
from app.core.config import get_settings
from app.core.db import user_session
from app.core.security import Principal
from app.integrations.storage import get_storage
from app.models import AgentRun, Job, Resume, ResumeVersion
from app.schemas import api as S
from app.schemas.llm.resume import ResumeParsed
from app.services import resumes as svc
from app.services.common import audit, get_owned
from app.tasks import queue

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/upload", status_code=202, response_model=S.Accepted)
async def upload(file: UploadFile = File(...), label: str | None = Form(default=None),
                 p: Principal = Depends(rate_limit("upload", capacity=20))):
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    resume, _version, run_id = await svc.create_upload(p.user_id, data, file.filename or "resume", label)
    return S.Accepted(workflow_id=run_id, status="queued", status_url=f"/api/v1/agent-runs/{run_id}",
                      subject=S.Subject(type="resume", id=resume.id))


@router.get("", response_model=list[S.ResumeOut])
async def list_resumes(p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        rows = (await s.execute(select(Resume).where(Resume.user_id == p.user_id).order_by(Resume.created_at))).scalars().all()
        return [S.ResumeOut.model_validate(r) for r in rows]


@router.get("/{resume_id}", response_model=S.ResumeDetail)
async def get_resume(resume_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        r = await get_owned(s, Resume, resume_id, p.user_id)
        versions = (await s.execute(select(ResumeVersion).where(ResumeVersion.resume_id == r.id)
                                    .order_by(ResumeVersion.version_number))).scalars().all()
        current = next((v for v in versions if v.id == r.current_version_id), None)
        run = (await s.execute(select(AgentRun).where(AgentRun.subject_type == "resume", AgentRun.subject_id == r.id)
                               .order_by(AgentRun.created_at.desc()).limit(1))).scalars().first()
        return S.ResumeDetail(**S.ResumeOut.model_validate(r).model_dump(),
                              current_version=S.ResumeVersionOut.model_validate(current) if current else None,
                              parsed_data=current.parsed_data if current else None,
                              versions=[S.ResumeVersionOut.model_validate(v) for v in versions],
                              latest_run=S.RunRef(workflow_id=run.id, workflow_name=run.workflow_name, status=run.status) if run else None)


@router.patch("/{resume_id}", response_model=S.ResumeOut)
async def patch_resume(resume_id: uuid.UUID, body: S.ResumePatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        r = await get_owned(s, Resume, resume_id, p.user_id)
        if body.label is not None:
            r.label = body.label
        if body.category is not None:
            r.category = body.category
        if body.is_default:
            await svc.set_default(s, p.user_id, r.id)
        await s.flush()
        await s.refresh(r)
        return S.ResumeOut.model_validate(r)


@router.put("/{resume_id}/versions/{version_id}/parsed-data", response_model=S.ResumeDetail)
async def put_parsed(resume_id: uuid.UUID, version_id: uuid.UUID, body: ResumeParsed, p: Principal = Depends(get_principal)):
    """Save user corrections (authoritative). The original file is untouched; chunks and embeddings are rebuilt."""
    from app.core.errors import NotFound
    from app.domain.skills import get_taxonomy

    async with user_session(p.user_id) as s:
        v = await get_owned(s, ResumeVersion, version_id, p.user_id)
        if v.resume_id != resume_id:
            raise NotFound()
        text, page_count = v.extracted_text or "", v.page_count
        await audit(s, p.user_id, "resume.parsed_data_corrected", "resume_version", version_id)
    tax = get_taxonomy()
    for sk in body.skills:
        sk.name = tax.normalize_name(sk.name)
    await svc.persist_ingestion(p.user_id, resume_id, version_id, text, page_count, body, [], "user_corrected",
                                origin="user_corrected")
    async with user_session(p.user_id) as s:
        (await get_owned(s, Resume, resume_id, p.user_id)).status = "parsed"
    return await get_resume(resume_id, p)


@router.get("/{resume_id}/versions/{version_id}/download")
async def download(resume_id: uuid.UUID, version_id: uuid.UUID, p: Principal = Depends(get_principal)):
    storage = get_storage()
    async with user_session(p.user_id) as s:
        v = await get_owned(s, ResumeVersion, version_id, p.user_id)
        await audit(s, p.user_id, "resume.downloaded", "resume_version", version_id)
    if v.resume_id != resume_id:
        from app.core.errors import NotFound

        raise NotFound()
    if storage.supports_signed_urls:
        url = await storage.signed_url(v.storage_key, 60, v.original_filename)
        return JSONResponse(S.DownloadOut(url=url, filename=v.original_filename).model_dump())
    data = await storage.get(v.storage_key)
    return Response(content=data, media_type=v.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="{v.original_filename}"'})


@router.delete("/{resume_id}", response_model=S.OkOut)
async def delete_resume(resume_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        r = await get_owned(s, Resume, resume_id, p.user_id)
        keys = (await s.execute(select(ResumeVersion.storage_key).where(ResumeVersion.resume_id == r.id))).scalars().all()
        await s.execute(Job.__table__.update().where(Job.best_resume_id == r.id).values(best_resume_id=None))
        r.current_version_id = None
        await s.flush()
        await s.delete(r)
        await audit(s, p.user_id, "resume.deleted", "resume", resume_id)
    await get_storage().delete(list(keys))
    return S.OkOut()


@router.post("/{resume_id}/versions", status_code=201, response_model=S.TailoredVersionOut)
async def create_version(resume_id: uuid.UUID, body: S.TailoredVersionIn, p: Principal = Depends(get_principal)):
    """Create a tailored DOCX version from accepted suggestions. It stays inactive until approved (activate)."""
    from app.services import resume_versions

    out = await resume_versions.create_tailored(
        p.user_id, resume_id, base_version_id=body.base_version_id, job_id=body.job_id,
        changes=[c.model_dump() for c in body.changes], skill_order=body.skill_order, change_summary=body.change_summary)
    a = out["approval"]
    return S.TailoredVersionOut(
        version=S.ResumeVersionOut.model_validate(out["version"]),
        approval=S.ApprovalOut(approval_id=a.id, action_type=a.action_type, status=a.status, expires_at=a.expires_at,
                               payload_hash=a.payload_hash, payload_preview=a.payload_preview,
                               reference_type=a.reference_type, reference_id=a.reference_id))


@router.post("/{resume_id}/versions/{version_id}/activate", response_model=S.ActivationOut)
async def activate_version(resume_id: uuid.UUID, version_id: uuid.UUID, body: S.ApproveIn, p: Principal = Depends(get_principal),
                           key: str | None = Depends(idempotency_key)):
    from app.core.errors import ValidationFailed
    from app.services import resume_versions

    if not key:
        raise ValidationFailed("Idempotency-Key header is required for approvals.")
    return await resume_versions.activate(p.user_id, resume_id, version_id, body.approval_id, body.payload_hash)


@router.post("/match/{job_id}", status_code=202, response_model=S.Accepted)
async def match(job_id: uuid.UUID, p: Principal = Depends(rate_limit("llm_enqueue"))):
    async with user_session(p.user_id) as s:
        await get_owned(s, Job, job_id, p.user_id)
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="match_resumes", payload={"job_id": str(job_id)}, priority=1,
                                    subject_type="job", subject_id=job_id)
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type="job", id=job_id))

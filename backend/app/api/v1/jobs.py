"""Job intelligence endpoints (spec §8)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import get_principal, idempotency_key, rate_limit
from app.core.config import get_settings
from app.core.db import user_session
from app.core.errors import ValidationFailed
from app.core.security import Principal
from app.integrations.parsing.documents import extract_document, validate_upload
from app.models import (
    AgentRun,
    Application,
    Company,
    Job,
    JobEvidence,
    JobSkill,
    JobSourceRecord,
    Resume,
    ResumeChunk,
)
from app.schemas import api as S
from app.services import jobs as svc
from app.services.common import get_owned, idempotent_lookup, idempotent_store, request_hash
from app.tasks import queue

router = APIRouter(prefix="/jobs", tags=["jobs"])


def accepted(run: AgentRun, subject_type: str, subject_id: uuid.UUID) -> dict:
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type=subject_type, id=subject_id)).model_dump(mode="json")


async def _enqueue_analysis(user_id: uuid.UUID, job_id: uuid.UUID, company_hint: str | None = None) -> AgentRun:
    run, _, _ = await queue.enqueue(user_id=user_id, task_type="analyze_job", priority=1,
                                    payload={"job_id": str(job_id), "company_hint": company_hint},
                                    idempotency_key=f"analyze_job:{job_id}", subject_type="job", subject_id=job_id)
    return run


async def _respond(user_id: uuid.UUID, key: str | None, endpoint: str, body: dict, job: Job, dedup: bool,
                   company_hint: str | None = None) -> JSONResponse:
    if dedup:
        status, payload = 200, S.Deduplicated(job_id=job.id).model_dump(mode="json")
    else:
        run = await _enqueue_analysis(user_id, job.id, company_hint)
        status, payload = 202, accepted(run, "job", job.id)
    async with user_session(user_id) as s:
        await idempotent_store(s, user_id, key, endpoint, request_hash(body), status, payload)
    return JSONResponse(payload, status_code=status)


async def _replay(user_id: uuid.UUID, key: str | None, endpoint: str, body: dict) -> JSONResponse | None:
    async with user_session(user_id) as s:
        hit = await idempotent_lookup(s, user_id, key, endpoint, request_hash(body))
    return JSONResponse(hit[1], status_code=hit[0]) if hit else None


@router.post("/analyze", responses={200: {"model": S.Deduplicated}, 202: {"model": S.Accepted}})
async def analyze(body: S.AnalyzeTextIn, p: Principal = Depends(rate_limit("llm_enqueue")), key: str | None = Depends(idempotency_key)):
    raw = body.model_dump(mode="json")
    if (replay := await _replay(p.user_id, key, "jobs.analyze", raw)) is not None:
        return replay
    if body.input_type == "manual":
        if not body.manual_fields:
            raise ValidationFailed("manual_fields is required when input_type is 'manual'.")
        text = svc.manual_to_text(body.manual_fields.model_dump())
        job, dedup = await svc.create_job_from_text(p.user_id, text, input_type="manual", source_url=body.source_url)
    else:
        if not body.text:
            raise ValidationFailed("text is required.")
        job, dedup = await svc.create_job_from_text(p.user_id, body.text, input_type="text", source_url=body.source_url)
    return await _respond(p.user_id, key, "jobs.analyze", raw, job, dedup, body.company_hint)


@router.post("/analyze-url", responses={200: {"model": S.Deduplicated}, 202: {"model": S.Accepted}})
async def analyze_url(body: S.AnalyzeUrlIn, p: Principal = Depends(rate_limit("llm_enqueue")), key: str | None = Depends(idempotency_key)):
    raw = body.model_dump(mode="json")
    if (replay := await _replay(p.user_id, key, "jobs.analyze_url", raw)) is not None:
        return replay
    job, dedup = await svc.create_job_from_url(p.user_id, str(body.url))
    return await _respond(p.user_id, key, "jobs.analyze_url", raw, job, dedup)


@router.post("/analyze-file", responses={200: {"model": S.Deduplicated}, 202: {"model": S.Accepted}})
async def analyze_file(file: UploadFile = File(...), source_url: str | None = Form(default=None),
                       p: Principal = Depends(rate_limit("llm_enqueue"))):
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    info = validate_upload(data, s.max_upload_mb, s.max_resume_pages)
    doc = extract_document(data, info.kind)
    job, dedup = await svc.create_job_from_text(p.user_id, doc.text, input_type=info.kind, source_url=source_url)
    return await _respond(p.user_id, None, "jobs.analyze_file", {}, job, dedup)


async def _list_items(s, user_id: uuid.UUID, rows: list[tuple[Job, Company | None]]) -> list[S.JobListItem]:
    ids = [j.id for j, _ in rows]
    sources = await svc.job_sources(s, ids)
    resume_ids = {j.best_resume_id for j, _ in rows if j.best_resume_id}
    labels = dict((await s.execute(select(Resume.id, Resume.label).where(Resume.id.in_(resume_ids)))).all()) if resume_ids else {}
    apps = set((await s.execute(select(Application.job_id).where(Application.job_id.in_(ids)))).scalars().all()) if ids else set()
    return [_item(j, c, sources.get(j.id, []), labels, j.id in apps) for j, c in rows]


def _item(j: Job, c: Company | None, sources: list[str], labels: dict, has_app: bool, cls=S.JobListItem, **extra):
    num = lambda v: float(v) if v is not None else None  # noqa: E731
    return cls(
        id=j.id, title=j.title, company=S.CompanyOut(id=c.id, name=c.name, domain=c.domain) if c else None,
        locations=j.locations or [], work_mode=j.work_mode, employment_type=j.employment_type, seniority=j.seniority,
        experience=S.ExperienceOut(min_years=num(j.experience_min_years), max_years=num(j.experience_max_years),
                                   explicit=j.experience_explicit, evidence=j.experience_evidence),
        salary=S.SalaryOut(minimum=num(j.salary_min), maximum=num(j.salary_max), currency=j.salary_currency,
                           period=j.salary_period, source_type=j.salary_source_type, is_base=j.salary_is_base,
                           source_url=j.salary_source_url),
        job_score=num(j.job_score), priority=j.priority, match_score=num(j.match_score),
        best_resume=S.ResumeRef(id=j.best_resume_id, label=labels.get(j.best_resume_id, "Resume")) if j.best_resume_id else None,
        posted_at=j.posted_at, created_at=j.created_at, sources=sources, status=j.status, saved=j.saved, has_application=has_app,
        input_type=j.input_type, **extra)


@router.get("", response_model=S.Page[S.JobListItem])
async def list_jobs(
    q: str | None = None, role: str | None = None, company_id: uuid.UUID | None = None, location: str | None = None,
    work_mode: list[str] | None = Query(None), experience_max: float | None = None, experience_known: bool = False,
    salary_min: float | None = None, salary_disclosed: bool = False, source: list[str] | None = Query(None),
    skills: list[str] | None = Query(None), posted_after: date | None = None, min_score: float | None = None,
    priority: list[str] | None = Query(None), status: str | None = None, saved: bool | None = None, sort: str = "-job_score",
    limit: int = Query(25, ge=1, le=100), cursor: str | None = None, p: Principal = Depends(get_principal),
):
    filters = dict(q=q, role=role, company_id=company_id, location=location, work_mode=work_mode, experience_max=experience_max,
                   experience_known=experience_known, salary_min=salary_min, salary_disclosed=salary_disclosed, source=source,
                   skills=skills, posted_after=posted_after, min_score=min_score, priority=priority, status=status, saved=saved,
                   sort=sort)
    async with user_session(p.user_id) as s:
        rows, nxt = await svc.list_jobs(s, p.user_id, filters, limit, cursor)
        return S.Page[S.JobListItem](items=await _list_items(s, p.user_id, rows), next_cursor=nxt)


@router.get("/{job_id}", response_model=S.JobDetail)
async def get_job(job_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        job = await get_owned(s, Job, job_id, p.user_id)
        company = await s.get(Company, job.company_id) if job.company_id else None
        skills = (await s.execute(select(JobSkill).where(JobSkill.job_id == job_id)
                                  .order_by(JobSkill.importance, JobSkill.normalized_name))).scalars().all()
        evidence = (await s.execute(select(JobEvidence).where(JobEvidence.job_id == job_id))).scalars().all()
        records = (await s.execute(select(JobSourceRecord).where(JobSourceRecord.job_id == job_id)
                                   .order_by(JobSourceRecord.collected_at))).scalars().all()
        matches = await svc.job_matches(s, job_id)
        labels = dict((await s.execute(select(Resume.id, Resume.label).where(Resume.user_id == p.user_id))).all())
        has_app = (await s.execute(select(Application.id).where(Application.job_id == job_id))).first() is not None
        run = (await s.execute(select(AgentRun).where(AgentRun.subject_type == "job", AgentRun.subject_id == job_id,
                                                      AgentRun.user_id == p.user_id)
                               .order_by(AgentRun.created_at.desc()).limit(1))).scalars().first()
        return _item(
            job, company, sorted({r.source_name for r in records}), labels, has_app, cls=S.JobDetail,
            department=job.department, description_text=job.description_text, responsibilities=job.responsibilities or [],
            technical_requirements=job.technical_requirements or [], soft_skills=job.soft_skills or [],
            education=job.education or [], business_domain=job.business_domain, application_deadline=job.application_deadline,
            application_url=job.application_url, source_url=job.source_url, posted_by=job.posted_by,
            hiring_expectations=job.hiring_expectations, missing_information=job.missing_information or [],
            skills=[S.JobSkillOut(name=k.normalized_name, category=k.category, importance=k.importance, evidence_text=k.evidence_text,
                                  evidence_verified=k.evidence_verified, confidence=float(k.confidence) if k.confidence is not None else None,
                                  skill_id=k.skill_id) for k in skills],
            evidence=[S.JobEvidenceOut(field=e.field, value=e.value, evidence_text=e.evidence_text, explicit=e.explicit,
                                       verified=e.verified, confidence=float(e.confidence) if e.confidence is not None else None)
                      for e in evidence],
            source_records=[S.SourceRecordOut.model_validate(r) for r in records],
            job_score_breakdown=job.job_score_breakdown,
            match_summary=[S.MatchSummary(resume_id=m.resume_id, label=labels.get(m.resume_id, "Resume"), score=float(m.score), rank=m.rank)
                           for m in matches[:3]],
            latest_run=S.RunRef(workflow_id=run.id, workflow_name=run.workflow_name, status=run.status) if run else None,
            analysis_method=(job.prompt_version or "").split("@")[0] if job.prompt_version else None, model_id=job.model_id,
        )


@router.patch("/{job_id}", response_model=S.JobListItem)
async def patch_job(job_id: uuid.UUID, body: S.JobPatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        job = await get_owned(s, Job, job_id, p.user_id)
        if body.saved is not None:
            job.saved = body.saved
        if body.archived is not None:
            job.status = "archived" if body.archived else ("analyzed" if job.analyzed_at else "queued")
        if body.application_url is not None:
            job.application_url = body.application_url or None
        await s.flush()
        company = await s.get(Company, job.company_id) if job.company_id else None
        return (await _list_items(s, p.user_id, [(job, company)]))[0]


@router.get("/{job_id}/matches", response_model=S.MatchesOut)
async def get_matches(job_id: uuid.UUID, p: Principal = Depends(get_principal)):
    from app.domain.matching import load_scoring_config

    async with user_session(p.user_id) as s:
        job = await get_owned(s, Job, job_id, p.user_id)
        matches = await svc.job_matches(s, job_id)
        resumes = {r.id: r for r in (await s.execute(select(Resume).where(Resume.user_id == p.user_id))).scalars().all()}
        from app.models import ResumeVersion

        numbers = dict((await s.execute(select(ResumeVersion.id, ResumeVersion.version_number)
                                        .where(ResumeVersion.user_id == p.user_id))).all())
        refs = {ref.removeprefix("chunk:") for m in matches for c in m.components.values() for ref in c.get("evidence_refs", [])
                if ref.startswith("chunk:")}
        chunks = {}
        if refs:
            ids = [uuid.UUID(r) for r in refs]
            chunks = {f"chunk:{c.id}": c.content for c in (await s.execute(select(ResumeChunk).where(ResumeChunk.id.in_(ids)))).scalars()}
        items = []
        for m in matches:
            r = resumes.get(m.resume_id)
            items.append(S.MatchItem(
                rank=m.rank, resume={"id": str(m.resume_id), "label": r.label if r else "Resume", "version_id": str(m.resume_version_id),
                                     "version_number": numbers.get(m.resume_version_id)},
                score=float(m.score), components=m.components,
                mandatory_coverage=float(m.mandatory_coverage) if m.mandatory_coverage is not None else None,
                preferred_coverage=float(m.preferred_coverage) if m.preferred_coverage is not None else None,
                skill_breakdown=m.skill_breakdown,
                missing_skills=[b for b in m.skill_breakdown if b["status"] in ("no_evidence", "profile_only", "confirmed_missing")],
                weakly_highlighted_skills=[b["skill"] for b in m.skill_breakdown if b["status"] == "listed_only"],
                relevant_projects=m.relevant_projects, relevant_experience=m.relevant_experience, suggestions=m.suggestions,
                explanation=m.explanation, limitations=m.limitations, is_best=m.is_best))
        return S.MatchesOut(job_id=job.id, scoring_config_version=load_scoring_config().version, best_resume_id=job.best_resume_id,
                            items=items, evidence=chunks)

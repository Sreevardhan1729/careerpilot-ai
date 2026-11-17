"""People & recruiter intelligence endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import get_principal, rate_limit
from app.core.db import user_session
from app.core.security import Principal
from app.models import AgentRun, Company, Job, Person
from app.schemas import api as S
from app.services import people as svc
from app.services.common import get_owned
from app.tasks import queue

router = APIRouter(tags=["people"])


@router.get("/jobs/{job_id}/people", response_model=S.JobPeopleOut)
async def job_people(job_id: uuid.UUID, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        view = await svc.job_people_view(s, p.user_id, job_id)
        run = (await s.execute(select(AgentRun).where(AgentRun.user_id == p.user_id, AgentRun.workflow_name == "people_discovery",
                                                      AgentRun.subject_id == job_id).order_by(AgentRun.created_at.desc()).limit(1))).scalars().first()
        out = (run.output or {}) if run else {}
        c = view["company"]
        items = [S.JobPersonOut(**{**i, "evidence": [S.EvidenceItemOut.model_validate(e) for e in i["evidence"]]}) for i in view["items"]]
        verified = len(items)
        return S.JobPeopleOut(job_id=job_id, company=S.CompanyOut(id=c.id, name=c.name, domain=c.domain) if c else None,
                              verified_count=verified, unavailable_count=max(0, svc.TARGET - verified),
                              coverage_note=out.get("coverage_note"), items=items,
                              latest_run=S.RunRef(workflow_id=run.id, workflow_name=run.workflow_name, status=run.status) if run else None)


@router.post("/jobs/{job_id}/people/discover", status_code=202, response_model=S.Accepted)
async def discover_people(job_id: uuid.UUID, p: Principal = Depends(rate_limit("llm_enqueue"))):
    async with user_session(p.user_id) as s:
        await get_owned(s, Job, job_id, p.user_id)
    run, _, _ = await queue.enqueue(user_id=p.user_id, task_type="discover_people", payload={"job_id": str(job_id)}, priority=1,
                                    subject_type="job", subject_id=job_id)
    return S.Accepted(workflow_id=run.id, status=run.status, status_url=f"/api/v1/agent-runs/{run.id}",
                      subject=S.Subject(type="job", id=job_id))


def _person_out(person: Person, company: Company | None) -> S.PersonOut:
    out = S.PersonOut.model_validate(person)
    out.company = S.CompanyOut(id=company.id, name=company.name, domain=company.domain) if company else None
    return out


@router.get("/people", response_model=list[S.PersonOut])
async def list_people(company_id: uuid.UUID | None = None, contact_status: str | None = None, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        q = select(Person, Company).outerjoin(Company, Company.id == Person.company_id).where(Person.user_id == p.user_id)
        if company_id:
            q = q.where(Person.company_id == company_id)
        if contact_status:
            q = q.where(Person.contact_status == contact_status)
        return [_person_out(pp, c) for pp, c in (await s.execute(q.order_by(Person.created_at.desc()).limit(500))).all()]


@router.post("/people", response_model=S.PersonOut, status_code=201)
async def add_person(body: S.PersonIn, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        person = await svc.add_manual(s, p.user_id, body.name, body.linkedin_url, body.designation, body.company, body.job_id, body.notes)
        company = await s.get(Company, person.company_id) if person.company_id else None
        return _person_out(person, company)


@router.patch("/people/{person_id}", response_model=S.PersonOut)
async def patch_person(person_id: uuid.UUID, body: S.PersonPatch, p: Principal = Depends(get_principal)):
    async with user_session(p.user_id) as s:
        person = await get_owned(s, Person, person_id, p.user_id)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(person, k, v)
        await s.flush()
        company = await s.get(Company, person.company_id) if person.company_id else None
        return _person_out(person, company)

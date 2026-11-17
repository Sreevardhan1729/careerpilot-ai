"""Jobs: creation from user input, company upsert, verified persistence, listing/detail, DB-backed dedup."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import system_session, user_session
from app.core.errors import ValidationFailed
from app.domain.dedup import ExistingJob, ListingKey, find_duplicate, location_key, normalize_title
from app.domain.job_verify import VerifiedJob
from app.domain.text import clean_text, description_hash
from app.domain.urls import canonical_job_key, canonicalize_url, company_domain_from_url
from app.models import Company, Job, JobEvidence, JobSkill, JobSourceRecord, ResumeMatch, Skill
from app.services.common import audit, decode_cursor, encode_cursor, get_owned

_LEGAL_SUFFIX = re.compile(r"[,.]?\s+(pvt\.?\s*ltd\.?|private limited|limited|ltd\.?|inc\.?|llc|llp|gmbh|corp\.?|corporation|"
                           r"co\.?|plc|s\.?a\.?|b\.?v\.?)$", re.I)
MIN_TEXT_CHARS = 40
MAX_TEXT_CHARS = 60_000


def normalize_company(name: str) -> str:
    n = name.strip()
    while True:
        new = _LEGAL_SUFFIX.sub("", n).strip()
        if new == n:
            break
        n = new
    return re.sub(r"\s+", " ", n.lower()).strip()


async def upsert_company(name: str | None, url_hint: str | None = None) -> uuid.UUID | None:
    if not name or not name.strip():
        return None
    domain = company_domain_from_url(name, url_hint)  # never a job board / form host / mismatched site
    norm = normalize_company(name)
    async with system_session() as s:
        row = (await s.execute(select(Company).where(Company.normalized_name == norm))).scalar_one_or_none()
        if row is None:
            if domain and (await s.execute(select(Company.id).where(Company.domain == domain))).first():
                domain = None
            row = Company(name=name.strip()[:200], normalized_name=norm, domain=domain,
                          website=f"https://{domain}" if domain else None)
            s.add(row)
            await s.flush()
        elif domain and not row.domain and not (await s.execute(select(Company.id).where(Company.domain == domain))).first():
            row.domain = domain
            row.website = row.website or f"https://{domain}"
        return row.id


async def existing_by_hash_or_url(session: AsyncSession, user_id: uuid.UUID, desc_hash: str | None, canonical: str | None,
                                  exclude: uuid.UUID | None = None) -> Job | None:
    conds = []
    if desc_hash:
        conds.append(Job.description_sha256 == desc_hash)
    if canonical:
        conds.append(Job.canonical_url == canonical)
    if not conds:
        return None
    q = select(Job).where(Job.user_id == user_id, or_(*conds), Job.status != "failed")
    if exclude:
        q = q.where(Job.id != exclude)
    return (await session.execute(q.order_by(Job.created_at))).scalars().first()


def _validate_text(raw: str) -> str:
    cleaned = clean_text(raw or "")
    if len(cleaned) < MIN_TEXT_CHARS:
        raise ValidationFailed(f"Paste at least {MIN_TEXT_CHARS} characters of the job post.",
                               details={"fields": [{"field": "text", "message": "too short"}]})
    if len(cleaned) > MAX_TEXT_CHARS:
        raise ValidationFailed("The job text is too long (max 60,000 characters).")
    return cleaned


def manual_to_text(fields: dict[str, Any]) -> str:
    labels = [("company", "Company"), ("job_title", "Role"), ("location", "Location"), ("work_mode", "Work mode"),
              ("employment_type", "Employment type"), ("experience", "Experience"), ("salary", "Compensation"),
              ("application_url", "Apply at")]
    lines = [f"{label}: {fields[key]}" for key, label in labels if fields.get(key)]
    for key, heading in (("requirements", "Requirements"), ("nice_to_have", "Nice to have"),
                         ("responsibilities", "Responsibilities")):
        items = fields.get(key) or []
        if isinstance(items, str):
            items = [i.strip() for i in items.split("\n") if i.strip()]
        if items:
            lines.append(heading)
            lines += [f"- {i}" for i in items]
    if fields.get("description"):
        lines.append(str(fields["description"]))
    return "\n".join(lines)


async def create_job_from_text(user_id: uuid.UUID, raw_text: str, *, input_type: str = "text",
                               source_url: str | None = None) -> tuple[Job, bool]:
    """Returns (job, deduplicated)."""
    cleaned = _validate_text(raw_text)
    digest = description_hash(cleaned)
    async with user_session(user_id) as s:
        dup = await existing_by_hash_or_url(s, user_id, digest, None)
        if dup:
            return dup, True
        job = Job(user_id=user_id, input_type=input_type, source_url=source_url, canonical_url=None,
                  description_text=cleaned, description_sha256=digest, status="queued")
        s.add(job)
        await s.flush()
        s.add(JobSourceRecord(user_id=user_id, job_id=job.id, source_name="user_paste" if input_type in ("text", "manual") else input_type,
                              source_url=source_url, canonical_url=canonicalize_url(source_url), raw_description=cleaned,
                              content_sha256=digest, collected_at=datetime.now(tz=UTC), dedup_signal="new"))
        await audit(s, user_id, "job.created", "job", job.id, input_type=input_type)
        return job, False


async def create_job_from_url(user_id: uuid.UUID, url: str) -> tuple[Job, bool]:
    from app.integrations.fetch import SafeFetcher

    await SafeFetcher().validate_target(url)  # unsafe / blocked URLs fail fast with 400/422
    canonical = canonical_job_key(url)
    async with user_session(user_id) as s:
        dup = await existing_by_hash_or_url(s, user_id, None, canonical)
        if dup:
            return dup, True
        job_id = uuid.uuid4()
        job = Job(id=job_id, user_id=user_id, input_type="url", source_url=url, canonical_url=canonical,
                  description_text="", description_sha256=f"pending:{job_id}", status="queued")
        s.add(job)
        await audit(s, user_id, "job.created", "job", job_id, input_type="url")
        return job, False


async def find_db_duplicate(session: AsyncSession, user_id: uuid.UUID, key: ListingKey,
                            exclude: uuid.UUID | None = None) -> tuple[uuid.UUID, str] | None:
    rec_conds = []
    if key.canonical_url:
        rec_conds.append(JobSourceRecord.canonical_url == key.canonical_url)
    if key.source_listing_id:
        rec_conds.append(and_(JobSourceRecord.source_name == key.source_name, JobSourceRecord.source_listing_id == key.source_listing_id))
    if key.application_url:
        rec_conds.append(JobSourceRecord.application_url == key.application_url)
    if key.description_hash:
        rec_conds.append(JobSourceRecord.content_sha256 == key.description_hash)
    job_conds = []
    if key.canonical_url:
        job_conds.append(Job.canonical_url == key.canonical_url)
    if key.description_hash:
        job_conds.append(Job.description_sha256 == key.description_hash)
    if key.company_id and key.normalized_title:
        job_conds.append(and_(Job.company_id == key.company_id, Job.normalized_title == key.normalized_title))
    candidates: dict[uuid.UUID, ExistingJob] = {}
    if rec_conds:
        recs = (await session.execute(select(JobSourceRecord).where(JobSourceRecord.user_id == user_id, or_(*rec_conds)))).scalars().all()
        for r in recs:
            candidates.setdefault(r.job_id, ExistingJob(r.job_id)).keys.append(ListingKey(
                canonical_url=r.canonical_url, source_name=r.source_name, source_listing_id=r.source_listing_id,
                application_url=r.application_url, description_hash=r.content_sha256, company_id=None,
                normalized_title=None, location_key=None, posted_at=r.posted_at))
    if job_conds:
        jobs = (await session.execute(select(Job).where(Job.user_id == user_id, or_(*job_conds)))).scalars().all()
        ids = [j.id for j in jobs] + list(candidates)
    else:
        ids = list(candidates)
    if not ids:
        return None
    for j in (await session.execute(select(Job).where(Job.id.in_(ids)))).scalars().all():
        candidates.setdefault(j.id, ExistingJob(j.id)).keys.append(ListingKey(
            canonical_url=j.canonical_url, source_name=None, source_listing_id=None,
            application_url=canonicalize_url(j.application_url), description_hash=j.description_sha256,
            company_id=j.company_id, normalized_title=j.normalized_title,
            location_key=location_key(j.locations, j.work_mode), posted_at=j.posted_at))
    if exclude:
        candidates.pop(exclude, None)
    return find_duplicate(key, list(candidates.values()))


async def skill_ids_by_slug(session: AsyncSession) -> dict[str, uuid.UUID]:
    return {slug: sid for slug, sid in (await session.execute(select(Skill.slug, Skill.id))).all()}


async def persist_verified(user_id: uuid.UUID, job_id: uuid.UUID, v: VerifiedJob, *, extraction: dict[str, Any],
                           model_id: str, prompt_ref: str, company_url_hint: str | None) -> Job:
    company_id = await upsert_company(v.company_name, company_url_hint or v.application_url)
    async with user_session(user_id) as s:
        job = await get_owned(s, Job, job_id, user_id)
        job.company_id = company_id
        job.title, job.normalized_title = v.title, normalize_title(v.title)
        job.department, job.seniority = v.department, v.seniority
        job.experience_min_years, job.experience_max_years = v.experience_min, v.experience_max
        job.experience_explicit, job.experience_evidence = v.experience_explicit, v.experience_evidence
        job.locations, job.work_mode, job.employment_type = v.locations, v.work_mode, v.employment_type
        job.salary_min, job.salary_max, job.salary_currency = v.salary_min, v.salary_max, v.salary_currency
        job.salary_period, job.salary_source_type, job.salary_is_base = v.salary_period, v.salary_source_type, v.salary_is_base
        job.salary_confidence = v.salary_confidence
        if v.salary_source_type != "not_disclosed":
            job.salary_retrieved_at = datetime.now(tz=UTC)
            job.salary_source_url = job.source_url
        job.education, job.responsibilities = v.education, v.responsibilities
        job.technical_requirements, job.soft_skills = v.technical_requirements, v.soft_skills
        job.business_domain, job.application_deadline = v.business_domain, v.application_deadline
        if v.posted_at:
            job.posted_at, job.posted_at_source = v.posted_at, job.posted_at_source or "jd_text"
        job.application_url = v.application_url or job.application_url
        job.posted_by, job.hiring_expectations = v.posted_by, v.hiring_expectations
        job.extraction, job.missing_information = extraction, v.missing_information
        job.field_confidence = v.field_confidence
        job.status, job.analyzed_at, job.model_id, job.prompt_version = "analyzed", datetime.now(tz=UTC), model_id, prompt_ref
        job.last_seen_at = job.last_seen_at or datetime.now(tz=UTC)
        await s.execute(delete(JobSkill).where(JobSkill.job_id == job_id))
        await s.execute(delete(JobEvidence).where(JobEvidence.job_id == job_id))
        slugs = await skill_ids_by_slug(s)
        for sk in v.skills:
            s.add(JobSkill(user_id=user_id, job_id=job_id, skill_id=slugs.get(sk["skill_slug"]) if sk["skill_slug"] else None,
                           raw_name=sk["raw_name"][:80], normalized_name=sk["name"], category=sk["category"],
                           importance=sk["importance"], evidence_text=sk["evidence_text"], evidence_verified=sk["evidence_verified"],
                           confidence=sk["confidence"]))
        for e in v.evidence:
            s.add(JobEvidence(user_id=user_id, job_id=job_id, field=e["field"][:80], value=e["value"],
                              evidence_text=e["evidence_text"], explicit=e["explicit"], verified=e["verified"],
                              confidence=e["confidence"]))
        return job


JOB_SORTS = {"-job_score": (Job.job_score.desc().nulls_last(), Job.created_at.desc()),
             "-posted_at": (Job.posted_at.desc().nulls_last(), Job.created_at.desc()),
             "-created_at": (Job.created_at.desc(),), "company": (Company.name.asc().nulls_last(), Job.created_at.desc())}


async def list_jobs(session: AsyncSession, user_id: uuid.UUID, f: dict[str, Any], limit: int, cursor: str | None) -> tuple[list[tuple[Job, Company | None]], str | None]:
    q = select(Job, Company).outerjoin(Company, Company.id == Job.company_id).where(Job.user_id == user_id)
    if f.get("q"):
        like = f"%{f['q'].lower()}%"
        q = q.where(or_(func.lower(Job.title).like(like), func.lower(Company.name).like(like)))
    if f.get("role"):
        q = q.where(Job.normalized_title.like(f"%{normalize_title(f['role'])}%"))
    if f.get("company_id"):
        q = q.where(Job.company_id == f["company_id"])
    if f.get("location"):
        loc = f["location"].lower()
        if loc == "remote":
            q = q.where(Job.work_mode == "remote")
        else:
            q = q.where(text("EXISTS (SELECT 1 FROM jsonb_array_elements(jobs.locations) l WHERE lower(l->>'city') = :loc)")
                        .bindparams(loc=loc))
    if f.get("work_mode"):
        q = q.where(Job.work_mode.in_(f["work_mode"]))
    if f.get("experience_max") is not None:
        cond = Job.experience_min_years <= f["experience_max"]
        q = q.where(cond if f.get("experience_known") else or_(cond, Job.experience_min_years.is_(None)))
    if f.get("salary_min") is not None:
        cond = func.coalesce(Job.salary_max, Job.salary_min) >= f["salary_min"]
        q = q.where(cond if f.get("salary_disclosed") else or_(cond, Job.salary_source_type == "not_disclosed"))
    if f.get("source"):
        q = q.where(Job.id.in_(select(JobSourceRecord.job_id).where(JobSourceRecord.source_name.in_(f["source"]))))
    for skill in f.get("skills") or []:
        q = q.where(Job.id.in_(select(JobSkill.job_id).where(func.lower(JobSkill.normalized_name) == skill.lower())))
    if f.get("posted_after"):
        q = q.where(Job.posted_at >= f["posted_after"])
    if f.get("min_score") is not None:
        q = q.where(Job.job_score >= f["min_score"])
    if f.get("priority"):
        q = q.where(Job.priority.in_(f["priority"]))
    if f.get("status"):
        q = q.where(Job.status == f["status"])
    else:
        q = q.where(Job.status != "archived")
    if f.get("saved") is not None:
        q = q.where(Job.saved == f["saved"])
    q = q.order_by(*JOB_SORTS.get(f.get("sort") or "-job_score", JOB_SORTS["-job_score"]))
    offset = int((decode_cursor(cursor) or {}).get("o", 0))
    rows = (await session.execute(q.offset(offset).limit(limit + 1))).all()
    next_cursor = encode_cursor({"o": offset + limit}) if len(rows) > limit else None
    return [(r[0], r[1]) for r in rows[:limit]], next_cursor


async def job_sources(session: AsyncSession, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    out: dict[uuid.UUID, list[str]] = {}
    if not job_ids:
        return out
    for job_id, name in (await session.execute(select(JobSourceRecord.job_id, JobSourceRecord.source_name)
                                               .where(JobSourceRecord.job_id.in_(job_ids)))).all():
        if name not in out.setdefault(job_id, []):
            out[job_id].append(name)
    return out


async def job_matches(session: AsyncSession, job_id: uuid.UUID) -> list[ResumeMatch]:
    from app.domain.matching import load_scoring_config

    return list((await session.execute(select(ResumeMatch).where(
        ResumeMatch.job_id == job_id, ResumeMatch.scoring_config_version == load_scoring_config().version)
        .order_by(ResumeMatch.rank))).scalars().all())

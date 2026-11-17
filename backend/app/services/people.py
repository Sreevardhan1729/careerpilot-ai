"""People & recruiter intelligence (spec §4.3; AGENT_DESIGN §7). Evidence first, classification second."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import user_session
from app.core.logging import get_logger
from app.domain.people_scoring import c_score, classify_role, d_score, people_score, s_score, t_score
from app.domain.text import normalize_for_match, sha256_hex
from app.domain.urls import normalize_linkedin_profile, registrable_domain
from app.integrations.fetch import SafeFetcher
from app.integrations.parsing.html import extract_links
from app.integrations.search import get_search_provider
from app.models import Company, Job, JobPerson, Outreach, Person, PersonEvidence
from app.schemas.llm.other import ClassifiedPerson
from app.services.common import get_owned

log = get_logger(__name__)
TARGET = 15
_TEAM_LINK = re.compile(r"/(team|about|about-us|leadership|people|company|our-team|who-we-are)(/|$)", re.I)
_ROLE_HINT = re.compile(r"engineer|manager|head|director|lead|recruit|talent|founder|cto|ceo|vp|scientist|hr|people|partner", re.I)
_NAME = re.compile(r"^[A-Z][a-zA-Z'’.-]+(?:\s[A-Z][a-zA-Z'’.-]+){1,3}$")


def extract_people_blocks(html: str) -> list[tuple[str, str]]:
    """(name, title) pairs from team/leadership pages: heading/strong name followed by a short role line."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    pairs: list[tuple[str, str]] = []
    for el in soup.find_all(["h2", "h3", "h4", "h5", "strong", "b", "p", "span", "div"]):
        if el.find(["h2", "h3", "h4", "h5", "p", "div"]):
            continue
        name = el.get_text(" ", strip=True)
        if not _NAME.match(name) or len(name) > 60:
            continue
        sib = el.find_next(string=lambda t, n=name: t and t.strip() and t.strip() != n)
        title = (sib or "").strip()
        if 2 < len(title) <= 100 and _ROLE_HINT.search(title) and (name, title) not in pairs:
            pairs.append((name, title))
    return pairs[:60]


async def collect_company_pages(company: Company, fetcher: SafeFetcher) -> list[dict[str, Any]]:
    if not company.domain:
        return []
    out: list[dict[str, Any]] = []
    try:
        home = await fetcher.get(f"https://{company.domain}/")
    except Exception as exc:
        log.info("company_home_unavailable", domain=company.domain, error=type(exc).__name__)
        return []
    urls = [home.url]
    for href, _ in extract_links(home.text, home.url):
        if registrable_domain(href) == company.domain and _TEAM_LINK.search(href) and href not in urls:
            urls.append(href)
    for url in urls[:5]:
        try:
            page = home if url == home.url else await fetcher.get(url)
        except Exception:
            continue
        for name, title in extract_people_blocks(page.text):
            out.append({"source_type": "company_page", "provider": "fetch", "source_url": page.url,
                        "source_title": None, "snippet": f"{name} — {title}"})
    return out


def search_queries(company: str, domain: str | None, job_title: str | None, department: str | None) -> list[str]:
    qs = [
        f'"{company}" ("technical recruiter" OR "talent acquisition") India',
        f'"{company}" ("engineering manager" OR "head of engineering" OR "director of engineering") {department or ""}'.strip(),
        f'"{company}" "{job_title}" team' if job_title else None,
        f'site:linkedin.com/in "{company}" (recruiter OR "talent acquisition")',
        f"site:{domain} (team OR leadership OR about OR people)" if domain else None,
        f'"{company}" (speaker OR talk) {department or "engineering"}',
    ]
    return [q for q in qs if q][:6]


async def collect_search(company: Company, job: Job) -> list[dict[str, Any]]:
    provider = get_search_provider()
    if not provider.enabled:
        return []
    out: list[dict[str, Any]] = []
    for q in search_queries(company.name, company.domain, job.title, job.department):
        try:
            results = await provider.search(q, limit=10)
        except Exception as exc:
            log.info("search_failed", provider=provider.name, error=type(exc).__name__)
            continue
        for r in results:
            if not r.url:
                continue
            on_site = bool(company.domain and registrable_domain(r.url) == company.domain)
            out.append({"source_type": "company_page" if on_site else "search_result", "provider": r.provider,
                        "source_url": r.url, "source_title": r.title[:300], "snippet": (r.snippet or "")[:1000]})
    return out


async def store_evidence(user_id: uuid.UUID, job_id: uuid.UUID, company_id: uuid.UUID | None,
                         raw: list[dict[str, Any]]) -> list[PersonEvidence]:
    now = datetime.now(tz=UTC)
    stored: list[PersonEvidence] = []
    async with user_session(user_id) as s:
        for item in raw:
            digest = sha256_hex(f"{item['source_url']}|{item.get('source_title')}|{item['snippet']}")
            row = (await s.execute(select(PersonEvidence).where(PersonEvidence.user_id == user_id,
                                                                PersonEvidence.content_sha256 == digest))).scalar_one_or_none()
            if row is None:
                row = PersonEvidence(user_id=user_id, job_id=job_id, company_id=company_id, content_sha256=digest, retrieved_at=now,
                                     **{k: item.get(k) for k in ("source_type", "provider", "source_url", "source_title", "snippet")})
                s.add(row)
                await s.flush()
            stored.append(row)
    return stored


_EMAIL_TOKEN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_FORMER = re.compile(r"\b(?:former(?:ly)?|ex-|previously|past|retired|alumn(?:us|a|i) of)\b", re.I)
_GENERIC_MAILBOX = re.compile(r"^(careers|jobs|hr|hiring|recruit(ing|ment)?|talent|info|contact|hello|support|team|admin)@", re.I)
_SITE_TYPES = ("company_page", "job_post", "user_provided")


def validate_person(p: ClassifiedPerson, evidence: dict[str, PersonEvidence], company: Company) -> tuple[bool, str]:
    """Deterministic checks (AGENT_DESIGN §7.3). Returns (keep, reason)."""
    cited = [evidence[e] for e in p.evidence_ids if e in evidence]
    if not cited:
        return False, "no cited evidence"
    name = normalize_for_match(p.name)
    comp = normalize_for_match(company.name)

    def text(e: PersonEvidence) -> str:
        return normalize_for_match(f"{e.source_title or ''} {e.snippet}")

    supporting = [e for e in cited if name in text(e) and (e.source_type in _SITE_TYPES or comp in text(e))]
    if not supporting:
        return False, "name and company not supported by the same evidence item"
    for e in supporting:
        t = text(e)
        idx = t.find(name)
        if _FORMER.search(t[max(0, idx - 25): idx + len(name) + 80]):
            return False, "former employee"
    if p.linkedin_url:
        norm = normalize_linkedin_profile(p.linkedin_url)
        p.linkedin_url = norm if norm and any(normalize_linkedin_profile(e.source_url) == norm for e in cited) else None
    else:
        p.linkedin_url = next((normalize_linkedin_profile(e.source_url) for e in cited if normalize_linkedin_profile(e.source_url)), None)
    if p.public_email:
        want = p.public_email.strip().lower()
        tokens = {m.lower() for e in supporting for m in _EMAIL_TOKEN.findall(e.snippet or "")}
        domain_ok = bool(company.domain) and (want.endswith("@" + company.domain) or want.endswith("." + company.domain))
        if want not in tokens or not domain_ok or _GENERIC_MAILBOX.match(want):
            p.public_email = None
    p.evidence_ids = [str(e.id) for e in supporting] + [i for i in p.evidence_ids if i not in {str(e.id) for e in supporting}]
    return True, "ok"


def association_for(p: ClassifiedPerson, cited: list[PersonEvidence]) -> str:
    if any(e.source_type in ("company_page", "job_post") for e in cited):
        return "verified_current"
    if p.current_company_verified or any(e.source_type == "search_result" for e in cited):
        return "likely_current"
    return "unverified"


async def upsert_people(user_id: uuid.UUID, job: Job, company: Company, people: list[ClassifiedPerson],
                        evidence: dict[str, PersonEvidence]) -> tuple[int, int]:
    """Validate, dedupe, score, persist; returns (verified_count, rejected_count)."""
    now = datetime.now(tz=UTC)
    rejected = 0
    scored: list[tuple[float, Person, dict[str, Any], ClassifiedPerson, list[uuid.UUID]]] = []
    async with user_session(user_id) as s:
        for p in people:
            keep, reason = validate_person(p, evidence, company)
            if not keep:
                rejected += 1
                log.info("person_rejected", reason=reason)
                continue
            cited = [evidence[e] for e in p.evidence_ids if e in evidence]
            status = association_for(p, cited)
            norm_name = normalize_for_match(p.name)
            q = select(Person).where(Person.user_id == user_id)
            person = None
            if p.linkedin_url:
                person = (await s.execute(q.where(Person.linkedin_url == p.linkedin_url))).scalar_one_or_none()
            if person is None:
                person = (await s.execute(q.where(Person.company_id == company.id, Person.normalized_name == norm_name))).scalars().first()
            email_ev = next((e.id for e in cited if p.public_email and p.public_email.lower() in e.snippet.lower()), None)
            if person is None:
                person = Person(user_id=user_id, company_id=company.id, name=p.name, normalized_name=norm_name,
                                designation=p.designation, department=p.department, linkedin_url=p.linkedin_url,
                                public_email=p.public_email, public_email_evidence_id=email_ev, association_status=status,
                                added_by="discovery", first_discovered_at=now, last_verified_at=now)
                s.add(person)
                await s.flush()
            else:
                rank_status = {"verified_current": 0, "likely_current": 1, "unverified": 2}
                if rank_status[status] < rank_status[person.association_status]:
                    person.association_status = status
                person.designation = person.designation or p.designation
                person.linkedin_url = person.linkedin_url or p.linkedin_url
                if p.public_email and not person.public_email:
                    person.public_email, person.public_email_evidence_id = p.public_email, email_ev
                person.last_verified_at = now
            for e in cited:
                e.person_id = person.id
            role = p.role_category if p.role_category != "other_employee" else classify_role(p.designation)
            linkedin = any("linkedin.com" in e.source_url for e in cited)
            comps = {"T": t_score(role), "D": d_score(p.department or p.designation, job.department or job.title),
                     "C": c_score(person.association_status), "S": s_score([e.source_type for e in cited], linkedin=linkedin)}
            score = people_score(comps["T"], comps["D"], comps["C"], comps["S"])
            scored.append((score, person, {**comps, "role_category": role}, p, [e.id for e in cited]))
        # Replace only discovery-made links; people the user added stay linked to the job.
        discovered_ids = select(Person.id).where(Person.user_id == user_id, Person.added_by == "discovery")
        await s.execute(delete(JobPerson).where(JobPerson.job_id == job.id, JobPerson.person_id.in_(discovered_ids)))
        existing = {jp.person_id: jp for jp in (await s.execute(select(JobPerson).where(JobPerson.job_id == job.id))).scalars()}
        scored.sort(key=lambda x: (-x[0], x[1].name))
        seen: set[uuid.UUID] = set()
        added = 0
        for score, person, comps, p, ev_ids in scored:
            if person.id in seen or added >= TARGET:
                continue
            seen.add(person.id)
            role = comps.pop("role_category")
            reason = (p.relevance_reason or f"{p.designation or 'Employee'} at {company.name}.")[:400]
            if person.id in existing:  # a user-added contact that discovery also found: refresh its evidence/score
                jp = existing[person.id]
                jp.relevance_score, jp.components, jp.role_category = max(float(jp.relevance_score), score), comps, role
                jp.evidence_ids = list(dict.fromkeys([*jp.evidence_ids, *ev_ids]))
                continue
            added += 1
            s.add(JobPerson(user_id=user_id, job_id=job.id, person_id=person.id, role_category=role, relevance_score=score,
                            components=comps, confidence=p.confidence, evidence_ids=ev_ids, rank=999, relevance_reason=reason))
        await s.flush()
        links = (await s.execute(select(JobPerson).where(JobPerson.job_id == job.id))).scalars().all()
        for i, jp in enumerate(sorted(links, key=lambda j: (-float(j.relevance_score), str(j.person_id))), start=1):
            jp.rank = i
    return added, rejected


async def add_manual(session: AsyncSession, user_id: uuid.UUID, name: str, linkedin_url: str | None, designation: str | None,
                     company_name: str | None, job_id: uuid.UUID | None, notes: str | None) -> Person:
    from app.services.jobs import upsert_company

    company_id = None
    job = await get_owned(session, Job, job_id, user_id) if job_id else None
    if job:
        company_id = job.company_id
    elif company_name:
        company_id = await upsert_company(company_name)
    norm_url = normalize_linkedin_profile(linkedin_url) if linkedin_url else None
    now = datetime.now(tz=UTC)
    person = None
    if norm_url:
        person = (await session.execute(select(Person).where(Person.user_id == user_id, Person.linkedin_url == norm_url))).scalar_one_or_none()
    if person is None:
        person = Person(user_id=user_id, company_id=company_id, name=name, normalized_name=normalize_for_match(name),
                        designation=designation, linkedin_url=norm_url, association_status="unverified", added_by="user",
                        notes=notes, first_discovered_at=now)
        session.add(person)
        await session.flush()
    ev = PersonEvidence(user_id=user_id, person_id=person.id, job_id=job_id, company_id=company_id, source_type="user_provided",
                        provider="user", source_url=norm_url or "user-provided", source_title=designation,
                        snippet=f"Added by you: {name}" + (f" — {designation}" if designation else ""),
                        content_sha256=sha256_hex(f"user|{person.id}|{job_id}|{designation}"), retrieved_at=now)
    existing = (await session.execute(select(PersonEvidence).where(PersonEvidence.user_id == user_id,
                                                                   PersonEvidence.content_sha256 == ev.content_sha256))).scalar_one_or_none()
    if existing is None:
        session.add(ev)
        await session.flush()
        existing = ev
    if job:
        link = (await session.execute(select(JobPerson).where(JobPerson.job_id == job.id, JobPerson.person_id == person.id))).scalar_one_or_none()
        if link is None:
            role = classify_role(designation)
            comps = {"T": t_score(role), "D": d_score(designation, job.department or job.title), "C": c_score("unverified"),
                     "S": s_score(["user_provided"])}
            rank = int((await session.execute(select(func.count()).select_from(JobPerson).where(JobPerson.job_id == job.id))).scalar_one()) + 1
            session.add(JobPerson(user_id=user_id, job_id=job.id, person_id=person.id, role_category=role,
                                  relevance_score=people_score(comps["T"], comps["D"], comps["C"], comps["S"]),
                                  components=comps, relevance_reason="Added by you.", confidence=None,
                                  evidence_ids=[existing.id], rank=rank))
    return person


async def job_people_view(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
    job = await get_owned(session, Job, job_id, user_id)
    company = await session.get(Company, job.company_id) if job.company_id else None
    rows = (await session.execute(select(JobPerson, Person).join(Person, Person.id == JobPerson.person_id)
                                  .where(JobPerson.job_id == job_id).order_by(JobPerson.rank))).all()
    ev_ids = [e for jp, _ in rows for e in jp.evidence_ids]
    evidence = {e.id: e for e in (await session.execute(select(PersonEvidence).where(PersonEvidence.id.in_(ev_ids)))).scalars()} if ev_ids else {}
    counts = dict((await session.execute(select(Outreach.person_id, func.count()).where(Outreach.user_id == user_id)
                                         .group_by(Outreach.person_id))).all())
    items = []
    for jp, person in rows:
        items.append({
            "rank": jp.rank, "person_id": person.id, "name": person.name, "designation": person.designation,
            "department": person.department, "role_category": jp.role_category, "linkedin_url": person.linkedin_url,
            "public_email": person.public_email, "association_status": person.association_status,
            "relevance_score": float(jp.relevance_score), "components": jp.components, "relevance_reason": jp.relevance_reason,
            "confidence": float(jp.confidence) if jp.confidence is not None else None,
            "evidence": [evidence[e] for e in jp.evidence_ids if e in evidence], "contact_status": person.contact_status,
            "outreach_count": int(counts.get(person.id, 0)),
        })
    return {"job": job, "company": company, "items": items}

"""Rule-based classification of retrieved people evidence (no LLM). Only names present in evidence are returned."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.people_scoring import classify_role
from app.domain.text import normalize_for_match
from app.schemas.llm.job import PosterInfo
from app.schemas.llm.other import ClassifiedPerson, PeopleClassification

_NAME = r"([A-Z][a-zA-Z'’.-]+(?:\s[A-Z][a-zA-Z'’.-]+){1,3})"
_FORMER = re.compile(r"\b(former|ex-|previously|formerly|alumni of|past)\b", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GENERIC_MAILBOX = re.compile(r"^(careers|jobs|hr|hiring|recruit(ing|ment)?|talent|info|contact|hello|support)@", re.I)
_SNIPPET_PATTERNS = [
    re.compile(_NAME + r"\s*[—–-]\s*([^\n|]{2,80})$"),
    re.compile(_NAME + r",\s+([A-Z][^,.\n]{2,80}?)\s+(?:at|@)\s+(.+?)(?:[.|\n]|$)"),
    re.compile(_NAME + r"\s+is\s+(?:a|an|the|our)\s+([^,.\n]{2,80}?)\s+(?:at|@)\s+(.+?)(?:[.|\n]|$)"),
    re.compile(_NAME + r"\s*\n\s*([^\n]{2,120})"),
]


@dataclass
class EvidenceItem:
    id: str
    source_type: str
    url: str
    title: str | None
    snippet: str


def _company_matches(text: str | None, company: str) -> bool:
    return bool(text) and normalize_for_match(company) in normalize_for_match(text)


def _from_linkedin_title(title: str) -> tuple[str, str | None, str | None] | None:
    t = re.sub(r"\s*\|\s*LinkedIn\s*$", "", title.strip(), flags=re.I)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", t) if p.strip()]
    if not parts or not re.fullmatch(_NAME, parts[0]):
        return None
    designation = parts[1] if len(parts) > 1 else None
    company = parts[2] if len(parts) > 2 else None
    if designation and not company:
        m = re.search(r"\s+(?:at|@)\s+(.+)$", designation)
        if m:
            designation, company = designation[: m.start()].strip(), m.group(1).strip()
    return parts[0], designation, company


def classify_evidence(items: list[EvidenceItem], company: str, company_domain: str | None,
                      poster: PosterInfo | None) -> PeopleClassification:
    people: dict[str, ClassifiedPerson] = {}

    def add(name: str, designation: str | None, item: EvidenceItem, verified: bool, is_poster: bool = False) -> None:
        context = f"{item.title or ''}\n{item.snippet}"
        if _FORMER.search(designation or "") or re.search(r"\b(former|ex-)\s*" + re.escape(name.split()[0]), context, re.I):
            return
        key = normalize_for_match(name)
        email = None
        for e in _EMAIL.findall(item.snippet):
            if company_domain and e.lower().endswith("@" + company_domain.lower()) and not _GENERIC_MAILBOX.match(e):
                if normalize_for_match(name.split()[0]) in normalize_for_match(e.split("@")[0]):
                    email = e
        linkedin = item.url if re.search(r"(^|\.)linkedin\.com/in/", item.url) else None
        role = classify_role(designation, is_poster=is_poster)
        existing = people.get(key)
        if existing:
            existing.evidence_ids = sorted(set(existing.evidence_ids) | {item.id})
            existing.current_company_verified = existing.current_company_verified or verified
            existing.linkedin_url = existing.linkedin_url or linkedin
            existing.public_email = existing.public_email or email
            if is_poster:
                existing.role_category = "job_poster"
            return
        reason = "Posted this job." if is_poster else f"{designation or 'Employee'} at {company}."
        people[key] = ClassifiedPerson(
            name=name, designation=designation, department=None, role_category=role, linkedin_url=linkedin,
            public_email=email, evidence_ids=[item.id], current_company_verified=verified, relevance_reason=reason,
            confidence=0.8 if verified else 0.6,
        )

    for item in items:
        on_company_site = item.source_type in ("company_page", "job_post")
        if poster and poster.name and item.source_type == "job_post" and poster.name in item.snippet:
            add(poster.name, poster.headline, item, True, is_poster=True)
            continue
        if item.title and "linkedin" in item.title.lower():
            parsed = _from_linkedin_title(item.title)
            if parsed:
                name, designation, comp = parsed
                if _company_matches(comp or designation, company) or _company_matches(item.snippet, company):
                    add(name, designation, item, False)
                continue
        for pattern in _SNIPPET_PATTERNS:
            m = pattern.search(item.snippet)
            if not m:
                continue
            name, designation = m.group(1), m.group(2).strip()
            comp = m.group(3) if m.lastindex and m.lastindex >= 3 else None
            if on_company_site or _company_matches(comp, company) or _company_matches(designation, company):
                if comp is None and designation and re.search(r"\s+(?:at|@)\s+", designation):
                    designation = re.split(r"\s+(?:at|@)\s+", designation)[0]
                add(name, designation, item, on_company_site or bool(comp))
            break
    return PeopleClassification(people=list(people.values()))

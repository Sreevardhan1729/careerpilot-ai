"""Users, candidate profile, profile facts, search configs, settings (spec §3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import system_session, user_session
from app.core.security import Principal
from app.models import CandidateProfile, CandidateProfileFact, DeletedUser, SearchConfig, User
from app.services.common import audit

DEFAULT_SEARCH = {
    "name": "Default",
    "role_filters": ["AI Engineer", "ML Engineer", "GenAI Engineer", "LLM Engineer", "Backend Engineer",
                     "Software Development Engineer", "Data Engineer"],
    "experience_bands": [{"label": "Fresher", "min": 0, "max": 0}, {"label": "Graduate", "min": 0, "max": 1},
                         {"label": "0–2 years", "min": 0, "max": 2}, {"label": "0–3 years", "min": 0, "max": 3}],
    "locations": ["Bengaluru", "Hyderabad", "Pune", "Chennai", "Mumbai", "Remote India"],
    "work_modes": ["remote", "hybrid", "onsite"],
    "skills": ["Python", "LLMs", "RAG", "LangChain", "LangGraph", "FastAPI", "Machine Learning", "Artificial Intelligence",
               "Vector Databases", "Backend Engineering"],
}
DEFAULT_SETTINGS = {"scheduler_local_time": "08:00", "auto_generate_outreach": False, "notifications": {"in_app": True}}
PROFILE_FIELDS = (
    "full_name", "preferred_email", "phone", "current_location", "preferred_locations", "preferred_work_modes",
    "graduation_year", "total_experience_months", "preferred_roles", "preferred_industries", "portfolio_url", "github_url",
    "linkedin_url", "salary_preference", "employment_type_preferences", "notice_period_days", "work_authorization",
)


async def ensure_user(principal: Principal) -> User:
    """Create the user, an empty profile, and the spec §3.3 default search config on first sight."""
    async with system_session() as s:
        user = await s.get(User, principal.user_id)
        if user is None:
            if await s.get(DeletedUser, principal.user_id) is not None:
                from app.core.errors import Forbidden

                raise Forbidden("This account was deleted.")
            user = User(id=principal.user_id, email=principal.email or f"{principal.user_id}@unknown.local",
                        settings=dict(DEFAULT_SETTINGS))
            s.add(user)
            await s.flush()
            s.add(CandidateProfile(user_id=user.id, preferred_email=principal.email or None,
                                   preferred_locations=DEFAULT_SEARCH["locations"],
                                   preferred_roles=DEFAULT_SEARCH["role_filters"],
                                   preferred_work_modes=DEFAULT_SEARCH["work_modes"],
                                   employment_type_preferences=["full_time"],
                                   field_sources={"preferred_email": "user_entered"} if principal.email else {}))
            s.add(SearchConfig(user_id=user.id, **DEFAULT_SEARCH))
            await audit(s, user.id, "user.created", "user", user.id, actor="system")
        elif principal.email and user.email != principal.email:
            user.email = principal.email
        return user


async def get_profile(session: AsyncSession, user_id: uuid.UUID) -> CandidateProfile:
    profile = (await session.execute(select(CandidateProfile).where(CandidateProfile.user_id == user_id))).scalar_one_or_none()
    if profile is None:
        profile = CandidateProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


async def update_profile(session: AsyncSession, user_id: uuid.UUID, changes: dict[str, Any]) -> CandidateProfile:
    profile = await get_profile(session, user_id)
    sources = dict(profile.field_sources or {})
    for key, value in changes.items():
        if key in PROFILE_FIELDS:
            setattr(profile, key, value)
            sources[key] = "user_entered"
    profile.field_sources = sources
    await audit(session, user_id, "profile.updated", "candidate_profile", profile.id, fields=sorted(changes))
    return profile


def fact_dedup_key(fact_type: str, data: dict[str, Any]) -> str:
    from app.domain.text import normalize_for_match

    main = data.get("name") or data.get("title") or data.get("degree") or data.get("text") or ""
    extra = data.get("company") or data.get("institution") or ""
    return f"{fact_type}:{normalize_for_match(str(main))[:120]}:{normalize_for_match(str(extra))[:80]}"


async def add_fact(session: AsyncSession, user_id: uuid.UUID, fact_type: str, data: dict[str, Any], source: str = "user_entered",
                   status: str = "confirmed", source_resume_version_id: uuid.UUID | None = None) -> CandidateProfileFact | None:
    key = fact_dedup_key(fact_type, data)
    existing = (await session.execute(select(CandidateProfileFact).where(
        CandidateProfileFact.user_id == user_id, CandidateProfileFact.dedup_key == key))).scalars().first()
    if existing is not None:
        if source == "user_entered":
            existing.data, existing.status, existing.source = data, status, source
            return existing
        return None  # never overwrite an existing (possibly confirmed) fact with a suggestion
    fact = CandidateProfileFact(user_id=user_id, fact_type=fact_type, data=data, source=source, status=status,
                                dedup_key=key, source_resume_version_id=source_resume_version_id)
    from datetime import UTC, datetime

    if status == "confirmed":
        fact.confirmed_at = datetime.now(tz=UTC)
    session.add(fact)
    await session.flush()
    return fact


async def confirmed_skills(session: AsyncSession, user_id: uuid.UUID) -> tuple[set[str], set[str]]:
    from app.domain.skills import get_taxonomy

    tax = get_taxonomy()
    rows = (await session.execute(select(CandidateProfileFact).where(
        CandidateProfileFact.user_id == user_id, CandidateProfileFact.fact_type == "skill",
        CandidateProfileFact.status == "confirmed"))).scalars().all()
    has, missing = set(), set()
    for f in rows:
        name = tax.normalize_name(str(f.data.get("name", "")))
        (missing if f.data.get("has_skill") is False else has).add(name)
    return has, missing


async def active_search_config(session: AsyncSession, user_id: uuid.UUID) -> SearchConfig | None:
    return (await session.execute(select(SearchConfig).where(SearchConfig.user_id == user_id, SearchConfig.is_active)
                                  .order_by(SearchConfig.created_at))).scalars().first()


async def user_settings(user_id: uuid.UUID) -> dict[str, Any]:
    async with user_session(user_id) as s:
        user = await s.get(User, user_id)
        return {**DEFAULT_SETTINGS, **((user.settings if user else None) or {})}

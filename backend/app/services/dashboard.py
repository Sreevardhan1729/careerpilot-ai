"""Dashboard metrics (spec §9 page 1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AgentRun, Application, Company, Job, JobPerson, LLMCall, Outreach, Person, User
from app.utils.time import start_of_local_day_utc


async def summary(s: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    user = await s.get(User, user_id)
    tz = (user.timezone if user else None) or get_settings().default_timezone
    today = start_of_local_day_utc(tz)

    async def count(q) -> int:
        return int((await s.execute(q)).scalar_one())

    jobs_total = await count(select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status != "archived"))
    new_today = await count(select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.created_at >= today))
    bands = dict((await s.execute(select(Job.priority, func.count()).where(Job.user_id == user_id, Job.priority.is_not(None))
                                  .group_by(Job.priority))).all())
    people = await count(select(func.count()).select_from(Person).where(Person.user_id == user_id))
    drafts = await count(select(func.count()).select_from(Outreach).where(Outreach.user_id == user_id,
                                                                            Outreach.status.in_(("draft", "edited"))))
    submitted = await count(select(func.count()).select_from(Application).where(
        Application.user_id == user_id, Application.status.in_(("applied", "recruiter_contacted", "interview_scheduled",
                                                                 "rejected", "offer_received"))))
    follow_ups = (await s.execute(select(Application.id, Application.follow_up_date, Job.title).join(Job, Job.id == Application.job_id)
                                  .where(Application.user_id == user_id, Application.follow_up_date.is_not(None),
                                         Application.follow_up_date <= (datetime.now(tz=UTC) + timedelta(days=7)).date())
                                  .order_by(Application.follow_up_date).limit(10))).all()
    last_daily = (await s.execute(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.workflow_name == "daily_pipeline")
                                  .order_by(AgentRun.created_at.desc()).limit(1))).scalars().first()
    latest = (await s.execute(select(Job, Company).outerjoin(Company, Company.id == Job.company_id)
                              .where(Job.user_id == user_id, Job.status == "analyzed",
                                     Job.created_at >= datetime.now(tz=UTC) - timedelta(days=7))
                              .order_by(Job.job_score.desc().nulls_last()).limit(10))).all()
    failures = (await s.execute(select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.status == "failed")
                                .order_by(AgentRun.created_at.desc()).limit(5))).scalars().all()
    used = await count(select(func.count()).select_from(LLMCall).where(
        LLMCall.user_id == user_id, LLMCall.created_at >= datetime.now(tz=UTC) - timedelta(hours=24), LLMCall.status != "cache_hit"))
    people_linked = await count(select(func.count(func.distinct(JobPerson.job_id))).where(JobPerson.user_id == user_id))
    stale = last_daily is None or last_daily.created_at < datetime.now(tz=UTC) - timedelta(hours=36)
    settings = get_settings()
    return {
        "jobs_total": jobs_total, "jobs_new_today": new_today,
        "matches": {"excellent": bands.get("excellent", 0), "strong": bands.get("strong", 0),
                    "moderate": bands.get("moderate", 0), "low": bands.get("low", 0)},
        "people_discovered": people, "jobs_with_people": people_linked, "outreach_awaiting_review": drafts,
        "applications_submitted": submitted,
        "follow_ups_due": [{"application_id": str(a), "date": d.isoformat(), "job_title": t} for a, d, t in follow_ups],
        "scheduler": {"last_run_at": last_daily.created_at.isoformat() if last_daily else None,
                      "last_status": last_daily.status if last_daily else None, "stale": stale,
                      "last_run_id": str(last_daily.id) if last_daily else None},
        "latest_jobs": [{"id": str(j.id), "title": j.title, "company": c.name if c else None, "job_score": float(j.job_score or 0),
                         "priority": j.priority, "posted_at": j.posted_at.isoformat() if j.posted_at else None} for j, c in latest],
        "recent_failures": [{"workflow_id": str(r.id), "workflow_name": r.workflow_name,
                             "error_code": (r.error or {}).get("code"), "message": (r.error or {}).get("message"),
                             "at": r.created_at.isoformat()} for r in failures],
        "llm_budget": {"used_today": used, "limit": settings.llm_daily_call_budget, "provider": settings.llm_provider,
                       "model": settings.llm_model_label},
    }

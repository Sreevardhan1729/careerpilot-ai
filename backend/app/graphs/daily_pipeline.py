"""Daily pipeline (spec §10.1): discover → analyse+match → people for priority jobs → drafts → digest → retention.

Each stage runs as a child agent run so progress and failures are visible per stage; a failed stage marks the
pipeline partially_completed and later stages still run where possible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, not_, select

from app import agents
from app.core.config import get_settings
from app.core.db import user_session
from app.models import Company, Job, JobPerson
from app.services import retention
from app.services.notifications import notify
from app.services.users import user_settings
from app.tasks.runner import TaskContext, handler, run_inline


@handler("daily_pipeline")
async def handle(ctx: TaskContext) -> dict:
    s = get_settings()
    failures: list[str] = []
    uid = ctx.user_id

    await ctx.progress("discover", "running")
    _, disc, status = await run_inline(uid, "discover_jobs", {"enqueue_analysis": False}, ctx.agent_run_id)
    new_ids = (disc or {}).get("new_job_ids", [])
    if status in ("failed", "partially_completed"):
        failures.append(f"discover:{status}")
    await ctx.progress("discover", "completed" if status != "failed" else "failed", {"new_jobs": len(new_ids), "status": status})

    await ctx.progress("analyze_and_match", "running")
    analysed = 0
    for job_id in new_ids[: s.discovery_max_new_jobs_analyzed_per_run]:
        jid = uuid.UUID(job_id)
        _, out, st = await run_inline(uid, "analyze_job", {"job_id": job_id, "chain_match": False}, ctx.agent_run_id, "job", jid)
        if st == "failed":
            failures.append(f"analyze:{job_id}")
            continue
        target = (out or {}).get("job_id", job_id)
        if (out or {}).get("deduplicated"):
            continue
        _, _, st = await run_inline(uid, "match_resumes", {"job_id": target}, ctx.agent_run_id, "job", uuid.UUID(target))
        if st == "failed":
            failures.append(f"match:{target}")
        analysed += 1
    await ctx.progress("analyze_and_match", "completed", {"analysed": analysed})

    await ctx.progress("people", "running")
    since = datetime.now(tz=UTC) - timedelta(days=2)
    async with user_session(uid) as session:
        priority_jobs = (await session.execute(
            select(Job.id).where(Job.user_id == uid, Job.status == "analyzed", Job.priority.in_(("excellent", "strong")),
                                 Job.analyzed_at >= since, not_(exists().where(JobPerson.job_id == Job.id)))
            .order_by(Job.job_score.desc()).limit(s.people_discovery_max_jobs_per_run))).scalars().all()
    for jid in priority_jobs:
        _, _, st = await run_inline(uid, "discover_people", {"job_id": str(jid)}, ctx.agent_run_id, "job", jid)
        if st == "failed":
            failures.append(f"people:{jid}")
    await ctx.progress("people", "completed", {"jobs": len(priority_jobs)})

    prefs = await user_settings(uid)
    if prefs.get("auto_generate_outreach"):
        await ctx.progress("outreach", "running")
        for jid in priority_jobs:
            _, _, st = await run_inline(uid, "generate_outreach", {"job_id": str(jid), "message_types": ["linkedin_connection", "recruiter_email"]},
                                        ctx.agent_run_id, "job", jid)
            if st == "failed":
                failures.append(f"outreach:{jid}")
        await ctx.progress("outreach", "completed")

    await ctx.progress("digest", "running")
    async with user_session(uid) as session:
        rows = (await session.execute(select(Job, Company).outerjoin(Company, Company.id == Job.company_id)
                                      .where(Job.user_id == uid, Job.analyzed_at >= since, Job.job_score.is_not(None))
                                      .order_by(Job.job_score.desc()).limit(15))).all()
    jobs = [{"job_id": str(j.id), "title": j.title, "company": c.name if c else None, "job_score": float(j.job_score),
             "priority": j.priority, "missing": j.missing_information,
             "disqualifiers": (j.job_score_breakdown or {}).get("disqualifiers", [])} for j, c in rows]
    digest = await agents.daily_digest(jobs, user_id=uid, run_id=ctx.agent_run_id)
    await notify(uid, "daily_summary", f"Daily discovery: {len(new_ids)} new, {analysed} analysed", digest, "/dashboard")
    await ctx.progress("digest", "completed")

    await ctx.progress("retention", "running")
    purged = await retention.run(uid)
    await ctx.progress("retention", "completed", purged)
    return {"_status": "partially_completed" if failures else "completed", "new_jobs": len(new_ids), "analysed": analysed,
            "people_jobs": len(priority_jobs), "failures": failures[:50], "retention": purged}

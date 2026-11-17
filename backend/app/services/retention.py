"""Data retention (docs/DATABASE_SCHEMA.md §7). Runs at the end of the daily pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, exists, not_, or_, select, update

from app.core.db import system_session, user_session
from app.models import (
    AgentRun,
    Application,
    Approval,
    CrawlRun,
    IdempotencyKey,
    Job,
    JobPerson,
    JobSourceRecord,
    LLMCall,
    Outreach,
    PersonEvidence,
)


async def run(user_id: uuid.UUID) -> dict[str, int]:
    now = datetime.now(tz=UTC)
    out: dict[str, int] = {}
    async with user_session(user_id) as s:
        keep_job = or_(Job.saved, Job.priority.in_(("excellent", "strong", "moderate")),
                       exists().where(Application.job_id == Job.id), exists().where(Outreach.job_id == Job.id))
        r = await s.execute(update(JobSourceRecord).where(
            JobSourceRecord.user_id == user_id, JobSourceRecord.collected_at < now - timedelta(days=30),
            JobSourceRecord.raw_description.is_not(None),
            JobSourceRecord.job_id.in_(select(Job.id).where(Job.user_id == user_id, not_(keep_job)))).values(raw_description=None))
        out["source_descriptions_purged"] = r.rowcount or 0
        r = await s.execute(delete(Job).where(Job.user_id == user_id, not_(keep_job),
                                              func_coalesce(Job.last_seen_at, Job.created_at) < now - timedelta(days=90)))
        out["jobs_deleted"] = r.rowcount or 0
        r = await s.execute(delete(PersonEvidence).where(
            PersonEvidence.user_id == user_id, PersonEvidence.created_at < now - timedelta(days=180),
            or_(PersonEvidence.person_id.is_(None), not_(exists().where(JobPerson.person_id == PersonEvidence.person_id)))))
        out["people_evidence_deleted"] = r.rowcount or 0
        r = await s.execute(update(LLMCall).where(LLMCall.user_id == user_id, LLMCall.created_at < now - timedelta(days=90),
                                                  LLMCall.output.is_not(None)).values(output=None))
        out["llm_outputs_purged"] = r.rowcount or 0
        old_runs = list((await s.execute(select(AgentRun.id).where(
            AgentRun.user_id == user_id, AgentRun.completed_at < now - timedelta(days=90),
            not_(exists().where(Approval.agent_run_id == AgentRun.id))))).scalars())
        expired_exports = list((await s.execute(select(AgentRun.id).where(
            AgentRun.user_id == user_id, AgentRun.workflow_name == "account_export",
            AgentRun.completed_at < now - timedelta(days=1)))).scalars())
        r = await s.execute(delete(AgentRun).where(AgentRun.id.in_(old_runs)))
        out["runs_deleted"] = r.rowcount or 0
        r = await s.execute(delete(CrawlRun).where(CrawlRun.user_id == user_id, CrawlRun.created_at < now - timedelta(days=180)))
        out["crawl_runs_deleted"] = r.rowcount or 0
    from app.graphs.runtime import delete_thread
    from app.integrations.storage import get_storage

    for run_id in old_runs:  # checkpoints can hold resume/JD text: purge them with their run
        try:
            await delete_thread(run_id)
        except Exception:
            pass
    if expired_exports:
        try:
            await get_storage().delete([f"{user_id}/exports/{r}.zip" for r in expired_exports])
        except Exception:
            pass
    out["exports_deleted"] = len(expired_exports)
    async with system_session() as s:
        await s.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at < now))
    return out


def func_coalesce(a, b):
    from sqlalchemy import func

    return func.coalesce(a, b)


__all__ = ["run", "and_"]

"""Resume matching + job ranking orchestration (deterministic scores; optional LLM prose on top)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import agents
from app.core.db import user_session
from app.core.logging import get_logger
from app.domain.claims import ClaimContext, check_claims
from app.domain.matching import (
    JobForMatch,
    JobSkillIn,
    MatchResult,
    ProfileSkills,
    load_scoring_config,
    rank_results,
    result_to_json,
    score_resume,
)
from app.domain.normalize import normalize_location
from app.domain.ranking import RankingInput, score_job
from app.heuristics.improve import suggest_improvements
from app.integrations.embeddings import get_embeddings
from app.models import Job, JobSkill, Resume, ResumeChunk, ResumeMatch, ResumeVersion
from app.schemas.llm.resume import ResumeParsed
from app.services import users as users_svc
from app.services.common import get_owned
from app.services.resumes import resumes_for_matching

log = get_logger(__name__)


def job_focus_text(job: Job) -> str:
    return "\n".join(filter(None, [job.title or "", *(job.responsibilities or [])[:10], *(job.technical_requirements or [])[:10]]))


async def _resume_evidence(session: AsyncSession, version_id: uuid.UUID) -> tuple[str, dict[str, str]]:
    chunks = (await session.execute(select(ResumeChunk).where(ResumeChunk.resume_version_id == version_id))).scalars().all()
    by_id = {f"chunk:{c.id}": c.content for c in chunks}
    return "\n".join(f"[{cid}] {text}" for cid, text in by_id.items()), by_id


async def match_job(user_id: uuid.UUID, job_id: uuid.UUID, run_id: uuid.UUID | None = None) -> dict[str, Any]:
    cfg = load_scoring_config()
    emb = get_embeddings()
    async with user_session(user_id) as s:
        job = await get_owned(s, Job, job_id, user_id)
        skills = (await s.execute(select(JobSkill).where(JobSkill.job_id == job_id))).scalars().all()
        resumes = await resumes_for_matching(s, user_id)
        has, missing = await users_svc.confirmed_skills(s, user_id)
        focus_text, responsibilities = job_focus_text(job), list(job.responsibilities or [])[:15]
        job_text, title = job.description_text, job.title or "this role"
        jf_static = dict(skills=[JobSkillIn(sk.normalized_name, sk.importance) for sk in skills],
                         experience_min=float(job.experience_min_years) if job.experience_min_years is not None else None,
                         experience_max=float(job.experience_max_years) if job.experience_max_years is not None else None,
                         domain=job.business_domain)
    if not resumes:
        await rank_job(user_id, job_id)
        return {"resumes_ranked": 0, "message": "Upload a resume to get match scores."}
    focus = await emb.embed_query(focus_text or title)
    resp_vecs = [await emb.embed_query(r) for r in responsibilities]
    jf = JobForMatch(focus_embedding=focus, responsibility_embeddings=resp_vecs, **jf_static)
    profile = ProfileSkills(has=has, missing=missing)
    ranked: list[MatchResult] = rank_results([score_resume(jf, r, profile, cfg, emb.provider) for r in resumes])

    explanations: dict[uuid.UUID, dict[str, Any]] = {}
    async with user_session(user_id) as s:
        for m in ranked:
            version = await s.get(ResumeVersion, m.version_id)
            parsed = ResumeParsed.model_validate(version.parsed_data) if version and version.parsed_data else ResumeParsed()
            base = suggest_improvements({"skill_breakdown": m.skill_breakdown}, parsed, title)
            text_expl = " ".join(c.explanation for c in m.components.values())
            entry: dict[str, Any] = {"explanation": text_expl, "suggestions": {
                "summary": None, "bullet_rewrites": [], "keywords_to_highlight": base.keywords_to_highlight,
                "missing_evidence": base.missing_evidence, "skill_order": base.skill_order}, "limitations": []}
            if m.rank <= 3:
                evidence_text, chunk_texts = await _resume_evidence(s, m.version_id)
                try:
                    result = await agents.explain_match(
                        job_title=title, job_text=job_text, resume_evidence=evidence_text, user_id=user_id, run_id=run_id,
                        scores={"score": m.score, "components": result_to_json(m), "skills": m.skill_breakdown})
                except Exception as exc:  # prose is optional; numbers already stand
                    log.warning("match_explanation_failed", error=str(exc)[:200])
                    result = None
                    entry["limitations"].append("LLM explanation unavailable; showing rule-based explanation.")
                if result:
                    value, _meta = result
                    candidate_skills = {sk.name for sk in parsed.skills}
                    rewrites = []
                    for rw in value.bullet_rewrites:
                        evidence = [rw.before, *(chunk_texts.get(ref, "") for ref in rw.evidence_refs)]
                        check = check_claims(rw.after, None, None, ClaimContext(evidence_texts=evidence, candidate_skills=candidate_skills,
                                                                                 has_relationship_history=True, recipient_verified_email=None))
                        if check.passed:
                            rewrites.append(rw.model_dump())
                        else:
                            entry["limitations"].append(f"Dropped a suggested rewrite: {check.blocking[0]['detail']}")
                    entry["explanation"] = value.explanation
                    entry["suggestions"].update({"summary": value.suggested_summary, "bullet_rewrites": rewrites})
            explanations[m.version_id] = entry
        await s.execute(delete(ResumeMatch).where(ResumeMatch.job_id == job_id, ResumeMatch.scoring_config_version == cfg.version))
        for m in ranked:
            e = explanations[m.version_id]
            s.add(ResumeMatch(
                user_id=user_id, job_id=job_id, resume_id=m.resume_id, resume_version_id=m.version_id, score=m.score,
                components=result_to_json(m), mandatory_coverage=m.mandatory_coverage, preferred_coverage=m.preferred_coverage,
                skill_breakdown=m.skill_breakdown, relevant_projects=m.relevant_projects, relevant_experience=m.relevant_experience,
                suggestions=e["suggestions"], explanation=e["explanation"], limitations=[*m.limitations, *e["limitations"]],
                rank=m.rank, is_best=m.is_best, scoring_config_version=cfg.version,
                input_hash=f"{job.description_sha256}:{m.version_id}:{cfg.version}:{emb.model}"))
    best = ranked[0]
    await rank_job(user_id, job_id, best_resume_id=best.resume_id, match_score=best.score)
    return {"resumes_ranked": len(ranked), "best_resume_id": str(best.resume_id), "match_score": best.score}


async def rank_job(user_id: uuid.UUID, job_id: uuid.UUID, best_resume_id: uuid.UUID | None = None,
                   match_score: float | None = None) -> dict[str, Any]:
    cfg = load_scoring_config()
    async with user_session(user_id) as s:
        job = await get_owned(s, Job, job_id, user_id)
        profile = await users_svc.get_profile(s, user_id)
        search = await users_svc.active_search_config(s, user_id)
        if match_score is None:
            best = (await s.execute(select(ResumeMatch).where(ResumeMatch.job_id == job_id, ResumeMatch.is_best,
                                                              ResumeMatch.scoring_config_version == cfg.version))).scalars().first()
            if best:
                match_score, best_resume_id = float(best.score), best.resume_id
        mandatory = (await s.execute(select(JobSkill.evidence_text).where(JobSkill.job_id == job_id,
                                                                          JobSkill.importance == "mandatory"))).scalars().all()
        cities = list(dict.fromkeys([*(profile.preferred_locations or []), *((search.locations if search else []) or [])]))
        remote_ok = "remote" in (profile.preferred_work_modes or []) or any("remote" in c.lower() for c in cities)
        country = None
        for c in [profile.current_location, *cities]:
            if c and (loc := normalize_location(c))["country"]:
                country = loc["country"]
                break
        pref = profile.salary_preference or {}
        pref_min = pref.get("minimum") if pref else None
        if pref_min is None and search and search.salary_minimum is not None:
            pref_min = float(search.salary_minimum)
        collected = job.created_at or datetime.now(tz=UTC)
        years = profile.total_experience_months / 12 if profile.total_experience_months is not None else None
        result = score_job(RankingInput(
            match_score=match_score, posted_at=job.posted_at, collected_at=collected, now=datetime.now(tz=UTC),
            experience_min=float(job.experience_min_years) if job.experience_min_years is not None else None,
            experience_max=float(job.experience_max_years) if job.experience_max_years is not None else None,
            candidate_years=years, job_locations=job.locations or [], work_mode=job.work_mode,
            preferred_cities=[c for c in cities if "remote" not in c.lower()], remote_ok=remote_ok, candidate_country=country or "India",
            salary_min=float(job.salary_min) if job.salary_min is not None else None,
            salary_max=float(job.salary_max) if job.salary_max is not None else None,
            salary_currency=job.salary_currency, salary_period=job.salary_period, salary_source_type=job.salary_source_type,
            pref_salary_min=float(pref_min) if pref_min is not None else None,
            pref_salary_currency=(pref.get("currency") if pref else None) or (search.salary_currency if search else None) or "INR",
            employment_type=job.employment_type, preferred_employment_types=list(profile.employment_type_preferences or []),
            mandatory_texts=[m for m in mandatory if m] + list(job.technical_requirements or []),
            work_authorization=profile.work_authorization, deadline=job.application_deadline,
        ), cfg)
        job.best_resume_id = best_resume_id or job.best_resume_id
        job.match_score = match_score
        job.job_score, job.priority = result.score, result.priority
        job.job_score_breakdown, job.scoring_config_version = result.to_json(), cfg.version
        return result.to_json()


async def rerank_all(user_id: uuid.UUID) -> int:
    async with user_session(user_id) as s:
        ids = (await s.execute(select(Job.id).where(Job.user_id == user_id, Job.status == "analyzed"))).scalars().all()
    for jid in ids:
        await rank_job(user_id, jid)
    return len(ids)


async def default_resume_label(session: AsyncSession, resume_id: uuid.UUID | None) -> str | None:
    if not resume_id:
        return None
    r = await session.get(Resume, resume_id)
    return r.label if r else None

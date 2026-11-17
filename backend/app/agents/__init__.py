"""LLM-backed agents with deterministic heuristic fallbacks (LLM_PROVIDER=none).

Agents never have tools: they turn (prompt + untrusted content) into a validated schema. Every result carries the
model id and prompt/heuristic version for provenance (spec §13.8).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.heuristics import answers as h_answers
from app.heuristics import improve as h_improve
from app.heuristics import job_extract as h_job
from app.heuristics import outreach as h_outreach
from app.heuristics import people as h_people
from app.heuristics import resume_parse as h_resume
from app.integrations.llm import service as llm
from app.schemas.llm.job import JobExtraction, PosterInfo
from app.schemas.llm.other import (
    ApplicationAnswers,
    DailyDigest,
    MatchExplanation,
    OutreachDrafts,
    PeopleClassification,
    ResumeImprovement,
)
from app.schemas.llm.resume import ResumeParsed

HEURISTIC_MODEL = "heuristic-v1"


@dataclass
class AgentMeta:
    model_id: str
    prompt_ref: str
    method: str  # llm | heuristic


def _heuristic(version: str) -> AgentMeta:
    return AgentMeta(HEURISTIC_MODEL, version, "heuristic")


async def extract_job(text: str, *, company_hint: str | None, source_url: str | None, user_id: uuid.UUID,
                      run_id: uuid.UUID | None) -> tuple[JobExtraction, AgentMeta]:
    if not llm.llm_enabled():
        return h_job.extract_job(text, company_hint=company_hint, source_url=source_url), _heuristic(h_job.VERSION)
    r = await llm.structured("jd_extraction", JobExtraction, variables={"company_hint": company_hint, "job_url": source_url},
                             untrusted={"job_description": text[:30000]}, user_id=user_id, agent_run_id=run_id, node="llm_extract")
    return r.value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def parse_resume(text: str, *, user_id: uuid.UUID, run_id: uuid.UUID | None) -> tuple[ResumeParsed, AgentMeta]:
    if not llm.llm_enabled():
        return h_resume.parse_resume(text), _heuristic(h_resume.VERSION)
    r = await llm.structured("resume_parse", ResumeParsed, variables={}, untrusted={"resume_text": text[:30000]},
                             user_id=user_id, agent_run_id=run_id, node="structure")
    return r.value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def explain_match(*, job_title: str, scores: dict[str, Any], job_text: str, resume_evidence: str,
                        user_id: uuid.UUID, run_id: uuid.UUID | None) -> tuple[MatchExplanation, AgentMeta] | None:
    if not llm.llm_enabled():
        return None
    r = await llm.structured("resume_match_explain", MatchExplanation,
                             variables={"job_title": job_title, "scores_json": json.dumps(scores, default=str)[:12000]},
                             untrusted={"job_description": job_text[:12000], "resume_evidence": resume_evidence[:12000]},
                             user_id=user_id, agent_run_id=run_id, node="llm_explain")
    return r.value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def classify_people(items: list[h_people.EvidenceItem], *, company: str, domain: str | None, job_title: str | None,
                          department: str | None, poster: PosterInfo | None, user_id: uuid.UUID,
                          run_id: uuid.UUID | None) -> tuple[PeopleClassification, AgentMeta]:
    if not llm.llm_enabled() or not items:
        return h_people.classify_evidence(items, company, domain, poster), _heuristic("heuristic@v1")
    evidence = "\n".join(json.dumps({"id": i.id, "source_type": i.source_type, "url": i.url, "title": i.title,
                                     "snippet": i.snippet[:600]}) for i in items[:60])
    r = await llm.structured("people_classify", PeopleClassification,
                             variables={"company": company, "domain": domain, "job_title": job_title, "department": department},
                             untrusted={"evidence": evidence}, user_id=user_id, agent_run_id=run_id, node="llm_classify")
    return r.value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def write_outreach(message_types: list[str], ctx: h_outreach.OutreachContext, *, job_summary: str,
                         user_id: uuid.UUID, run_id: uuid.UUID | None, violations: list[str] | None = None
                         ) -> tuple[OutreachDrafts, AgentMeta]:
    if not llm.llm_enabled():
        return h_outreach.write_drafts(message_types, ctx), _heuristic("heuristic@v1")
    linkedin = [m for m in message_types if not m.startswith(("recruiter_", "thank_"))]
    email = [m for m in message_types if m not in linkedin]
    facts = "\n".join(f"{f.id}: {f.text}" for f in ctx.facts)
    history = "Prior contact recorded." if ctx.has_history else "No prior contact."
    if violations:
        history += " Fix these problems from the previous draft: " + "; ".join(violations)
    variables = {"recipient_name": ctx.recipient_name or "(unknown)", "recipient_designation": ctx.recipient_designation or "",
                 "company": ctx.company, "job_title": ctx.job_title, "history": history, "facts": facts,
                 "max_chars": ctx.max_chars, "resume_label": ctx.resume_label or ""}
    drafts: list = []
    meta = None
    for prompt_id, types in (("outreach_linkedin", linkedin), ("outreach_email", email)):
        if not types:
            continue
        r = await llm.structured(prompt_id, OutreachDrafts, variables={**variables, "message_types": ", ".join(types)},
                                 untrusted={"job_summary": job_summary[:6000]}, user_id=user_id, agent_run_id=run_id,
                                 node="llm_generate")
        drafts += [d for d in r.value.drafts if d.message_type in types]
        meta = AgentMeta(r.model_id, r.prompt_ref, "llm")
    return OutreachDrafts(drafts=drafts), meta or _heuristic("heuristic@v1")


async def improve_resume(*, match: dict[str, Any], parsed: ResumeParsed, job_title: str, job_text: str, keywords: list[str],
                         resume_evidence: str, user_id: uuid.UUID, run_id: uuid.UUID | None) -> tuple[ResumeImprovement, AgentMeta]:
    base = h_improve.suggest_improvements(match, parsed, job_title)
    if not llm.llm_enabled():
        return base, _heuristic("heuristic@v1")
    r = await llm.structured("resume_improvement", ResumeImprovement,
                             variables={"job_title": job_title, "keywords": ", ".join(keywords),
                                        "analysis_json": json.dumps({"skill_breakdown": match.get("skill_breakdown")}, default=str)[:8000]},
                             untrusted={"job_description": job_text[:10000], "resume_evidence": resume_evidence[:12000]},
                             user_id=user_id, agent_run_id=run_id, node="llm_suggest")
    value = r.value
    value.missing_evidence = sorted(set(value.missing_evidence) | set(base.missing_evidence))
    return value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def draft_answers(questions: list[str], *, profile: dict[str, Any], facts: dict[str, str], job_summary: str,
                        user_id: uuid.UUID, run_id: uuid.UUID | None) -> tuple[ApplicationAnswers, AgentMeta]:
    base = h_answers.draft_answers(questions, profile, facts)
    if not llm.llm_enabled():
        return base, _heuristic("heuristic@v1")
    all_facts = {**{f"profile:{k}": str(v) for k, v in profile.items() if v not in (None, "", [])}, **facts}
    r = await llm.structured("application_answers", ApplicationAnswers,
                             variables={"questions": json.dumps(questions), "facts": "\n".join(f"{k}: {v}" for k, v in all_facts.items())},
                             untrusted={"job_summary": job_summary[:6000]}, user_id=user_id, agent_run_id=run_id,
                             node="draft_answers")
    # Declarations always stay with the user, even if the model answered them.
    by_q = {a.question: a for a in base.answers}
    for a in r.value.answers:
        if by_q.get(a.question) and h_answers._DECLARATION.search(a.question):
            a.answer, a.needs_user_input, a.source_fact_ids = None, True, []
        if a.answer and not any(fid in all_facts for fid in a.source_fact_ids):
            a.answer, a.needs_user_input = None, True
    return r.value, AgentMeta(r.model_id, r.prompt_ref, "llm")


async def daily_digest(jobs: list[dict[str, Any]], *, user_id: uuid.UUID, run_id: uuid.UUID | None) -> str:
    if not jobs:
        return "No new jobs matched your preferences today."
    lines = [f"{j['title']} at {j['company']} — {j['priority']} ({j['job_score']:.0f})" for j in jobs[:5]]
    templated = f"{len(jobs)} new job(s) analysed. Top: " + "; ".join(lines) + "."
    if not llm.llm_enabled():
        return templated
    try:
        r = await llm.structured("job_recommendation_summary", DailyDigest,
                                 variables={"jobs_json": json.dumps(jobs[:15], default=str)}, untrusted={},
                                 user_id=user_id, agent_run_id=run_id, node="digest")
        return r.value.summary
    except Exception:
        return templated

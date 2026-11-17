"""Outreach drafts, claim checks, Gmail drafts, approval-gated sending (spec §4.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import agents
from app.core.config import get_settings
from app.core.db import user_session
from app.core.errors import ApprovalRequired, NotFound, UnverifiedRecipient, ValidationFailed
from app.domain.claims import ClaimCheck, ClaimContext, check_claims
from app.heuristics.outreach import Fact, OutreachContext
from app.integrations import gmail
from app.models import (
    CandidateProfileFact,
    Company,
    Job,
    JobPerson,
    JobSkill,
    Outreach,
    Person,
    Resume,
    ResumeChunk,
    ResumeVersion,
)
from app.models.enums import EMAIL_MESSAGE_TYPES
from app.schemas.llm.resume import ResumeParsed
from app.services import approvals as approvals_svc
from app.services import oauth as oauth_svc
from app.services import users as users_svc
from app.services.common import audit, get_owned

SENT_STATUSES = ("sent", "manually_sent")


def channel_for(message_type: str) -> str:
    return "email" if message_type in EMAIL_MESSAGE_TYPES else "linkedin"


async def _candidate(session: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID | None) -> tuple[list[Fact], set[str], str | None, uuid.UUID | None]:
    facts: list[Fact] = []
    rows = (await session.execute(select(CandidateProfileFact).where(
        CandidateProfileFact.user_id == user_id, CandidateProfileFact.status == "confirmed",
        CandidateProfileFact.fact_type.in_(("achievement", "project", "experience"))))).scalars().all()
    for f in rows:
        text_ = f.data.get("text") or " ".join(filter(None, [f.data.get("title"), f.data.get("description"), *(f.data.get("bullets") or [])[:1]]))
        if text_:
            facts.append(Fact(f"fact:{f.id}", text_[:300], f.fact_type))
    skills, label = set(), None
    if resume_id:
        resume = await session.get(Resume, resume_id)
        version = await session.get(ResumeVersion, resume.current_version_id) if resume and resume.current_version_id else None
        label = resume.label if resume else None
        if version and version.parsed_data:
            parsed = ResumeParsed.model_validate(version.parsed_data)
            skills |= {s.name for s in parsed.skills}
            chunks = (await session.execute(select(ResumeChunk).where(ResumeChunk.resume_version_id == version.id))).scalars().all()
            by_ref = {c.item_ref: c for c in chunks}
            for i, a in enumerate(parsed.achievements):
                c = by_ref.get(f"achievements[{i}]")
                facts.append(Fact(f"chunk:{c.id}" if c else f"achievement:{i}", a.text, "achievement"))
            for i, e in enumerate(parsed.experience):
                c = by_ref.get(f"experience[{i}]")
                for b in e.bullets[:2]:
                    if any(ch.isdigit() for ch in b):
                        facts.append(Fact(f"chunk:{c.id}" if c else f"experience:{i}", b, "achievement"))
            for i, p in enumerate(parsed.projects):
                c = by_ref.get(f"projects[{i}]")
                desc = (p.bullets[0] if p.bullets else p.description) or ""
                facts.append(Fact(f"chunk:{c.id}" if c else f"project:{i}", f"{p.title}: {desc}".strip(": "), "project"))
    has, _missing = await users_svc.confirmed_skills(session, user_id)
    return facts, skills | has, label, resume_id


def _claim_ctx(facts: list[Fact], skills: set[str], has_history: bool, recipient_email: str | None, company: str,
               job_title: str, max_chars: int | None, max_words: int | None) -> ClaimContext:
    return ClaimContext(evidence_texts=[f.text for f in facts], candidate_skills=skills, has_relationship_history=has_history,
                        recipient_verified_email=recipient_email, company_name=company, job_title=job_title,
                        max_chars=max_chars, max_words=max_words)


def _limits(message_type: str) -> tuple[int | None, int | None]:
    if message_type == "linkedin_connection":
        return get_settings().linkedin_connection_note_max_chars, None
    return None, 180 if channel_for(message_type) == "email" else 150


async def generate(user_id: uuid.UUID, run_id: uuid.UUID | None, job_id: uuid.UUID, person_ids: list[uuid.UUID] | None,
                   message_types: list[str], resume_id: uuid.UUID | None) -> dict[str, Any]:
    async with user_session(user_id) as s:
        job = await get_owned(s, Job, job_id, user_id)
        company = await s.get(Company, job.company_id) if job.company_id else None
        resume_id = resume_id or job.best_resume_id
        facts, cand_skills, label, resume_id = await _candidate(s, user_id, resume_id)
        profile = await users_svc.get_profile(s, user_id)
        job_skills = (await s.execute(select(JobSkill.normalized_name).where(JobSkill.job_id == job_id)
                                      .order_by(JobSkill.importance))).scalars().all()
        if person_ids:
            persons = [await get_owned(s, Person, pid, user_id) for pid in person_ids]
        else:
            persons = [p for _, p in (await s.execute(select(JobPerson, Person).join(Person, Person.id == JobPerson.person_id)
                                                     .where(JobPerson.job_id == job_id).order_by(JobPerson.rank).limit(3))).all()]
        targets: list[Person | None] = [p for p in persons if p.contact_status != "do_not_contact"] or [None]
        history = dict((await s.execute(select(Outreach.person_id, func.count()).where(
            Outreach.user_id == user_id, Outreach.status.in_(SENT_STATUSES)).group_by(Outreach.person_id))).all())
        job_title, company_name = job.title or "the role", company.name if company else "your company"
        summary = "\n".join(filter(None, [job.title, company_name, *(job.responsibilities or [])[:5]]))
    skills = [s for s in job_skills if s in cand_skills][:3]
    created: list[str] = []
    blocked = 0
    for person in targets:
        has_hist = bool(person and history.get(person.id))
        types = [m for m in message_types if has_hist or m not in ("linkedin_follow_up", "recruiter_follow_up", "thank_you")]
        if not types:
            continue
        octx = OutreachContext(candidate_name=profile.full_name, recipient_name=person.name if person else None,
                               recipient_designation=person.designation if person else None, company=company_name,
                               job_title=job_title, facts=facts, skills=skills, resume_label=label, has_history=has_hist,
                               max_chars=get_settings().linkedin_connection_note_max_chars,
                               extra={"job_skills": list(job_skills)})
        drafts, meta = await agents.write_outreach(types, octx, job_summary=summary, user_id=user_id, run_id=run_id)
        checked = []
        for d in drafts.drafts:
            email = person.public_email if (person and channel_for(d.message_type) == "email") else None
            mc, mw = _limits(d.message_type)
            ctx = _claim_ctx(facts, cand_skills, has_hist, email, company_name, job_title, mc, mw)
            result = check_claims(d.body, d.subject, None, ctx)
            checked.append((d, result, email))
        if meta.method == "llm" and any(not r.passed for _, r, _ in checked):
            problems = [v["detail"] for _, r, _ in checked for v in r.blocking]
            redo, meta = await agents.write_outreach(types, octx, job_summary=summary, user_id=user_id, run_id=run_id,
                                                     violations=problems[:10])
            checked = []
            for d in redo.drafts:
                email = person.public_email if (person and channel_for(d.message_type) == "email") else None
                mc, mw = _limits(d.message_type)
                checked.append((d, check_claims(d.body, d.subject, None,
                                                _claim_ctx(facts, cand_skills, has_hist, email, company_name, job_title, mc, mw)), email))
        by_id = {f.id: f for f in facts}
        async with user_session(user_id) as s:
            for d, result, email in checked:
                blocked += 0 if result.passed else 1
                o = Outreach(user_id=user_id, job_id=job_id, person_id=person.id if person else None, message_type=d.message_type,
                             channel=channel_for(d.message_type), recipient_name=person.name if person else None,
                             recipient_email=email, subject=d.subject, body=d.body, recommended_resume_id=resume_id,
                             personalization_evidence=[{"id": i, "text": by_id[i].text, "kind": by_id[i].kind}
                                                       for i in d.used_evidence_ids if i in by_id],
                             claim_check=result.to_json(), requires_review=True, status="draft",
                             prompt_version=meta.prompt_ref, model_id=meta.model_id)
                s.add(o)
                await s.flush()
                created.append(str(o.id))
    return {"outreach_ids": created, "drafts": len(created), "with_blocking_issues": blocked}


async def _resume_for(s: AsyncSession, user_id: uuid.UUID, job: Job | None) -> uuid.UUID | None:
    if job and job.best_resume_id:
        return job.best_resume_id
    return (await s.execute(select(Resume.id).where(Resume.user_id == user_id)
                            .order_by(Resume.is_default.desc(), Resume.created_at))).scalars().first()


async def recheck(s: AsyncSession, user_id: uuid.UUID, o: Outreach) -> ClaimCheck:
    job = await s.get(Job, o.job_id) if o.job_id else None
    company = await s.get(Company, job.company_id) if job and job.company_id else None
    person = await s.get(Person, o.person_id) if o.person_id else None
    o.recommended_resume_id = o.recommended_resume_id or await _resume_for(s, user_id, job)
    facts, skills, _, _ = await _candidate(s, user_id, o.recommended_resume_id)
    facts += [Fact(e["id"], e["text"], e.get("kind", "fact")) for e in (o.personalization_evidence or [])]
    has_hist = bool(person and (await s.execute(select(Outreach.id).where(
        Outreach.person_id == person.id, Outreach.status.in_(SENT_STATUSES), Outreach.id != o.id))).first())
    mc, mw = _limits(o.message_type)
    ctx = _claim_ctx(facts, skills, has_hist, person.public_email if person else None,
                     company.name if company else "", job.title if job else "", mc, mw)
    result = check_claims(o.body, o.subject, o.recipient_email, ctx)
    o.claim_check = result.to_json()
    return result


async def create_manual(s: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID | None, person_id: uuid.UUID | None,
                        message_type: str, subject: str | None, body: str) -> Outreach:
    person = await get_owned(s, Person, person_id, user_id) if person_id else None
    if job_id:
        await get_owned(s, Job, job_id, user_id)
    channel = channel_for(message_type)
    o = Outreach(user_id=user_id, job_id=job_id, person_id=person_id, message_type=message_type, channel=channel,
                 recipient_name=person.name if person else None,
                 recipient_email=person.public_email if (person and channel == "email") else None,
                 subject=subject, body=body, status="edited", prompt_version="user", model_id="user")
    s.add(o)
    await s.flush()
    await recheck(s, user_id, o)
    return o


def _send_payload(o: Outreach) -> dict[str, Any]:
    return {"outreach_id": str(o.id), "to": o.recipient_email, "subject": o.subject or "", "body": o.body}


async def request_send_approval(s: AsyncSession, user_id: uuid.UUID, o: Outreach):
    if o.channel != "email":
        raise ApprovalRequired("LinkedIn messages are sent manually. Copy the text and mark it as sent.",
                               details={"reason": "manual_channel"})
    if o.status in SENT_STATUSES or o.status == "discarded":
        raise ApprovalRequired(f"This message is already {o.status}.")
    person = await s.get(Person, o.person_id) if o.person_id else None
    if not o.recipient_email or not person or person.public_email != o.recipient_email:
        raise UnverifiedRecipient("There is no verified public email for this recipient; send it yourself instead.")
    check = await recheck(s, user_id, o)
    if not check.passed:
        raise ApprovalRequired("Fix the flagged claims before sending.", details={"violations": check.blocking})
    await oauth_svc.access_token(user_id)  # must be connected
    return await approvals_svc.create_pending(s, user_id, "send_email", "outreach", o.id, _send_payload(o))


async def approve_and_send(user_id: uuid.UUID, outreach_id: uuid.UUID, approval_id: uuid.UUID, given_hash: str) -> dict[str, Any]:
    """Decide → consume (committed before any external call) → send → record. A failed or timed-out send can
    never be retried with the same approval: the user must look at Gmail and request a fresh approval."""
    from app.core.errors import UpstreamError
    from app.models import Approval

    async with user_session(user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, user_id)
        approval = await approvals_svc.decide(s, user_id, approval_id, given_hash)
        if approval.reference_id != o.id:
            raise NotFound()
        if approval.status == "executed":
            return {"status": o.status, "gmail_message_id": o.gmail_message_id, "sent_at": o.sent_at}
    token, sender = await oauth_svc.access_token(user_id)
    async with user_session(user_id) as s:  # 1) consume — committed before Gmail is called
        o = await get_owned(s, Outreach, outreach_id, user_id)
        await approvals_svc.consume(s, user_id, approval_id, _send_payload(o))
        to, subject, body = o.recipient_email or "", o.subject or "", o.body
    try:  # 2) external call, outside any transaction
        message_id = await gmail.send_message(token, to, subject, body, sender)
    except Exception as exc:
        timed_out = "timeout" in type(exc).__name__.lower() or "timeout" in str(getattr(exc, "details", "")).lower()
        async with user_session(user_id) as s:  # 3a) record the failure separately
            approval = await s.get(Approval, approval_id)
            await approvals_svc.record_result(s, approval, False, {
                "error": getattr(exc, "code", type(exc).__name__), "outcome": "unknown" if timed_out else "failed"})
        raise UpstreamError("Sending failed or timed out. Check your Gmail Sent folder before requesting approval again.",
                            details={"outcome": "unknown" if timed_out else "failed"}, code="send_failed") from exc
    async with user_session(user_id) as s:  # 3b) record success
        o = await get_owned(s, Outreach, outreach_id, user_id)
        approval = await s.get(Approval, approval_id)
        o.status, o.sent_at, o.gmail_message_id = "sent", datetime.now(tz=UTC), message_id
        await approvals_svc.record_result(s, approval, True, {"sent": True}, {"gmail_message_id": message_id})
        if o.person_id:
            person = await s.get(Person, o.person_id)
            if person and person.contact_status == "new":
                person.contact_status = "contacted"
        await audit(s, user_id, "outreach.sent", "outreach", o.id, channel="email")
        return {"status": "sent", "gmail_message_id": message_id, "sent_at": o.sent_at}


async def create_gmail_draft(user_id: uuid.UUID, outreach_id: uuid.UUID) -> Outreach:
    async with user_session(user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, user_id)
        if o.channel != "email":
            raise ValidationFailed("Only email messages can become Gmail drafts.")
    token, sender = await oauth_svc.access_token(user_id)
    draft_id = await gmail.create_draft(token, o.recipient_email, o.subject or "", o.body, sender)
    async with user_session(user_id) as s:
        o = await get_owned(s, Outreach, outreach_id, user_id)
        o.gmail_draft_id, o.status = draft_id, "gmail_draft_created"
        await audit(s, user_id, "outreach.gmail_draft_created", "outreach", o.id)
        return o

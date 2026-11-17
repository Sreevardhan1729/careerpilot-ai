"""Tailored resume versions (spec §4.2 "Resume versioning"; FR-RES-13; AT-18).

Accepted suggestions become a *new* DOCX version (parent → child). Every changed text must pass the claim check
against the same resume item's own text, skill reordering may only use skills already in the resume, and the
version becomes active only through an approval. The original file is never modified.
"""

from __future__ import annotations

import io
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.db import user_session
from app.core.errors import ApprovalRequired, NotFound, ValidationFailed
from app.domain.claims import ClaimContext, check_claims
from app.domain.skills import get_taxonomy
from app.domain.text import normalize_for_match, sha256_hex
from app.integrations.parsing.documents import DOCX_MIME
from app.integrations.storage import get_storage
from app.models import Resume, ResumeVersion
from app.schemas.llm.resume import ResumeParsed
from app.services import approvals as approvals_svc
from app.services.common import audit, get_owned

ATS_ORDER = ["summary", "skills", "experience", "projects", "education", "certifications", "achievements"]


def render_docx(parsed: ResumeParsed, skill_order: list[str] | None = None) -> tuple[bytes, str]:
    """ATS-friendly single-column DOCX. Returns (bytes, plain text)."""
    import docx

    d = docx.Document()
    lines: list[str] = []

    def para(text: str, style: str | None = None) -> None:
        d.add_paragraph(text, style=style)
        lines.append(text)

    def heading(text: str, level: int = 1) -> None:
        d.add_heading(text, level=level)
        lines.append(text.upper() if level == 1 else text)

    c = parsed.contact
    if c.name:
        d.add_heading(c.name, level=0)
        lines.append(c.name)
    contact = " | ".join(filter(None, [c.location, c.email, c.phone, c.linkedin_url, c.github_url, c.portfolio_url]))
    if contact:
        para(contact)
    skills = list(dict.fromkeys(s.name for s in parsed.skills))
    if skill_order:
        skills = [s for s in skill_order if s in skills] + [s for s in skills if s not in skill_order]
    for section in ATS_ORDER:
        if section == "summary" and parsed.summary:
            heading("Summary")
            para(parsed.summary)
        elif section == "skills" and skills:
            heading("Skills")
            para(", ".join(skills))
        elif section == "experience" and parsed.experience:
            heading("Experience")
            for e in parsed.experience:
                heading(" | ".join(filter(None, [e.title, e.company, " - ".join(filter(None, [e.start, e.end]))])), level=2)
                for b in e.bullets:
                    para(b, "List Bullet")
        elif section == "projects" and parsed.projects:
            heading("Projects")
            for p in parsed.projects:
                heading(p.title or "Project", level=2)
                if p.description:
                    para(p.description)
                for b in p.bullets:
                    para(b, "List Bullet")
        elif section == "education" and parsed.education:
            heading("Education")
            for ed in parsed.education:
                para(", ".join(filter(None, [ed.degree, ed.institution, ed.year])))
        elif section == "certifications" and parsed.certifications:
            heading("Certifications")
            for cert in parsed.certifications:
                para(cert, "List Bullet")
        elif section == "achievements" and parsed.achievements:
            heading("Achievements")
            for a in parsed.achievements:
                para(a.text, "List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue(), "\n".join(lines)


def _apply_change(parsed: ResumeParsed, before: str, after: str) -> str:
    """Replace one existing text; returns the text of the item it belongs to (claim-check evidence)."""
    want = normalize_for_match(before)
    if parsed.summary and normalize_for_match(parsed.summary) == want:
        parsed.summary = after
        return before
    for item in (*parsed.experience, *parsed.projects):
        for i, b in enumerate(item.bullets):
            if normalize_for_match(b) == want:
                own = "\n".join([*(x for x in item.bullets), getattr(item, "description", None) or "", " ".join(item.technologies)])
                item.bullets[i] = after
                return own
        if getattr(item, "description", None) and normalize_for_match(item.description) == want:
            own = "\n".join([item.description, *item.bullets])
            item.description = after
            return own
    for a in parsed.achievements:
        if normalize_for_match(a.text) == want:
            a.text = after
            return before
    raise ValidationFailed("A change refers to text that isn't in this resume version.", details={"before": before[:200]})


async def create_tailored(user_id: uuid.UUID, resume_id: uuid.UUID, *, base_version_id: uuid.UUID | None, job_id: uuid.UUID | None,
                          changes: list[dict[str, Any]], skill_order: list[str] | None, change_summary: str | None) -> dict[str, Any]:
    tax = get_taxonomy()
    async with user_session(user_id) as s:
        resume = await get_owned(s, Resume, resume_id, user_id)
        base = await get_owned(s, ResumeVersion, base_version_id or resume.current_version_id, user_id)
        if base.resume_id != resume.id or not base.parsed_data:
            raise NotFound("The base version has no parsed data.")
        if job_id:
            from app.models import Job

            await get_owned(s, Job, job_id, user_id)
        parsed = ResumeParsed.model_validate(base.parsed_data)
        next_number = int((await s.execute(select(func.max(ResumeVersion.version_number))
                                           .where(ResumeVersion.resume_id == resume.id))).scalar_one()) + 1
        label = resume.label
    skills = {sk.name for sk in parsed.skills}
    if skill_order:
        unknown = [x for x in (tax.normalize_name(n) for n in skill_order) if x not in skills]
        if unknown:
            raise ValidationFailed("Skill order may only use skills already in this resume.", details={"unknown": unknown})
        skill_order = [tax.normalize_name(n) for n in skill_order]
        by_name = {sk.name: sk for sk in parsed.skills}
        parsed.skills = [by_name[n] for n in skill_order] + [sk for sk in parsed.skills if sk.name not in skill_order]
    if not changes and not skill_order:
        raise ValidationFailed("Nothing to change.")
    for ch in changes:
        before, after = (ch.get("before") or "").strip(), (ch.get("after") or "").strip()
        if not before or not after:
            raise ValidationFailed("Each change needs 'before' and 'after' text.")
        own_text = _apply_change(parsed, before, after)
        result = check_claims(after, None, None, ClaimContext(evidence_texts=[before, own_text], candidate_skills=skills,
                                                              has_relationship_history=True, recipient_verified_email=None))
        if not result.passed:
            raise ValidationFailed("A change adds something your resume doesn't support.", details={"violations": result.blocking})
    data, rendered_text = render_docx(parsed, skill_order)
    key = f"{user_id}/{uuid.uuid4()}.docx"
    await get_storage().put(key, data, DOCX_MIME)
    async with user_session(user_id) as s:
        version = ResumeVersion(user_id=user_id, resume_id=resume_id, version_number=next_number, parent_version_id=base.id,
                                storage_key=key, file_sha256=sha256_hex(data), mime_type=DOCX_MIME, file_size_bytes=len(data),
                                original_filename=f"{label} - tailored v{next_number}.docx"[:120], extracted_text=rendered_text,
                                parsed_data=parsed.model_dump(mode="json"), parsed_data_origin="tailored", parse_method="tailored",
                                approval_status="pending_approval", change_summary=(change_summary or "Tailored version")[:500],
                                job_id=job_id)
        s.add(version)
        await s.flush()
        approval = await approvals_svc.create_pending(s, user_id, "activate_resume_version", "resume_version", version.id,
                                                      _activation_payload(version),
                                                      {"resume": label, "version_number": next_number, "changes": changes,
                                                       "skill_order": skill_order, "change_summary": version.change_summary})
        version.approval_id = approval.id
        await audit(s, user_id, "resume.version_created", "resume_version", version.id, parent=str(base.id))
        version_id = version.id
        out = {"version": version, "approval": approval}
    from app.integrations.embeddings import get_embeddings
    from app.models import ResumeChunk
    from app.services.resumes import build_chunks  # index the new version for matching (no re-parse needed)

    chunks = build_chunks(parsed)
    emb = get_embeddings()
    vectors = await emb.embed_documents([c["content"] for c in chunks])
    async with user_session(user_id) as s:
        for c, v in zip(chunks, vectors, strict=True):
            s.add(ResumeChunk(user_id=user_id, resume_version_id=version_id, content_sha256=sha256_hex(c["content"]),
                              embedding=v, embedding_model=emb.model, **c))
    return out


def _activation_payload(version: ResumeVersion) -> dict[str, Any]:
    return {"resume_id": str(version.resume_id), "version_id": str(version.id), "file_sha256": version.file_sha256}


async def activate(user_id: uuid.UUID, resume_id: uuid.UUID, version_id: uuid.UUID, approval_id: uuid.UUID, given_hash: str) -> dict[str, Any]:
    async with user_session(user_id) as s:
        version = await get_owned(s, ResumeVersion, version_id, user_id)
        if version.resume_id != resume_id:
            raise NotFound()
        approval = await approvals_svc.decide(s, user_id, approval_id, given_hash)
        if approval.reference_id != version.id or approval.action_type != "activate_resume_version":
            raise ApprovalRequired("That approval is for a different action.")
        if approval.status == "executed":
            resume = await s.get(Resume, resume_id)
            return {"status": "active", "current_version_id": str(resume.current_version_id)}
    async with user_session(user_id) as s:
        version = await get_owned(s, ResumeVersion, version_id, user_id)
        approval = await approvals_svc.consume(s, user_id, approval_id, _activation_payload(version))
        resume = await get_owned(s, Resume, resume_id, user_id)
        resume.current_version_id, version.approval_status = version.id, "approved"
        await approvals_svc.record_result(s, approval, True, {"activated": str(version.id)})
        await audit(s, user_id, "resume.version_activated", "resume_version", version.id)
        return {"status": "active", "current_version_id": str(version.id)}

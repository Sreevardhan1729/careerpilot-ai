"""Resume library: upload, ingestion persistence, corrections, versions, matching inputs (spec §4.2)."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePath
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import user_session
from app.core.errors import Duplicate, NotFound
from app.domain.matching import ResumeForMatch, ResumeItem
from app.domain.skills import get_taxonomy
from app.domain.text import chunk_text, normalize_for_match, sha256_hex
from app.integrations.embeddings import get_embeddings
from app.integrations.parsing.documents import validate_upload
from app.integrations.storage import get_storage
from app.models import Resume, ResumeChunk, ResumeVersion
from app.schemas.llm.resume import ResumeParsed
from app.services import users as users_svc
from app.services.common import audit, get_owned
from app.tasks import queue

LABELS = [
    ("GenAI / LLM Engineer", {"llm_engineering", "retrieval_vector_db"}, re.compile(r"genai|llm|generative", re.I)),
    ("ML Engineer", {"ai_ml"}, re.compile(r"\bml\b|machine learning|data scientist", re.I)),
    ("AI Engineer", {"ai_ml", "llm_engineering"}, re.compile(r"\bai\b", re.I)),
    ("Data Engineer", {"data_engineering"}, re.compile(r"data engineer", re.I)),
    ("Backend Engineer", {"frameworks_libraries", "databases", "system_design"}, re.compile(r"backend|api", re.I)),
    ("Full Stack Engineer", {"frameworks_libraries"}, re.compile(r"full[\s-]?stack|frontend|react", re.I)),
]


def _safe_filename(name: str) -> str:
    base = PurePath(name or "resume").name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:120] or "resume"


async def create_upload(user_id: uuid.UUID, data: bytes, filename: str, label: str | None) -> tuple[Resume, ResumeVersion, uuid.UUID]:
    s = get_settings()
    info = validate_upload(data, s.max_upload_mb, s.max_resume_pages)
    digest = sha256_hex(data)
    async with user_session(user_id) as session:
        dup = (await session.execute(select(ResumeVersion).where(ResumeVersion.user_id == user_id,
                                                                  ResumeVersion.file_sha256 == digest))).scalars().first()
        if dup:
            raise Duplicate("This file is already in your resume library.", details={"resume_id": str(dup.resume_id)})
        has_default = (await session.execute(select(Resume.id).where(Resume.user_id == user_id, Resume.is_default))).first()
        resume = Resume(user_id=user_id, label=(label or PurePath(_safe_filename(filename)).stem)[:80], status="uploaded",
                        is_default=has_default is None)
        session.add(resume)
        await session.flush()
        key = f"{user_id}/{uuid.uuid4()}.{info.kind}"
        await get_storage().put(key, data, info.mime_type)
        version = ResumeVersion(user_id=user_id, resume_id=resume.id, version_number=1, storage_key=key, file_sha256=digest,
                                mime_type=info.mime_type, file_size_bytes=info.size, original_filename=_safe_filename(filename),
                                page_count=info.page_count, approval_status="original")
        session.add(version)
        await session.flush()
        resume.current_version_id = version.id
        await audit(session, user_id, "resume.uploaded", "resume", resume.id)
    run, _, _ = await queue.enqueue(user_id=user_id, task_type="parse_resume", priority=1,
                                    payload={"resume_id": str(resume.id), "version_id": str(version.id)},
                                    idempotency_key=f"parse_resume:{version.id}", subject_type="resume", subject_id=resume.id)
    return resume, version, run.id


def suggest_label(parsed: ResumeParsed) -> str:
    tax = get_taxonomy()
    cats: dict[str, int] = {}
    for s in parsed.skills:
        c = tax.category_of(s.name, "")
        cats[c] = cats.get(c, 0) + 1
    titles = " ".join(filter(None, [*(e.title or "" for e in parsed.experience), parsed.summary or ""]))
    best, best_score = "Software Engineer", 0.0
    for label, categories, pattern in LABELS:
        score = sum(cats.get(c, 0) for c in categories) + (6 if pattern.search(titles) else 0)
        if score > best_score:
            best, best_score = label, score
    return best


def verify_parsed(parsed: ResumeParsed, text: str) -> tuple[ResumeParsed, list[str]]:
    """Drop parsed claims that are not in the resume text (LLM output); canonicalise skills. Whole items are verified,
    so an invented tail on a real bullet ("…cutting latency by 70%") removes the bullet."""
    from app.domain.evidence import verify_snippet

    tax = get_taxonomy()
    norm_text = normalize_for_match(text)
    in_text = {m.entry.canonical for m in tax.find_in_text(text)}

    def present(name: str) -> bool:
        entry = tax.canonicalize(name)
        return normalize_for_match(name) in norm_text or bool(entry and entry.canonical in in_text)

    def verified(item: str | None) -> bool:
        if not item:
            return False
        n = normalize_for_match(item)
        return n in norm_text if len(n) < 12 else verify_snippet(item, text)

    warnings: list[str] = []
    kept, seen = [], set()
    for sk in parsed.skills:
        entry = tax.canonicalize(sk.name)
        name = entry.canonical if entry else sk.name
        if not present(sk.name):
            warnings.append(f"Dropped skill not found in the text: {sk.name}")
            continue
        if (name, sk.section) not in seen:
            seen.add((name, sk.section))
            kept.append(sk.model_copy(update={"name": name}))
    parsed.skills = kept
    dropped = 0
    for item in (*parsed.experience, *parsed.projects):
        item.technologies = sorted({(tax.canonicalize(t).canonical if tax.canonicalize(t) else t)
                                    for t in item.technologies if present(t)})
        item.domains = sorted({d for d in (tax.canonical_domain(x) for x in item.domains) if d})
        before = len(item.bullets)
        item.bullets = [b for b in item.bullets if verified(b)]
        dropped += before - len(item.bullets)
        if getattr(item, "description", None) and not verified(item.description):
            item.description = None
    if dropped:
        warnings.append(f"Dropped {dropped} bullet(s) that don't match the resume text.")
    parsed.domains = sorted({d for d in (tax.canonical_domain(x) for x in parsed.domains) if d} |
                            {d for i in (*parsed.experience, *parsed.projects) for d in i.domains})
    parsed.achievements = [a for a in parsed.achievements if verified(a.text)]
    parsed.certifications = [c for c in parsed.certifications if verified(c)]
    if parsed.summary and not verified(parsed.summary[:600]):
        parsed.summary = None
        warnings.append("The parsed summary didn't match the resume text and was removed.")
    if not parsed.skills:
        warnings.append("No skills were detected. Check the parsed data and add them if needed.")
    if not parsed.experience and not parsed.projects:
        warnings.append("No experience or projects were detected.")
    if len(text) < 400:
        warnings.append("Very little text was extracted — is this a scanned PDF?")
    return parsed, warnings


def build_chunks(parsed: ResumeParsed) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if parsed.summary:
        chunks.append({"section": "summary", "section_index": 0, "item_ref": "summary", "content": parsed.summary})
    skill_names = [s.name for s in parsed.skills if s.section == "skills"]
    if skill_names:
        chunks.append({"section": "skills", "section_index": 0, "item_ref": "skills", "content": "Skills: " + ", ".join(skill_names)})
    for i, e in enumerate(parsed.experience):
        head = f"Experience: {e.title or ''} at {e.company or ''}. Technologies: {', '.join(e.technologies)}"
        for j, part in enumerate(chunk_text("\n".join([head, *e.bullets]), 1200)):
            chunks.append({"section": "experience", "section_index": i, "item_ref": f"experience[{i}]" + (f"#{j}" if j else ""), "content": part})
    for i, p in enumerate(parsed.projects):
        head = f"Project: {p.title or ''}. {p.description or ''} Technologies: {', '.join(p.technologies)}"
        for j, part in enumerate(chunk_text("\n".join([head, *p.bullets]), 1200)):
            chunks.append({"section": "project", "section_index": i, "item_ref": f"projects[{i}]" + (f"#{j}" if j else ""), "content": part})
    for i, ed in enumerate(parsed.education):
        chunks.append({"section": "education", "section_index": i, "item_ref": f"education[{i}]",
                       "content": " ".join(filter(None, [ed.degree, ed.institution, ed.year, ed.details]))})
    for i, c in enumerate(parsed.certifications):
        chunks.append({"section": "certification", "section_index": i, "item_ref": f"certifications[{i}]", "content": c})
    for i, a in enumerate(parsed.achievements):
        chunks.append({"section": "achievement", "section_index": i, "item_ref": f"achievements[{i}]", "content": a.text})
    return [c for c in chunks if c["content"].strip()]


async def persist_ingestion(user_id: uuid.UUID, resume_id: uuid.UUID, version_id: uuid.UUID, text: str, page_count: int | None,
                            parsed: ResumeParsed, warnings: list[str], method: str, origin: str = "llm") -> None:
    chunks = build_chunks(parsed)
    emb = get_embeddings()
    vectors = await emb.embed_documents([c["content"] for c in chunks])
    async with user_session(user_id) as s:
        version = await get_owned(s, ResumeVersion, version_id, user_id)
        resume = await get_owned(s, Resume, resume_id, user_id)
        if version.extracted_text is None:
            version.extracted_text = text
        version.page_count = version.page_count or page_count
        version.parsed_data = parsed.model_dump(mode="json")
        version.parsed_data_origin = origin
        version.parse_method = method
        version.parse_warnings = warnings
        await s.execute(delete(ResumeChunk).where(ResumeChunk.resume_version_id == version_id))
        for c, v in zip(chunks, vectors, strict=True):
            s.add(ResumeChunk(user_id=user_id, resume_version_id=version_id, content_sha256=sha256_hex(c["content"]),
                              embedding=v, embedding_model=emb.model, **c))
        resume.label_suggested = suggest_label(parsed)
        resume.status = "needs_review" if warnings else "parsed"
    await suggest_profile_facts(user_id, version_id, parsed)


async def suggest_profile_facts(user_id: uuid.UUID, version_id: uuid.UUID, parsed: ResumeParsed) -> None:
    """Resume-derived facts become *suggestions*; confirmed facts and user-entered fields are never overwritten."""
    async with user_session(user_id) as s:
        for skill in {sk.name for sk in parsed.skills}:
            await users_svc.add_fact(s, user_id, "skill", {"name": skill, "has_skill": True}, "resume_derived", "suggested", version_id)
        for e in parsed.experience:
            await users_svc.add_fact(s, user_id, "experience", e.model_dump(mode="json"), "resume_derived", "suggested", version_id)
        for p in parsed.projects:
            await users_svc.add_fact(s, user_id, "project", p.model_dump(mode="json"), "resume_derived", "suggested", version_id)
        for ed in parsed.education:
            await users_svc.add_fact(s, user_id, "education", ed.model_dump(mode="json"), "resume_derived", "suggested", version_id)
        for c in parsed.certifications:
            await users_svc.add_fact(s, user_id, "certification", {"name": c}, "resume_derived", "suggested", version_id)
        for a in parsed.achievements:
            await users_svc.add_fact(s, user_id, "achievement", a.model_dump(mode="json"), "resume_derived", "suggested", version_id)
        profile = await users_svc.get_profile(s, user_id)
        sources = dict(profile.field_sources or {})
        contact = parsed.contact
        for field_name, value in (("full_name", contact.name), ("phone", contact.phone), ("linkedin_url", contact.linkedin_url),
                                  ("github_url", contact.github_url), ("portfolio_url", contact.portfolio_url),
                                  ("current_location", contact.location)):
            if value and not getattr(profile, field_name) and sources.get(field_name) != "user_entered":
                setattr(profile, field_name, value)
                sources[field_name] = "resume_derived"
        if profile.total_experience_months is None and sources.get("total_experience_months") != "user_entered":
            months = sum((e.months or 0) * (0.5 if e.is_internship else 1) for e in parsed.experience)
            if parsed.experience and months:
                profile.total_experience_months = int(round(months))
                sources["total_experience_months"] = "resume_derived"
        profile.field_sources = sources


async def set_default(session: AsyncSession, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    await session.execute(update(Resume).where(Resume.user_id == user_id, Resume.is_default).values(is_default=False))
    await session.flush()
    resume = await get_owned(session, Resume, resume_id, user_id)
    resume.is_default = True


async def resumes_for_matching(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeForMatch]:
    tax = get_taxonomy()
    rows = (await session.execute(select(Resume, ResumeVersion).join(ResumeVersion, ResumeVersion.id == Resume.current_version_id)
                                  .where(Resume.user_id == user_id, Resume.status.in_(("parsed", "needs_review")),
                                         ResumeVersion.parsed_data.is_not(None)))).all()
    out = []
    for resume, version in rows:
        parsed = ResumeParsed.model_validate(version.parsed_data)
        chunks = (await session.execute(select(ResumeChunk).where(ResumeChunk.resume_version_id == version.id)
                                        .order_by(ResumeChunk.section, ResumeChunk.section_index))).scalars().all()
        emb_by_ref = {}
        for c in chunks:
            base_ref = (c.item_ref or "").split("#")[0]
            emb_by_ref.setdefault(base_ref, list(c.embedding) if c.embedding is not None else None)
        evidenced: dict[str, list[str]] = {}
        for i, e in enumerate(parsed.experience):
            for t in e.technologies:
                evidenced.setdefault(t, []).append(f"experience[{i}]")
        for i, p in enumerate(parsed.projects):
            for t in p.technologies:
                evidenced.setdefault(t, []).append(f"projects[{i}]")
        projects = [ResumeItem(ref=f"projects[{i}]", kind="project", title=p.title or f"Project {i + 1}",
                               technologies=set(p.technologies), text="\n".join(p.bullets), embedding=emb_by_ref.get(f"projects[{i}]"),
                               months=None, is_internship=False, domains={d for d in p.domains})
                    for i, p in enumerate(parsed.projects)]
        experience = [ResumeItem(ref=f"experience[{i}]", kind="experience", title=e.title or f"Role {i + 1}",
                                 technologies=set(e.technologies), text="\n".join(e.bullets),
                                 embedding=emb_by_ref.get(f"experience[{i}]"), months=e.months, is_internship=e.is_internship,
                                 domains={d for d in e.domains})
                      for i, e in enumerate(parsed.experience)]
        out.append(ResumeForMatch(
            resume_id=resume.id, version_id=version.id, created_at=version.created_at,
            # every verified skill counts as "listed"; only verified item technologies count as strong evidence
            skills_section={tax.normalize_name(sk.name) for sk in parsed.skills},
            evidenced_skills=evidenced, projects=projects, experience=experience,
            chunks=[(f"chunk:{c.id}", list(c.embedding) if c.embedding is not None else None) for c in chunks
                    if c.section in ("experience", "project", "summary")],
            domains=set(parsed.domains),
        ))
    return out


async def get_version_bytes(user_id: uuid.UUID, resume_id: uuid.UUID, version_id: uuid.UUID) -> tuple[ResumeVersion, bytes]:
    async with user_session(user_id) as s:
        version = await get_owned(s, ResumeVersion, version_id, user_id)
        if version.resume_id != resume_id:
            raise NotFound()
    return version, await get_storage().get(version.storage_key)

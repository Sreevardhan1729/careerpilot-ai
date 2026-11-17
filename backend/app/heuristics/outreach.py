"""Template-based outreach drafts from verified facts only (no LLM). Spec §4.4 rules apply."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.llm.other import DraftMessage, OutreachDrafts


@dataclass
class Fact:
    id: str
    text: str
    kind: str  # achievement | project | experience | skill


@dataclass
class OutreachContext:
    candidate_name: str | None
    recipient_name: str | None
    recipient_designation: str | None
    company: str
    job_title: str
    facts: list[Fact]
    skills: list[str]
    resume_label: str | None
    has_history: bool
    max_chars: int = 200
    extra: dict = field(default_factory=dict)


def _first(name: str | None) -> str | None:
    return name.split()[0] if name else None


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _most_relevant(facts: list[Fact], ctx: OutreachContext) -> Fact | None:
    """Highest overlap with the job's skills, then facts with a stated metric; stable on ties."""
    from app.domain.skills import get_taxonomy

    if not facts:
        return None
    wanted = set(ctx.extra.get("job_skills") or ctx.skills)
    tax = get_taxonomy()

    def score(f: Fact) -> tuple[int, int]:
        overlap = len({e.canonical for e in tax.skills_in(f.text)} & wanted)
        return overlap, int(any(ch.isdigit() for ch in f.text) and "%" in f.text)

    return max(facts, key=score)


def write_drafts(message_types: list[str], ctx: OutreachContext) -> OutreachDrafts:
    hi = f"Hi {_first(ctx.recipient_name)}," if ctx.recipient_name else "Hi there,"
    me = ctx.candidate_name or "a candidate"
    sign = ctx.candidate_name or ""
    achievement = _most_relevant([f for f in ctx.facts if f.kind == "achievement"], ctx)
    project = next((f for f in ctx.facts if f.kind == "project"), None)
    skills = ", ".join(ctx.skills[:3])
    fit_ids: list[str] = []
    fit = ""
    if achievement:
        fit = f"Recently I {_lower_first(achievement.text.rstrip('.'))}."
        fit_ids.append(achievement.id)
    elif project:
        fit = f"I built {project.text.rstrip('.')}."
        fit_ids.append(project.id)
    skill_line = f"My work centres on {skills}." if skills else ""
    drafts: list[DraftMessage] = []
    for mt in message_types:
        if mt == "linkedin_connection":
            body = f"{hi} I'm {me}, interested in the {ctx.job_title} role at {ctx.company}. {fit} Would be glad to connect."
            ids = list(fit_ids)
            if len(body) > ctx.max_chars:
                body = f"{hi} I'm {me}, interested in the {ctx.job_title} role at {ctx.company}. Would be glad to connect."
                ids = []
            if len(body) > ctx.max_chars:
                body = body[: ctx.max_chars - 1].rstrip() + "…"
            drafts.append(DraftMessage(message_type=mt, body=" ".join(body.split()), used_evidence_ids=ids))
        elif mt == "linkedin_follow_up":
            body = (f"{hi} following up on my connection request about the {ctx.job_title} role at {ctx.company}. "
                    f"{fit} {skill_line} Happy to share more details if useful.")
            drafts.append(DraftMessage(message_type=mt, body=" ".join(body.split()), used_evidence_ids=fit_ids))
        elif mt == "referral_request":
            body = (f"{hi} I'm {me} and I'm interested in the {ctx.job_title} role at {ctx.company}. {fit} {skill_line} "
                    "If my background looks relevant, would you be open to referring me or pointing me to the right "
                    "person? I can share my resume.")
            drafts.append(DraftMessage(message_type=mt, body=" ".join(body.split()), used_evidence_ids=fit_ids))
        elif mt == "hiring_manager_message":
            body = (f"{hi} I saw the {ctx.job_title} opening at {ctx.company}. {fit} {skill_line} "
                    "I'd value a short conversation about how I could contribute to the team.")
            drafts.append(DraftMessage(message_type=mt, body=" ".join(body.split()), used_evidence_ids=fit_ids))
        elif mt == "recruiter_email":
            ids = list(fit_ids)
            lines = [hi.replace(",", ",\n"), f"I'm {me}, applying for the {ctx.job_title} role at {ctx.company}."]
            if skill_line:
                lines.append(skill_line)
            if fit:
                lines.append(fit)
            if project and project.id not in ids:
                lines.append(f"I also built {project.text.rstrip('.')}.")
                ids.append(project.id)
            lines.append("I'd appreciate being considered, and I'm happy to share my resume or any details you need.")
            lines.append(f"Thanks,\n{sign}".rstrip())
            drafts.append(DraftMessage(message_type=mt, subject=f"Application: {ctx.job_title} — {sign}".rstrip(" —"),
                                       body="\n\n".join(line.strip() for line in lines), used_evidence_ids=ids))
        elif mt == "recruiter_follow_up":
            body = "\n\n".join([hi, f"I'm following up on my application for the {ctx.job_title} role at {ctx.company}. "
                                    "I remain very interested and would be glad to provide anything else you need.",
                                f"Thanks,\n{sign}".rstrip()])
            drafts.append(DraftMessage(message_type=mt, subject=f"Following up: {ctx.job_title} application", body=body))
        elif mt == "thank_you":
            body = "\n\n".join([hi, f"Thank you for your time regarding the {ctx.job_title} role at {ctx.company}. "
                                    "I enjoyed learning more about the team and remain very interested.",
                                f"Best regards,\n{sign}".rstrip()])
            drafts.append(DraftMessage(message_type=mt, subject=f"Thank you — {ctx.job_title}", body=body))
    return OutreachDrafts(drafts=drafts)

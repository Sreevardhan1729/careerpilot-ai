"""Rule-based resume improvement suggestions: ordering and highlighting only — never new content."""

from __future__ import annotations

from typing import Any

from app.schemas.llm.other import ResumeImprovement, SuggestedChange
from app.schemas.llm.resume import ResumeParsed

ATS_SECTION_ORDER = ["summary", "skills", "experience", "projects", "education", "certifications", "achievements"]


def suggest_improvements(match: dict[str, Any], parsed: ResumeParsed, job_title: str) -> ResumeImprovement:
    breakdown = match.get("skill_breakdown") or []
    present = [b["skill"] for b in breakdown if b["status"] in ("strong", "listed_only", "related")]
    weak = [b["skill"] for b in breakdown if b["status"] == "listed_only"]
    missing = [b["skill"] for b in breakdown if b["status"] in ("no_evidence", "confirmed_missing")]
    profile_only = [b["skill"] for b in breakdown if b["status"] == "profile_only"]
    resume_skills = list(dict.fromkeys(s.name for s in parsed.skills if s.section == "skills"))
    ordered = [s for s in present if s in resume_skills or s in {x.name for x in parsed.skills}]
    ordered += [s for s in resume_skills if s not in ordered]
    changes: list[SuggestedChange] = []
    for skill in weak:
        changes.append(SuggestedChange(
            section="skills", before=None,
            after=f"Move {skill} near the top of your skills list; if you used it in a project or role, say so in that bullet.",
            reason=f"{skill} is a requirement for {job_title} but only appears in the skills list."))
    for skill in profile_only:
        changes.append(SuggestedChange(
            section="skills", before=None,
            after=f"Your profile says you know {skill}, but this resume doesn't show it. Add it only where it is true.",
            reason="Present in your confirmed profile, missing from this resume."))
    current_order = parsed.section_order
    target = [s for s in ATS_SECTION_ORDER if s in current_order]
    if current_order and current_order != target:
        changes.append(SuggestedChange(section="layout", before=" > ".join(current_order), after=" > ".join(target),
                                       reason="Conventional ATS-friendly section order."))
    return ResumeImprovement(updated_summary=None, suggested_changes=changes, keywords_to_highlight=present[:30],
                             missing_evidence=missing[:30], skill_order=ordered[:40], section_order=target)

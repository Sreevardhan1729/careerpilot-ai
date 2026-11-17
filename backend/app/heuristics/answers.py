"""Rule-based application answers from verified profile facts only. Declarations always go to the user."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.llm.other import ApplicationAnswers, DraftAnswer

_DECLARATION = re.compile(
    r"certif|declar|consent|agree|terms|acknowledg|authori[sz]|visa|sponsor|citizen|clearance|gender|race|ethnic|"
    r"disabilit|veteran|pronoun|criminal|background check|salary|ctc|compensation|why|motivat|cover letter|tell us about",
    re.I,
)
_FIELDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(full\s*)?name\b", re.I), "full_name"),
    (re.compile(r"\be-?mail\b", re.I), "preferred_email"),
    (re.compile(r"\bphone|mobile|contact number\b", re.I), "phone"),
    (re.compile(r"\blinkedin\b", re.I), "linkedin_url"),
    (re.compile(r"\bgithub\b", re.I), "github_url"),
    (re.compile(r"\bportfolio|website\b", re.I), "portfolio_url"),
    (re.compile(r"\b(current\s+)?(location|city)\b", re.I), "current_location"),
    (re.compile(r"\bnotice period\b", re.I), "notice_period_days"),
    (re.compile(r"\byears? of experience|total experience|how many years\b", re.I), "total_experience_months"),
    (re.compile(r"\bgraduation year|year of graduation|graduat(ed|ion)\b", re.I), "graduation_year"),
]


def draft_answers(questions: list[str], profile: dict[str, Any], facts: dict[str, str]) -> ApplicationAnswers:
    out: list[DraftAnswer] = []
    for q in questions:
        if _DECLARATION.search(q):
            out.append(DraftAnswer(question=q, needs_user_input=True))
            continue
        answer = None
        sources: list[str] = []
        for pattern, field in _FIELDS:
            if pattern.search(q) and profile.get(field) not in (None, ""):
                value = profile[field]
                if field == "total_experience_months":
                    years = round(float(value) / 12, 1)
                    value = f"{years:g}"
                elif field == "notice_period_days":
                    value = f"{value} days"
                answer, sources = str(value), [f"profile:{field}"]
                break
        if answer is None:
            for fid, text in facts.items():
                words = [w for w in re.findall(r"[A-Za-z][A-Za-z+#.]{2,}", q) if w.lower() not in ("experience", "with", "have", "you", "your", "any", "what", "describe")]
                if words and all(w.lower() in text.lower() for w in words[:2]):
                    answer, sources = text, [fid]
                    break
        out.append(DraftAnswer(question=q, answer=answer, source_fact_ids=sources, needs_user_input=answer is None))
    return ApplicationAnswers(answers=out)

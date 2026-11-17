"""Deterministic claim checks for outreach and resume suggestions (FR-OUT-03; docs/AGENT_DESIGN.md §8)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.evidence import numbers_in
from app.domain.skills import get_taxonomy
from app.domain.text import normalize_for_match

_FIRST_PERSON = re.compile(r"\b(i|i've|i have|i'm|i am|my|me)\b", re.I)
_INTEREST = re.compile(r"\b(keen to learn|eager to learn|learning|want to learn|interested in learning|excited to explore)\b", re.I)
_RELATIONSHIP = re.compile(
    r"\b(we met|as (?:we )?discussed|great (?:chatting|talking|speaking)|nice (?:chatting|talking|meeting)|"
    r"referred (?:me|by)|you referred|my friend|our (?:conversation|chat|call)|following up on our|"
    r"following up on my earlier|as promised|thanks for (?:the|our) (?:chat|call|time))\b",
    re.I,
)
_ATTACHMENT = re.compile(r"\b(attached|attaching|attachment|please find (?:my|the) (?:resume|cv))\b", re.I)
_GENERIC = [
    "i hope this message finds you well",
    "i hope this email finds you well",
    "i am writing to express my interest",
    "passionate about leveraging",
    "synergy",
    "delve",
    "in today's fast-paced world",
    "i am reaching out to you today",
]


@dataclass
class ClaimContext:
    evidence_texts: list[str]
    candidate_skills: set[str]
    has_relationship_history: bool
    recipient_verified_email: str | None
    company_name: str | None = None
    job_title: str | None = None
    attachments_supported: bool = False
    max_chars: int | None = None
    max_words: int | None = None
    job_skills: set[str] = field(default_factory=set)
    job_texts: list[str] = field(default_factory=list)


@dataclass
class ClaimCheck:
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"passed": self.passed, "violations": self.violations}

    @property
    def blocking(self) -> list[dict[str, Any]]:
        return [v for v in self.violations if v["severity"] == "blocking"]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


_CLAUSE_SPLIT = re.compile(r"[,;:()\n]|\b(?:while|but|whereas|although|though)\b|(?<=[.!?])\s+", re.I)
_ROLE_REF = re.compile(r"\b((?:[A-Z][\w+/#.&-]*\s+){0,4}[A-Z][\w+/#.&-]*)\s+(?:role|position|opening|vacancy)\b")
_COMPANY_REF = re.compile(r"\b(?:role|position|opening|job|opportunity|team|vacancy)\s+(?:at|with)\s+"
                          r"([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,3})")


def _related(a: str, b: str) -> bool:
    na, nb = normalize_for_match(a), normalize_for_match(b)
    return bool(na) and bool(nb) and (na in nb or nb in na)


def check_claims(body: str, subject: str | None, recipient_email: str | None, ctx: ClaimContext) -> ClaimCheck:
    violations: list[dict[str, Any]] = []
    full = f"{subject or ''}\n{body}"
    allowed_numbers = {n for t in ctx.evidence_texts for n in numbers_in(t)}
    allowed_numbers |= set(numbers_in(f"{ctx.company_name or ''} {ctx.job_title or ''} {' '.join(ctx.job_texts)}"))

    def add(code: str, severity: str, detail: str) -> None:
        violations.append({"code": code, "severity": severity, "detail": detail})

    # Every number must come from a verified fact or the job itself (whatever unit or wording follows it).
    for m in re.finditer(r"\$?\d+(?:[.,]\d+)*(?:\s*(?:%|percent|x\b|k\b|m\b|million|billion|lakh|crore|lpa|users?|customers?|ms|hours?))?",
                         full, re.I):
        nums = numbers_in(m.group(0))
        if nums and any(n not in allowed_numbers for n in nums):
            add("unsupported_metric", "blocking", f"'{m.group(0).strip()}' does not appear in your verified facts.")

    # Skills: first-person clauses must be the candidate's; other clauses must be the candidate's or the job's.
    tax = get_taxonomy()
    scrubbed_full = _ROLE_REF.sub(" ", full)  # "the AI Engineer role" names a job, not a skill claim
    for name in (ctx.job_title, ctx.company_name):
        if name:
            scrubbed_full = re.sub(re.escape(name), " ", scrubbed_full, flags=re.I)
    for clause in _CLAUSE_SPLIT.split(scrubbed_full):
        if not clause or not clause.strip() or _INTEREST.search(clause):
            continue
        first_person = bool(_FIRST_PERSON.search(clause))
        for entry in tax.skills_in(clause):
            if entry.category in ("soft_skills", "domain_knowledge"):
                continue
            if entry.canonical in ctx.candidate_skills:
                continue
            if not first_person and entry.canonical in ctx.job_skills:
                continue
            add("unsupported_skill", "blocking", f"Mentions {entry.canonical}, which your resumes/profile don't show.")

    # The message must be about this job and company.
    if ctx.job_title:
        for m in _ROLE_REF.finditer(full):
            ref = re.sub(r"^(?:The|This|Your|An?|Our)\s+", "", m.group(1))
            if ref and not _related(ref, ctx.job_title) and not (ctx.company_name and _related(ref, ctx.company_name)):
                add("wrong_job_reference", "blocking", f"Mentions the '{ref}' role, but this job is '{ctx.job_title}'.")
    if ctx.company_name:
        for m in _COMPANY_REF.finditer(full):
            if not _related(m.group(1), ctx.company_name):
                add("wrong_job_reference", "blocking", f"Mentions '{m.group(1)}', but this job is at {ctx.company_name}.")

    if not ctx.has_relationship_history:
        for m in _RELATIONSHIP.finditer(full):
            add("unsupported_relationship", "blocking", f"'{m.group(0)}' implies a relationship with no recorded history.")

    if recipient_email and normalize_for_match(recipient_email) != normalize_for_match(ctx.recipient_verified_email or ""):
        add("unverified_recipient", "blocking", "Recipient email is not a verified public address for this person.")

    if not ctx.attachments_supported and _ATTACHMENT.search(full):
        add("attachment_claim", "blocking", "Mentions an attachment, but attachments are not added automatically.")

    if ctx.max_chars and len(body) > ctx.max_chars:
        add("too_long", "warning", f"{len(body)} characters; limit is {ctx.max_chars}.")
    if ctx.max_words and len(body.split()) > ctx.max_words:
        add("too_long", "warning", f"{len(body.split())} words; recommended maximum is {ctx.max_words}.")
    low = normalize_for_match(full)
    for phrase in _GENERIC:
        if phrase in low:
            add("generic_phrase", "warning", f"Generic phrase: '{phrase}'.")

    # de-duplicate identical violations
    unique = list({(v["code"], v["detail"]): v for v in violations}.values())
    return ClaimCheck(passed=not any(v["severity"] == "blocking" for v in unique), violations=unique)

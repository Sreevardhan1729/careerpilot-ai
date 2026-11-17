"""Deterministic verification of a JobExtraction against its source text (FR-JOB-06/07; AGENT_DESIGN §3.3).

Anything that cannot be supported by the source is nulled (salary → not_disclosed) and listed as missing.
Applies identically to LLM and heuristic extractions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from app.domain.evidence import (
    importance_cue,
    looks_like_injection,
    numbers_supported,
    source_span,
    verify_snippet,
)
from app.domain.normalize import (
    detect_employment_type,
    detect_seniority,
    detect_work_mode,
    find_locations,
    normalize_location,
    parse_date,
    parse_experience,
    parse_salary,
)
from app.domain.skills import get_taxonomy
from app.domain.text import normalize_for_match
from app.heuristics.job_extract import _expand as expand_sentences
from app.heuristics.job_extract import _heading_kind as heading_kind
from app.schemas.llm.job import EvidencedStr, ExtractedSkill, JobExtraction


@dataclass
class VerifiedJob:
    title: str | None = None
    company_name: str | None = None
    department: str | None = None
    seniority: str = "unknown"
    experience_min: float | None = None
    experience_max: float | None = None
    experience_explicit: bool = False
    experience_evidence: str | None = None
    locations: list[dict[str, Any]] = field(default_factory=list)
    work_mode: str = "unknown"
    employment_type: str = "unknown"
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    salary_source_type: str = "not_disclosed"
    salary_is_base: bool | None = None
    salary_confidence: float | None = None
    education: list[str] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    technical_requirements: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    business_domain: str | None = None
    application_deadline: date | None = None
    posted_at: datetime | None = None
    application_url: str | None = None
    posted_by: dict[str, Any] | None = None
    hiring_expectations: str | None = None
    missing_information: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    field_confidence: dict[str, float] = field(default_factory=dict)


def _ev(out: VerifiedJob, fld: str, value: Any, text: str | None, explicit: bool, verified: bool, conf: float | None) -> None:
    out.evidence.append({"field": fld, "value": value, "evidence_text": (text or "")[:500] or None, "explicit": explicit,
                         "verified": verified, "confidence": conf})


def _check_str(e: EvidencedStr, source: str) -> bool:
    """The value itself must appear in the source text its evidence matched (or anywhere, if no evidence)."""
    if not e.value:
        return False
    value = normalize_for_match(e.value)
    if e.evidence:
        span = source_span(e.evidence, source)
        return bool(span) and value in span
    return value in normalize_for_match(source)


def _display(evidence: str | None, span: str | None, source: str) -> str | None:
    """Prefer the model's snippet for display only when it is verbatim in the source."""
    if evidence and normalize_for_match(evidence).strip(" .,;:") in normalize_for_match(source):
        return evidence
    return span


def _line_index(lines: list[str], snippet: str | None, needle: str) -> int | None:
    n_snip = normalize_for_match(snippet or "")
    n_need = normalize_for_match(needle)
    for i, line in enumerate(lines):
        nl = normalize_for_match(line)
        if n_snip and len(n_snip) >= 8 and (n_snip in nl or nl in n_snip and len(nl) > 8):
            return i
    for i, line in enumerate(lines):
        if n_need and n_need in normalize_for_match(line):
            return i
    return None


def _section_for(lines: list[str], idx: int) -> str | None:
    kind, _ = heading_kind(lines[idx])
    if kind:
        return kind
    for j in range(idx - 1, -1, -1):
        kind, _ = heading_kind(lines[j])
        if kind:
            return kind
    return None


def _verify_skills(x: JobExtraction, source: str, lines: list[str], out: VerifiedJob) -> None:
    tax = get_taxonomy()
    rank = {"mandatory": 0, "preferred": 1, "mentioned": 2}
    chosen: dict[str, dict[str, Any]] = {}
    claimed: list[ExtractedSkill] = [*x.mandatory_skills, *x.preferred_skills, *x.mentioned_skills]
    for s in claimed:
        entry = tax.canonicalize(s.name)
        name = entry.canonical if entry else tax.normalize_name(s.name)
        needle_forms = {normalize_for_match(s.name), normalize_for_match(name)}
        span = source_span(s.evidence, source) if s.evidence else None
        evidence = _display(s.evidence, span, source) if span else None
        if span and not any(f in span for f in needle_forms) and not (
            entry and any(m.entry.canonical == name for m in tax.find_in_text(span))
        ):
            evidence = None
        idx = _line_index(lines, evidence, s.name)
        if evidence is None:
            # fall back to a line that names the skill; else the claim is unsupported
            hits = [i for i, ln in enumerate(lines) if entry and any(m.entry.canonical == name for m in tax.find_in_text(ln))]
            if not hits:
                hits = [i for i, ln in enumerate(lines) if normalize_for_match(s.name) in normalize_for_match(ln)]
            if not hits:
                _ev(out, f"skill:{name}", s.importance, s.evidence, True, False, s.confidence)
                continue
            idx = hits[0]
            evidence = lines[idx].strip()[:300]
        section = _section_for(lines, idx) if idx is not None else None
        cue = importance_cue(lines[idx] if idx is not None else evidence)
        if section == "preferred" or cue == "preferred":
            importance = "preferred"
        elif section == "requirements" or cue == "mandatory":
            importance = "mandatory"
        else:
            importance = "mentioned"
        item = {"name": name, "raw_name": s.name, "category": entry.category if entry else s.category,
                "importance": importance, "evidence_text": evidence, "evidence_verified": True,
                "confidence": s.confidence, "skill_slug": entry.slug if entry else None}
        prev = chosen.get(name)
        if prev is None or rank[importance] < rank[prev["importance"]]:
            chosen[name] = item
    out.skills = list(chosen.values())


def verify_extraction(x: JobExtraction, source: str, *, now: datetime | None = None, source_url: str | None = None,
                      source_salary: dict[str, Any] | None = None, source_posted_at: datetime | None = None,
                      company_hint: str | None = None) -> VerifiedJob:
    now = now or datetime.now(tz=UTC)
    all_lines = [ln for ln in expand_sentences(source.split("\n")) if ln.strip()]
    lines = [ln for ln in all_lines if not looks_like_injection(ln)]
    out = VerifiedJob()
    for ln in all_lines:
        if looks_like_injection(ln):
            _ev(out, "prompt_injection", None, ln, True, False, None)
    source = "\n".join(lines)  # every fact must be supported by text outside injected instructions

    for fld, e in (("job_title", x.job_title), ("company", x.company), ("department", x.department)):
        ok = _check_str(e, source)
        _ev(out, fld, e.value, e.evidence, e.explicit, ok, e.confidence)
        if ok:
            setattr(out, {"job_title": "title", "company": "company_name", "department": "department"}[fld], e.value)
            out.field_confidence[fld] = e.confidence
    if not out.company_name and company_hint:
        out.company_name = company_hint

    out.seniority = detect_seniority(out.title) if detect_seniority(out.title) != "unknown" else (
        x.seniority if out.title else "unknown")

    exp = x.experience
    nums = [n for n in (exp.minimum_years, exp.maximum_years) if n is not None]
    span = source_span(exp.evidence, source) if exp.evidence else None
    parsed_exp = parse_experience(span) if span else None
    exp_ok = bool(parsed_exp) or (bool(span) and bool(nums) and numbers_supported([float(n) for n in nums], span or ""))
    _ev(out, "experience", {"min": exp.minimum_years, "max": exp.maximum_years}, exp.evidence, exp.explicit, exp_ok, exp.confidence)
    if parsed_exp:  # re-derived from the source span, not the model's numbers
        out.experience_min, out.experience_max = parsed_exp.minimum_years, parsed_exp.maximum_years
        out.experience_explicit, out.experience_evidence = True, _display(exp.evidence, span, source)
    elif exp_ok:
        out.experience_min, out.experience_max = exp.minimum_years, exp.maximum_years
        out.experience_explicit, out.experience_evidence = True, _display(exp.evidence, span, source)

    sal = x.salary
    if source_salary and source_salary.get("minimum") is not None:
        out.salary_min, out.salary_max = source_salary.get("minimum"), source_salary.get("maximum")
        out.salary_currency, out.salary_period = source_salary.get("currency"), source_salary.get("period") or "unknown"
        out.salary_source_type, out.salary_confidence = "source_website", 0.9
        _ev(out, "salary", source_salary, None, True, True, 0.9)
    elif sal.source_type == "jd" and sal.evidence and (sal_span := source_span(sal.evidence, source)):
        parsed = parse_salary(sal_span)  # amounts come from the matched source text
        if parsed:
            out.salary_min, out.salary_max, out.salary_currency = parsed.minimum, parsed.maximum, parsed.currency or sal.currency
            out.salary_period = parsed.period if parsed.period != "unknown" else (sal.period or "unknown")
            out.salary_source_type, out.salary_is_base, out.salary_confidence = "jd", sal.is_base, sal.confidence
        _ev(out, "salary", sal.model_dump(), sal.evidence, True, parsed is not None, sal.confidence)
    elif sal.source_type != "not_disclosed" or sal.minimum is not None:
        _ev(out, "salary", sal.model_dump(), sal.evidence, False, False, sal.confidence)

    text_cities = {loc["city"] for loc in find_locations(source)}
    for raw in x.location:
        norm = normalize_location(raw)
        ok = (norm["city"] in text_cities) or (norm["remote"] and "remote" in source.lower()) or verify_snippet(raw, source)
        _ev(out, "location", raw, x.location_evidence, True, bool(ok), None)
        if ok:
            out.locations.append(norm)

    # A claim whose own evidence verifies (and says the same thing) stands; otherwise use deterministic detection.
    detected_mode, mode_ev = detect_work_mode(source)
    claimed_ok = (x.work_mode != "unknown" and x.work_mode_evidence and verify_snippet(x.work_mode_evidence, source)
                  and detect_work_mode(x.work_mode_evidence)[0] == x.work_mode)
    out.work_mode = x.work_mode if claimed_ok else detected_mode
    _ev(out, "work_mode", out.work_mode, x.work_mode_evidence if claimed_ok else mode_ev, True, out.work_mode != "unknown", None)
    detected_type, _type_ev = detect_employment_type(source)
    type_ok = (x.employment_type != "unknown" and x.employment_type_evidence and verify_snippet(x.employment_type_evidence, source)
               and detect_employment_type(x.employment_type_evidence)[0] == x.employment_type)
    out.employment_type = x.employment_type if type_ok else detected_type

    out.education = [e.value for e in x.education if e.value and (not e.evidence or verify_snippet(e.evidence, source))]
    _verify_skills(x, source, lines, out)
    out.responsibilities = [r for r in x.responsibilities if r][:30]
    out.technical_requirements = [r for r in x.technical_requirements if r][:30]
    out.soft_skills = [s for s in x.soft_skills if normalize_for_match(s) in normalize_for_match(source)]
    out.business_domain = get_taxonomy().canonical_domain(x.business_domain.value)

    dl = x.application_deadline
    if _check_str(dl, source):
        parsed_dl = parse_date(dl.value, prefer="future", base=now)
        out.application_deadline = parsed_dl.date() if parsed_dl else None
    pd = x.posted_date
    if source_posted_at:
        out.posted_at = source_posted_at
    elif _check_str(pd, source):
        parsed_pd = parse_date(pd.value, prefer="past", base=now)
        out.posted_at = parsed_pd.astimezone(UTC) if parsed_pd else None

    if x.application_url and (x.application_url in source or x.application_url == source_url):
        out.application_url = x.application_url
    elif source_url and not x.application_url:
        out.application_url = source_url
    if x.posted_by and x.posted_by.name and normalize_for_match(x.posted_by.name) in normalize_for_match(source):
        out.posted_by = x.posted_by.model_dump()
    out.hiring_expectations = x.key_hiring_expectations

    missing = [label for label, present in (
        ("Company", out.company_name), ("Job title", out.title),
        ("Experience", out.experience_min is not None or out.experience_max is not None),
        ("Location", out.locations or out.work_mode == "remote"), ("Work mode", out.work_mode != "unknown"),
        ("Employment type", out.employment_type != "unknown"), ("Salary", out.salary_source_type != "not_disclosed"),
        ("Mandatory skills", any(s["importance"] == "mandatory" for s in out.skills)),
    ) if not present]
    out.missing_information = missing
    return out

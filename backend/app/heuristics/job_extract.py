"""Rule-based job extraction used when no LLM is configured (LLM_PROVIDER=none).

Produces the same JobExtraction schema as the LLM path. Everything returned is copied from the text (evidence is
the source line), so the deterministic evidence verifier accepts it; nothing is inferred beyond the rules below.
"""

from __future__ import annotations

import re
from collections import Counter

from app.domain.evidence import importance_cue
from app.domain.normalize import (
    detect_employment_type,
    detect_seniority,
    detect_work_mode,
    find_locations,
    normalize_location,
    parse_experience,
    parse_salary,
)
from app.domain.skills import get_taxonomy
from app.domain.text import clean_text
from app.schemas.llm.job import (
    EvidencedStr,
    ExperienceRange,
    ExtractedSkill,
    JobExtraction,
    PosterInfo,
    SalaryInfo,
)

METHOD = "heuristic"
VERSION = "heuristic@v1"

_HEADINGS: list[tuple[str, re.Pattern[str]]] = [
    ("preferred", re.compile(r"^(nice[\s-]to[\s-]have|good[\s-]to[\s-]have|preferred( qualifications| skills)?|bonus( points)?|"
                             r"pluses|desired( skills)?|it'?s a plus)\b", re.I)),
    ("requirements", re.compile(r"^(requirements?|qualifications|minimum qualifications|basic qualifications|must[\s-]haves?|"
                                r"what you('| wi)ll need|what we('re| are) looking for|who you are|skills( required)?|"
                                r"you have|you bring|required skills|eligibility)\b", re.I)),
    ("responsibilities", re.compile(r"^(responsibilities|key responsibilities|what you('| wi)ll do|the role|role overview|"
                                    r"your role|day[\s-]to[\s-]day|duties|job description)\b", re.I)),
    ("about", re.compile(r"^(about( us| the company| the team)?|who we are|company overview)\b", re.I)),
    ("benefits", re.compile(r"^(benefits|perks|what we offer|why join( us)?|compensation( and benefits)?)\b", re.I)),
]
_ROLE_WORDS = re.compile(
    r"\b(engineer|developer|scientist|analyst|intern|architect|lead|manager|designer|consultant|sde|programmer|"
    r"researcher|specialist|administrator|devops|sre)\b", re.I)
_LABEL = re.compile(r"^\s*(role|position|job title|title|designation)\s*[:\-–]\s*(.+)$", re.I)
_COMPANY_LABEL = re.compile(r"^\s*(company|organisation|organization|employer)\s*[:\-–]\s*(.+)$", re.I)
_LOCATION_LABEL = re.compile(r"^\s*(location|locations|job location|based in)\s*[:\-–]\s*(.+)$", re.I)
_HIRING = re.compile(r"\b(?:hiring|looking for|seeking|recruiting)\s+(?:an?\s+|our\s+(?:next|first)\s+)?"
                     r"((?:[A-Z][\w/+.-]*\s+){0,4}(?:[A-Z][\w/+.-]*))(?=[\s!.,(]|$)")
_COMPANY_HIRING = re.compile(r"^(.{2,60}?)\s+(?:is|are)\s+hiring\b", re.I)
_ABOUT_COMPANY = re.compile(r"^about\s+([A-Z][\w&.\- ]{1,60})$")
_EDU = re.compile(r"\b(b\.?\s?tech|b\.?e\.?|b\.?sc|bachelor'?s?|m\.?\s?tech|m\.?s\.?|master'?s?|ph\.?d|mba|degree in|"
                  r"graduate in|diploma)\b", re.I)
_DEADLINE = re.compile(r"(?:apply by|deadline|last date(?: to apply)?|applications? close[sd]?(?: on)?)\s*[:\-]?\s*"
                       r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|"
                       r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})", re.I)
_POSTED = re.compile(r"(?:posted(?: on)?|date posted)\s*[:\-]?\s*(\d+\s+(?:day|week|hour)s?\s+ago|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|"
                     r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2}|today|yesterday)", re.I)
_URL = re.compile(r"https?://[^\s<>()\"']+")
_APPLY_URL_HINT = re.compile(r"apply|career|jobs?|greenhouse|lever|ashby|workday|forms|recruit", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦●○]|\d+[.)])\s+")
_NAME_LINE = re.compile(r"^[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3}$")
_POSTER_HINT = re.compile(r"recruit|talent|hiring|hr\b|human resources|people|founder|ceo|cto|engineer|manager|lead", re.I)


def _heading_kind(line: str) -> tuple[str | None, str]:
    """Return (section kind, inline remainder) if the line is a heading."""
    stripped = _BULLET.sub("", line).strip()
    for kind, pattern in _HEADINGS:
        m = pattern.match(stripped)
        if not m:
            continue
        rest = stripped[m.end():]
        if rest.startswith((":", " -", " –")) or rest.strip(" :") == "" or len(stripped) <= 40 and rest.strip().endswith(":"):
            return kind, rest.lstrip(" :-–").strip()
    return None, line


def _strip_bullet(line: str) -> str:
    return _BULLET.sub("", line).strip()


def _clean_title(raw: str) -> str:
    t = re.split(r"\s+(?:at|@)\s+|\s+[|–-]\s+", raw.strip(), maxsplit=1)[0]
    return re.sub(r"[!.,:;]+$", "", t).strip()


def _evidence(line: str, start: int | None = None, end: int | None = None) -> str:
    """The line itself if short; otherwise a <=300-char window around the match (evidence must contain the fact)."""
    line = line.strip()
    if len(line) <= 300 or start is None:
        return line[:300]
    mid = (start + (end or start)) // 2
    lo = max(0, min(mid - 150, len(line) - 300))
    return line[lo: lo + 300].strip()


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _expand(lines: list[str]) -> list[str]:
    """Single-paragraph posts: split long lines into sentences so inline 'Requirements: …' become sections."""
    out: list[str] = []
    for ln in lines:
        out += [p for p in _SENTENCE.split(ln) if p.strip()] if len(ln) > 160 else [ln]
    return out


def extract_job(text: str, company_hint: str | None = None, source_url: str | None = None) -> JobExtraction:
    text = clean_text(text)
    lines = _expand(text.split("\n"))
    tax = get_taxonomy()

    sections: list[tuple[str | None, str]] = []  # (section kind, line)
    current: str | None = None
    for line in lines:
        if not line.strip():
            continue
        kind, rest = _heading_kind(line)
        if kind:
            current = kind
            if rest:
                sections.append((current, rest))
            continue
        sections.append((current, line))

    # ---- title / company / poster
    title: EvidencedStr = EvidencedStr()
    company: EvidencedStr = EvidencedStr()
    posted_by: PosterInfo | None = None
    nonempty = [ln for ln in lines if ln.strip()]
    if len(nonempty) >= 2 and _NAME_LINE.match(nonempty[0]) and _POSTER_HINT.search(nonempty[1]) \
            and not _ROLE_WORDS.search(nonempty[0]):
        posted_by = PosterInfo(name=nonempty[0], headline=nonempty[1][:200], evidence=nonempty[0])
        m = re.search(r"\bat\s+([A-Z][\w&.\- ]{1,60})$", nonempty[1])
        if m:
            company = EvidencedStr(value=m.group(1).strip(), evidence=_evidence(nonempty[1]), confidence=0.6)
    for line in nonempty[:40]:
        m = _LABEL.match(line)
        if m and not title.value:
            title = EvidencedStr(value=_clean_title(m.group(2)), evidence=_evidence(line), confidence=0.9)
        m = _COMPANY_LABEL.match(line)
        if m and not company.value:
            company = EvidencedStr(value=m.group(2).strip(), evidence=_evidence(line), confidence=0.9)
        m = _COMPANY_HIRING.match(line)
        if m and not company.value:
            company = EvidencedStr(value=m.group(1).strip(), evidence=_evidence(line), confidence=0.8)
    if not title.value:
        for line in nonempty[:15]:
            m = _HIRING.search(line)
            if m and _ROLE_WORDS.search(m.group(1)):
                title = EvidencedStr(value=_clean_title(m.group(1)), evidence=_evidence(line), confidence=0.7)
                break
    if not title.value and nonempty:
        first = nonempty[0]
        if len(first) <= 80 and _ROLE_WORDS.search(first) and not _heading_kind(first)[0]:
            title = EvidencedStr(value=_clean_title(first), evidence=_evidence(first), confidence=0.6)
            m = re.search(r"\s(?:at|@)\s+([A-Z][\w&.\- ]{1,60})$", first)
            if m and not company.value:
                company = EvidencedStr(value=m.group(1).strip(), evidence=_evidence(first), confidence=0.6)
    if not company.value:
        for line in nonempty[:60]:
            m = _ABOUT_COMPANY.match(line.strip())
            if m and m.group(1).lower() not in ("us", "the company", "the team", "the role"):
                company = EvidencedStr(value=m.group(1).strip(), evidence=_evidence(line), confidence=0.6)
                break
    if not company.value and company_hint:
        company = EvidencedStr(value=company_hint, evidence=None, explicit=False, confidence=0.4)

    # ---- skills by section
    rank = {"mandatory": 0, "preferred": 1, "mentioned": 2}
    found: dict[str, ExtractedSkill] = {}
    for kind, line in sections:
        cue = importance_cue(line)
        if kind == "preferred" or cue == "preferred":
            importance = "preferred"
        elif kind == "requirements" or cue == "mandatory":
            importance = "mandatory"
        else:
            importance = "mentioned"
        seen_here: set[str] = set()
        for m in tax.find_in_text(line):
            entry = m.entry
            if entry.canonical in seen_here:
                continue
            seen_here.add(entry.canonical)
            cand = ExtractedSkill(name=entry.canonical, category=entry.category, importance=importance,
                                  evidence=_evidence(line, m.start, m.end), confidence=0.7 if importance != "mentioned" else 0.5)
            prev = found.get(entry.canonical)
            if prev is None or rank[importance] < rank[prev.importance]:
                found[entry.canonical] = cand
    skills = list(found.values())
    soft = [s.name for s in skills if s.category == "soft_skills"]
    tech = [s for s in skills if s.category != "soft_skills"]

    # ---- experience / salary / location / modes
    exp = parse_experience(text)
    experience = ExperienceRange(minimum_years=exp.minimum_years, maximum_years=exp.maximum_years, evidence=exp.evidence,
                                 explicit=True, confidence=0.8) if exp else ExperienceRange()
    salary = SalaryInfo()
    for _kind, line in sections:
        sal = parse_salary(line)
        if sal:
            salary = SalaryInfo(minimum=sal.minimum, maximum=sal.maximum, currency=sal.currency, period=sal.period,
                                source_type="jd", evidence=_evidence(line), confidence=0.8)
            break
    locations: list[str] = []
    location_evidence = None
    for line in nonempty[:60]:
        m = _LOCATION_LABEL.match(line)
        if m:
            value = re.sub(r"\((?:hybrid|remote|onsite|on-site)\)", "", m.group(2), flags=re.I).strip(" ,")
            parts = [p.strip() for p in re.split(r";|/|\bor\b", value) if p.strip()]
            for p in parts:
                norm = normalize_location(p)
                locations.append(p if not norm["city"] else ", ".join(x for x in (norm["city"], norm["country"]) if x))
            location_evidence = _evidence(line)
            break
    if not locations:
        for loc in find_locations(text)[:3]:
            locations.append(f"{loc['city']}, {loc['country']}")
        if locations:
            location_evidence = next((_evidence(ln) for ln in nonempty if locations[0].split(",")[0].lower() in ln.lower()), None)
    work_mode, wm_ev = detect_work_mode(text)
    if work_mode == "remote" and not locations:
        m = re.search(r"remote\s*\(([^)]+)\)", text, re.I)
        if m:
            locations.append(f"Remote ({m.group(1).strip()})")
            location_evidence = m.group(0)
    employment_type, et_ev = detect_employment_type(text)

    # ---- lists
    responsibilities = [_strip_bullet(ln) for k, ln in sections if k == "responsibilities" and _strip_bullet(ln)][:20]
    requirements = [_strip_bullet(ln) for k, ln in sections if k == "requirements" and _strip_bullet(ln)][:20]
    education = [EvidencedStr(value=_strip_bullet(ln)[:300], evidence=_evidence(ln), confidence=0.7)
                 for _, ln in sections if _EDU.search(ln)][:5]

    # ---- domain
    counts: Counter[str] = Counter()
    for _, line in sections:
        for d in tax.domains_in(line):
            counts[d] += 1
    domain = EvidencedStr()
    if counts:
        best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        ev = next((ln for _, ln in sections if best in tax.domains_in(ln)), None)
        domain = EvidencedStr(value=best, evidence=_evidence(ev) if ev else None, explicit=False, confidence=0.5)

    # ---- dates / urls
    deadline = EvidencedStr()
    m = _DEADLINE.search(text)
    if m:
        deadline = EvidencedStr(value=m.group(1), evidence=m.group(0), confidence=0.8)
    posted = EvidencedStr()
    m = _POSTED.search(text)
    if m:
        posted = EvidencedStr(value=m.group(1), evidence=m.group(0), confidence=0.7)
    urls = [u.rstrip(".,;)") for u in _URL.findall(text)]
    application_url = next((u for u in urls if _APPLY_URL_HINT.search(u)), None) or source_url

    seniority = detect_seniority(title.value)
    missing = [label for label, present in (
        ("Company", company.value), ("Job title", title.value), ("Experience", exp), ("Location", locations or work_mode == "remote"),
        ("Work mode", work_mode != "unknown"), ("Employment type", employment_type != "unknown"),
        ("Salary", salary.source_type != "not_disclosed"), ("Mandatory skills", any(s.importance == "mandatory" for s in tech)),
    ) if not present]

    mand = [s.name for s in tech if s.importance == "mandatory"]
    expectations = []
    if mand:
        expectations.append("Required: " + ", ".join(mand[:8]))
    if exp:
        expectations.append(f"Experience: {exp.evidence}")
    if responsibilities:
        expectations.append("Main duty: " + responsibilities[0])

    return JobExtraction(
        company=company,
        job_title=title,
        department=EvidencedStr(),
        seniority=seniority,  # type: ignore[arg-type]
        experience=experience,
        location=locations,
        location_evidence=location_evidence,
        work_mode=work_mode,  # type: ignore[arg-type]
        work_mode_evidence=wm_ev,
        employment_type=employment_type,  # type: ignore[arg-type]
        employment_type_evidence=et_ev,
        salary=salary,
        education=education,
        mandatory_skills=[s for s in tech if s.importance == "mandatory"],
        preferred_skills=[s for s in tech if s.importance == "preferred"],
        mentioned_skills=[s for s in tech if s.importance == "mentioned"],
        responsibilities=responsibilities,
        technical_requirements=requirements,
        soft_skills=soft,
        business_domain=domain,
        application_deadline=deadline,
        application_url=application_url,
        posted_date=posted,
        posted_by=posted_by,
        key_hiring_expectations="; ".join(expectations) or None,
        missing_information=missing,
    )

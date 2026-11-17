"""Rule-based resume parser used when no LLM is configured. Copies facts only; never adds content."""

from __future__ import annotations

import re
from datetime import date

from app.domain.normalize import find_locations
from app.domain.skills import get_taxonomy
from app.domain.text import clean_text
from app.domain.urls import normalize_linkedin_profile
from app.schemas.llm.resume import (
    ResumeAchievement,
    ResumeContact,
    ResumeEducation,
    ResumeExperience,
    ResumeParsed,
    ResumeProject,
    ResumeSkill,
)

METHOD = "heuristic"
VERSION = "heuristic@v1"

_SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("summary", re.compile(r"^(professional\s+)?(summary|profile|objective|about me|career objective)$", re.I)),
    ("skills", re.compile(r"^(technical\s+|core\s+|key\s+)?(skills|competencies|tech(nical)? stack|technologies|tools)"
                          r"( & tools| and tools)?$", re.I)),
    ("experience", re.compile(r"^(work\s+|professional\s+|relevant\s+)?(experience|employment( history)?|internships?|"
                              r"work history)$", re.I)),
    ("projects", re.compile(r"^((personal|academic|key|selected|side)\s+)?projects$", re.I)),
    ("education", re.compile(r"^(education|academics|academic background|qualifications)$", re.I)),
    ("certifications", re.compile(r"^(certifications?|certificates|licenses( & certifications)?|courses)$", re.I)),
    ("achievements", re.compile(r"^(achievements|awards|accomplishments|honou?rs( & awards)?|awards & achievements)$", re.I)),
    ("other", re.compile(r"^(publications|interests|hobbies|languages known|volunteering|extracurriculars?|references)$", re.I)),
]
_BULLET = re.compile(r"^\s*(?:[-*•·▪◦●○➢►]|\d+[.)])\s+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\+?\d[\d\s()-]{8,}\d")
_LINKEDIN = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?", re.I)
_GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9\-_]+/?", re.I)
_URL = re.compile(r"(?:https?://)[^\s|,;]+")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_RANGE = re.compile(
    rf"(?:{_MON}\s*(\d{{4}})|(\d{{1,2}})/(\d{{4}})|(\d{{4}}))\s*(?:-|to|–|—)\s*"
    rf"(present|current|now|till date|ongoing|{_MON}\s*(\d{{4}})|(\d{{1,2}})/(\d{{4}})|(\d{{4}}))",
    re.I,
)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_DEGREE = re.compile(r"\b(b\.?\s?tech|b\.?e\.?|b\.?sc|bca|mca|bachelor|m\.?\s?tech|m\.?sc?|master|ph\.?d|mba|diploma|"
                     r"higher secondary|class xii|12th|10th)\b", re.I)
_METRIC = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|x\b|\+|k\b|ms\b|users?\b|customers?\b)", re.I)


def _section_of(line: str) -> str | None:
    s = line.strip().rstrip(":").strip()
    if len(s) > 45:
        return None
    for name, pattern in _SECTION_PATTERNS:
        if pattern.match(s):
            return name
    return None


def _is_bullet(line: str) -> bool:
    return bool(_BULLET.match(line))


def _strip_bullet(line: str) -> str:
    return _BULLET.sub("", line).strip()


def _month_index(month_word: str | None, month_num: str | None, year: str | None, end: bool) -> tuple[int, int] | None:
    if not year:
        return None
    if month_word:
        return int(year), _MONTHS[month_word.lower()[:3]]
    if month_num:
        return int(year), max(1, min(12, int(month_num)))
    return int(year), 12 if end else 1


def _months_between(m: re.Match[str], today: date) -> tuple[str, str, float | None]:
    g = m.groups()
    start = _month_index(g[0], g[2], g[1] or g[3] or g[4], end=False)
    end_word = (g[5] or "").lower()
    if end_word in ("present", "current", "now", "till date", "ongoing"):
        end = (today.year, today.month)
    else:
        end = _month_index(g[6], g[8], g[7] or g[9] or g[10], end=True)
    start_raw, _, end_raw = m.group(0).partition("-") if "-" in m.group(0) else (m.group(0), "", "")
    if not start or not end:
        return start_raw.strip(), end_raw.strip(), None
    months = (end[0] - start[0]) * 12 + (end[1] - start[1]) + 1
    return start_raw.strip(), end_raw.strip(), float(months) if months > 0 else None


def _split_header(header: str) -> list[str]:
    header = re.sub(r"\(\s*\)|\[\s*\]", "", header)
    return [p.strip() for p in re.split(r"\s+\|\s+|\s+[–—-]\s+|\s{2,}|,\s+(?=[A-Z])|\s+@\s+|\s+at\s+", header) if p.strip()]


def _entries(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Group a section into (header line, bullet/continuation lines)."""
    out: list[tuple[str, list[str]]] = []
    for line in lines:
        if _is_bullet(line) and out:
            out[-1][1].append(_strip_bullet(line))
        elif not _is_bullet(line) and (not out or out[-1][1] or _DATE_RANGE.search(line) is None and len(line) < 120):
            if out and not out[-1][1] and _DATE_RANGE.search(line):
                out[-1] = (out[-1][0] + " | " + line, [])
            else:
                out.append((line, []))
        elif out:
            out[-1][1].append(line.strip())
        else:
            out.append((line, []))
    return out


def parse_resume(text: str, today: date | None = None) -> ResumeParsed:
    today = today or date.today()
    tax = get_taxonomy()
    lines = [ln for ln in clean_text(text).split("\n") if ln.strip()]

    sections: dict[str, list[str]] = {}
    order: list[str] = []
    header: list[str] = []
    current: str | None = None
    for line in lines:
        name = _section_of(line)
        if name:
            current = name
            if name not in order:
                order.append(name)
            sections.setdefault(name, [])
            continue
        if current is None:
            header.append(line)
        else:
            sections[current].append(line)

    # ---- contact
    head_text = "\n".join(header)
    contact = ResumeContact()
    if header and re.match(r"^[A-Za-z][A-Za-z.'-]+(?:\s[A-Za-z][A-Za-z.'-]+){0,3}$", header[0].strip()):
        contact.name = header[0].strip()
    if m := _EMAIL.search(head_text):
        contact.email = m.group(0)
    if m := _PHONE.search(_EMAIL.sub(" ", head_text)):
        contact.phone = re.sub(r"\s+", " ", m.group(0)).strip()
    if m := _LINKEDIN.search(head_text):
        url = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
        contact.linkedin_url = normalize_linkedin_profile(url)
    if m := _GITHUB.search(head_text):
        contact.github_url = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)
    locs = find_locations(head_text)
    if locs:
        contact.location = locs[0]["city"]

    skills: dict[tuple[str, str], ResumeSkill] = {}

    def add_skills(text_block: str, section: str) -> list[str]:
        names: list[str] = []
        for entry in tax.skills_in(text_block):
            names.append(entry.canonical)
            skills.setdefault((entry.canonical, section), ResumeSkill(name=entry.canonical, section=section,
                                                                      evidence=text_block[:300]))
        return names

    # ---- skills section: split list items and canonicalise each token too
    for line in sections.get("skills", []):
        content = line.split(":", 1)[1] if ":" in line and len(line.split(":", 1)[0]) < 40 else line
        add_skills(line, "skills")
        for token in re.split(r"[,|;/•·]", content):
            entry = tax.canonicalize(token)
            if entry:
                skills.setdefault((entry.canonical, "skills"), ResumeSkill(name=entry.canonical, section="skills",
                                                                           evidence=line[:300]))

    summary = " ".join(sections.get("summary", [])) or None
    if summary:
        add_skills(summary, "summary")

    # ---- experience
    experience: list[ResumeExperience] = []
    for head, body in _entries(sections.get("experience", [])):
        m = _DATE_RANGE.search(head)
        start = end = None
        months = None
        if m:
            start, end, months = _months_between(m, today)
            head_wo_date = (head[: m.start()] + head[m.end():]).strip(" |,–-")
        else:
            head_wo_date = head
        parts = _split_header(head_wo_date)
        title = parts[0] if parts else None
        company = parts[1] if len(parts) > 1 else None
        block = "\n".join([head, *body])
        experience.append(ResumeExperience(
            title=title, company=company, start=start, end=end, months=months,
            is_internship=bool(re.search(r"\bintern(ship)?\b", head, re.I)),
            bullets=body[:30], technologies=sorted(set(add_skills(block, "experience"))),
            domains=sorted(tax.domains_in(block)),
        ))

    # ---- projects
    projects: list[ResumeProject] = []
    for head, body in _entries(sections.get("projects", [])):
        parts = [p.strip() for p in re.split(r"\s+\|\s+|\s+[–—-]\s+|:\s+", head, maxsplit=1)]
        title = parts[0] if parts else head
        block = "\n".join([head, *body])
        projects.append(ResumeProject(
            title=title[:200], description=parts[1][:1500] if len(parts) > 1 else None, bullets=body[:20],
            technologies=sorted(set(add_skills(block, "project"))), domains=sorted(tax.domains_in(block)),
            links=_URL.findall(block)[:5],
        ))

    # ---- education / certifications / achievements
    education: list[ResumeEducation] = []
    for line in sections.get("education", []):
        if _is_bullet(line) and education:
            education[-1].details = ((education[-1].details or "") + " " + _strip_bullet(line)).strip()[:300]
            continue
        parts = [p.strip() for p in re.split(r",\s+|\s+\|\s+|\s+[–—-]\s+", _strip_bullet(line)) if p.strip()]
        degree = next((p for p in parts if _DEGREE.search(p)), parts[0] if parts else None)
        years = _YEAR.findall(line)
        year_match = re.findall(r"\b(?:19|20)\d{2}\b", line)
        institution = next((p for p in parts if p != degree and not _YEAR.fullmatch(p)
                            and re.search(r"universit|institut|college|school|iit|nit|iiit", p, re.I)), None)
        education.append(ResumeEducation(degree=degree, institution=institution,
                                         year=year_match[-1] if years else None))
    certifications = [_strip_bullet(ln) for ln in sections.get("certifications", []) if _strip_bullet(ln)][:20]
    achievements = []
    for ln in sections.get("achievements", []):
        t = _strip_bullet(ln)
        if t:
            metric = _METRIC.search(t)
            achievements.append(ResumeAchievement(text=t[:400], metric=metric.group(0) if metric else None))

    domains: set[str] = set()
    for item in (*experience, *projects):
        domains |= set(item.domains)

    return ResumeParsed(
        contact=contact, summary=summary, skills=list(skills.values()), experience=experience, projects=projects,
        education=education, certifications=certifications, achievements=achievements[:20],
        domains=sorted(domains), section_order=[s for s in order if s != "other"],
    )

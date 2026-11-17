"""Deterministic people scoring (FR-PPL-06; docs/AGENT_DESIGN.md §7.4)."""

from __future__ import annotations

import re

from app.models.enums import ROLE_CATEGORIES

_ROLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("hr_business_partner", re.compile(r"\bhr\s*business\s*partner\b|\bhrbp\b", re.I)),
    ("talent_partner", re.compile(r"\btalent\s*partner\b", re.I)),
    ("technical_recruiter", re.compile(r"\b(technical|tech|engineering|it)\s+recruit", re.I)),
    ("talent_acquisition", re.compile(r"\btalent\s*acquisition\b|\bsourc(er|ing)\b", re.I)),
    ("hr_recruiter", re.compile(r"\brecruit(er|ing|ment)\b|\bhr\b|\bhuman resources\b|\bpeople (ops|operations)\b", re.I)),
    ("hiring_manager", re.compile(r"\bhiring\s*manager\b", re.I)),
    ("engineering_manager", re.compile(r"\b(engineering|software|development|ml|ai|data)\s+manager\b|\bmanager,?\s+(engineering|ml|ai)", re.I)),
    ("department_head", re.compile(r"\bhead of\b|\bdirector\b|\bvp\b|\bvice president\b", re.I)),
    ("technical_leader", re.compile(r"\bcto\b|\bchief\s+(technology|ai|data)\b|\bprincipal\b|\bdistinguished\b|\bfellow\b", re.I)),
    ("team_lead", re.compile(r"\b(tech|team|technical)\s+lead\b|\blead\b|\bstaff\b", re.I)),
    ("senior_engineer", re.compile(r"\bsenior\b|\bsr\.?\b", re.I)),
    ("team_member", re.compile(r"\bengineer\b|\bdeveloper\b|\bscientist\b|\banalyst\b|\bresearcher\b", re.I)),
]

_DEPT_GROUPS = {
    "ai": {"ai", "ml", "ai/ml", "machine learning", "artificial intelligence", "applied ai", "genai", "research"},
    "data": {"data", "data science", "data engineering", "analytics"},
    "engineering": {"engineering", "software", "platform", "backend", "infrastructure", "product engineering"},
    "talent": {"talent", "talent acquisition", "recruiting", "recruitment", "hr", "human resources", "people"},
}
_DEPT_ADJACENT = {("ai", "data"), ("ai", "engineering"), ("data", "engineering")}
_SOURCE_SCORES = {"company_page": 100, "job_post": 95, "user_provided": 90, "conference": 70, "blog": 70,
                  "directory": 60, "search_result": 50}


def classify_role(title: str | None, is_poster: bool = False) -> str:
    if is_poster:
        return "job_poster"
    if not title:
        return "other_employee"
    for category, pattern in _ROLE_RULES:
        if pattern.search(title):
            return category
    return "other_employee"


def t_score(role_category: str) -> float:
    rank = ROLE_CATEGORIES.index(role_category) + 1
    return float(100 - 6 * (rank - 1))


def _dept_group(dept: str | None) -> str | None:
    if not dept:
        return None
    d = dept.lower().strip()
    for group, words in _DEPT_GROUPS.items():
        if d in words or any(re.search(rf"\b{re.escape(w)}\b", d) for w in words if len(w) > 2):
            return group
    return d


def d_score(person_dept: str | None, job_dept: str | None) -> float:
    pg, jg = _dept_group(person_dept), _dept_group(job_dept)
    if pg is None:
        return 40.0
    if jg is None:
        return 40.0 if pg != "talent" else 60.0
    if pg == jg:
        return 100.0
    if pg == "talent" or (pg, jg) in _DEPT_ADJACENT or (jg, pg) in _DEPT_ADJACENT:
        return 60.0
    return 10.0


def c_score(association_status: str) -> float:
    return {"verified_current": 100.0, "likely_current": 70.0}.get(association_status, 30.0)


def s_score(source_types: list[str], linkedin: bool = False) -> float:
    best = 0.0
    for st in source_types:
        score = _SOURCE_SCORES.get(st, 50)
        if st == "search_result" and linkedin:
            score = 60
        best = max(best, float(score))
    return best


def people_score(t: float, d: float, c: float, s: float, weights: dict[str, float] | None = None) -> float:
    w = weights or {"T": 0.35, "D": 0.30, "C": 0.20, "S": 0.15}
    return round(w["T"] * t + w["D"] * d + w["C"] * c + w["S"] * s, 2)

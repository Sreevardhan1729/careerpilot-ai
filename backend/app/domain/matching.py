"""Deterministic resume ↔ job matching (FR-RES-07..11; docs/AGENT_DESIGN.md §5).

Match = Σ w·c / Σ w over non-null components K (skills), P (projects), E_rel (experience), R (responsibilities),
D (domain). The LLM never changes these numbers; it only adds prose on top.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.domain.skills import get_taxonomy

CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "scoring_config.yaml"
_IMPORTANCE_ORDER = {"mandatory": 0, "preferred": 1, "mentioned": 2}
MISSING_STATUSES = ("no_evidence", "profile_only", "confirmed_missing")


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    raw: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def similarity(self, provider: str) -> tuple[float, float]:
        scale = self.raw["similarity_scale"].get(provider) or self.raw["similarity_scale"]["nvidia"]
        return float(scale["lo"]), float(scale["hi"])


@lru_cache
def load_scoring_config(path: str | None = None) -> ScoringConfig:
    with Path(path or CONFIG_PATH).open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return ScoringConfig(version=str(raw["version"]), raw=raw)


# ------------------------------------------------------------------------------------------------ inputs


@dataclass(frozen=True)
class JobSkillIn:
    name: str
    importance: str


@dataclass
class JobForMatch:
    skills: list[JobSkillIn]
    focus_embedding: list[float] | None
    responsibility_embeddings: list[list[float]]
    experience_min: float | None
    experience_max: float | None
    domain: str | None


@dataclass
class ResumeItem:
    ref: str
    kind: str  # project | experience
    title: str
    technologies: set[str]
    text: str
    embedding: list[float] | None
    months: float | None
    is_internship: bool
    domains: set[str]


@dataclass
class ResumeForMatch:
    resume_id: uuid.UUID
    version_id: uuid.UUID
    created_at: datetime
    skills_section: set[str]
    evidenced_skills: dict[str, list[str]]
    projects: list[ResumeItem]
    experience: list[ResumeItem]
    chunks: list[tuple[str, list[float] | None]]
    domains: set[str]


@dataclass(frozen=True)
class ProfileSkills:
    has: set[str]
    missing: set[str]


# ------------------------------------------------------------------------------------------------ outputs


@dataclass(frozen=True)
class ComponentScore:
    score: float | None
    weight: float
    explanation: str
    evidence_refs: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchResult:
    resume_id: uuid.UUID
    version_id: uuid.UUID
    created_at: datetime
    score: float
    components: dict[str, ComponentScore]
    mandatory_coverage: float | None
    preferred_coverage: float | None
    skill_breakdown: list[dict[str, Any]]
    missing_skills: list[dict[str, Any]]
    weak_skills: list[str]
    relevant_projects: list[dict[str, Any]]
    relevant_experience: list[dict[str, Any]]
    limitations: list[str]
    rank: int = 0
    is_best: bool = False


# ------------------------------------------------------------------------------------------------ helpers


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _scale(x: float, lo: float, hi: float) -> float:
    return max(0.0, min(1.0, (x - lo) / (hi - lo))) if hi > lo else 0.0


def _all_resume_skills(r: ResumeForMatch) -> set[str]:
    skills = set(r.skills_section) | set(r.evidenced_skills)
    for item in (*r.projects, *r.experience):
        skills |= item.technologies
    return skills


def skill_status(skill: str, r: ResumeForMatch, profile: ProfileSkills) -> str:
    if skill in profile.missing:
        return "confirmed_missing"
    if skill in r.evidenced_skills or any(skill in i.technologies for i in (*r.projects, *r.experience)):
        return "strong"
    if skill in r.skills_section:
        return "listed_only"
    tax = get_taxonomy()
    if any(tax.related(skill, other) for other in _all_resume_skills(r)):
        return "related"
    if skill in profile.has:
        return "profile_only"
    return "no_evidence"


def _dedupe_skills(skills: list[JobSkillIn]) -> list[JobSkillIn]:
    best: dict[str, JobSkillIn] = {}
    for s in skills:
        cur = best.get(s.name)
        if cur is None or _IMPORTANCE_ORDER[s.importance] < _IMPORTANCE_ORDER[cur.importance]:
            best[s.name] = s
    return sorted(best.values(), key=lambda s: (_IMPORTANCE_ORDER[s.importance], s.name))


def _evidence_refs(skill: str, r: ResumeForMatch) -> list[str]:
    refs = list(r.evidenced_skills.get(skill, []))
    refs += [i.ref for i in (*r.projects, *r.experience) if skill in i.technologies and i.ref not in refs]
    return refs


def _fmt(names: list[str]) -> str:
    return ", ".join(names) if names else "none"


# ------------------------------------------------------------------------------------------------ components


def _component_k(job: JobForMatch, r: ResumeForMatch, profile: ProfileSkills, cfg: ScoringConfig):
    credit = cfg["skill_credit"]
    skills = _dedupe_skills(job.skills)
    breakdown = [
        {"skill": s.name, "importance": s.importance, "status": (st := skill_status(s.name, r, profile)),
         "credit": credit[st], "evidence_refs": _evidence_refs(s.name, r)}
        for s in skills
    ]
    groups = {imp: [b for b in breakdown if b["importance"] == imp] for imp in ("mandatory", "preferred", "mentioned")}

    def cov(items: list[dict[str, Any]]) -> float | None:
        return sum(i["credit"] for i in items) / len(items) if items else None

    mand, pref, ment = cov(groups["mandatory"]), cov(groups["preferred"]), cov(groups["mentioned"])
    mix = cfg["skill_mix"]
    if mand is not None and pref is not None:
        k = 100 * (mix["mandatory"] * mand + mix["preferred"] * pref)
    elif mand is not None:
        k = 100 * mand
    elif pref is not None:
        k = 100 * pref
    elif ment is not None:
        k = 100 * ment
    else:
        k = None

    m_items = groups["mandatory"]
    strong = [b["skill"] for b in m_items if b["status"] == "strong"]
    listed = [b["skill"] for b in breakdown if b["status"] == "listed_only"]
    missing = [b["skill"] for b in breakdown if b["status"] in MISSING_STATUSES]
    if k is None:
        explanation = "The job lists no skills, so skill coverage was not scored."
    else:
        explanation = (
            f"{len(strong)}/{len(m_items)} mandatory skills with strong evidence; "
            f"{len(listed)} listed only in the skills section ({_fmt(listed)}); "
            f"no evidence for {_fmt(missing)}."
        )
    refs = tuple(sorted({ref for b in breakdown for ref in b["evidence_refs"]}))
    return ComponentScore(None if k is None else round(k, 2), cfg["match_weights"]["K"], explanation, refs), breakdown, mand, pref


def _component_p(job: JobForMatch, r: ResumeForMatch, cfg: ScoringConfig, provider: str):
    pc = cfg["project"]
    lo, hi = cfg.similarity(provider)
    s_job = {s.name for s in job.skills if s.importance in ("mandatory", "preferred")}
    denom = min(len(s_job), pc["overlap_denominator_cap"]) if s_job else 0
    scored = []
    for p in r.projects:
        tech = min(1.0, len(p.technologies & s_job) / denom) if denom else 0.0
        sem = _scale(cosine(p.embedding, job.focus_embedding), lo, hi)
        scored.append({"ref": p.ref, "title": p.title, "score": round(100 * (pc["tech_weight"] * tech + pc["semantic_weight"] * sem), 2),
                       "matched_skills": sorted(p.technologies & s_job)})
    scored.sort(key=lambda x: (-x["score"], x["ref"]))
    if not scored:
        return ComponentScore(0.0, cfg["match_weights"]["P"], "No projects section found in this resume."), [], ["No projects section"]
    top = scored[: pc["top_n"]]
    p_score = round(sum(x["score"] for x in top) / len(top), 2)
    explanation = "Most relevant: " + "; ".join(
        f"{x['title']} ({x['score']:.0f}, uses {_fmt(x['matched_skills'])})" for x in top
    )
    return ComponentScore(p_score, cfg["match_weights"]["P"], explanation, tuple(x["ref"] for x in top)), scored, []


def _years_fit(y: float, lo: float | None, hi: float | None, unknown: float) -> float:
    if lo is None and hi is None:
        return unknown
    lo = lo or 0
    if y < lo:
        return max(0.0, 100 - 40 * (lo - y))
    if hi is not None and y > hi:
        return max(40.0, 100 - 15 * (y - hi))
    return 100.0


def _component_e(job: JobForMatch, r: ResumeForMatch, cfg: ScoringConfig, provider: str):
    ec = cfg["experience_rel"]
    lo_s, hi_s = cfg.similarity(provider)
    entries = []
    for e in r.experience:
        sim = _scale(cosine(e.embedding, job.focus_embedding), lo_s, hi_s)
        entries.append({"ref": e.ref, "title": e.title, "role_relevance": round(100 * sim, 2), "months": e.months,
                        "is_internship": e.is_internship})
    relevant_months = sum(
        (x["months"] or 0) * (ec["internship_factor"] if x["is_internship"] else 1)
        for x in entries if x["role_relevance"] >= 100 * ec["role_sim_threshold"]
    )
    y = round(relevant_months / 12, 2)
    years_fit = _years_fit(y, job.experience_min, job.experience_max, ec["unknown_requirement_score"])
    role_rel = max((x["role_relevance"] for x in entries), default=0.0)
    score = round(ec["years_weight"] * years_fit + ec["role_weight"] * role_rel, 2)
    if job.experience_min is None and job.experience_max is None:
        req = "The job does not state an experience requirement"
    else:
        req = f"Job asks for {job.experience_min or 0}–{job.experience_max if job.experience_max is not None else '+'} years"
    explanation = f"{req}; this resume shows ~{y:.1f} relevant years."
    entries.sort(key=lambda x: (-x["role_relevance"], x["ref"]))
    detail = {"years_fit": years_fit, "relevant_years": y, "role_relevance": role_rel}
    return ComponentScore(score, cfg["match_weights"]["E_rel"], explanation, tuple(x["ref"] for x in entries[:2]), detail), entries


def _component_r(job: JobForMatch, r: ResumeForMatch, cfg: ScoringConfig, provider: str) -> ComponentScore:
    if not job.responsibility_embeddings:
        return ComponentScore(None, cfg["match_weights"]["R"], "The job lists no responsibilities.")
    lo, hi = cfg.similarity(provider)
    per, refs = [], []
    for resp in job.responsibility_embeddings:
        best_id, best = None, 0.0
        for cid, emb in r.chunks:
            c = cosine(resp, emb)
            if c > best:
                best_id, best = cid, c
        per.append(_scale(best, lo, hi))
        if best_id:
            refs.append(best_id)
    score = round(100 * sum(per) / len(per), 2)
    aligned = sum(1 for s in per if s >= 0.5)
    return ComponentScore(score, cfg["match_weights"]["R"],
                          f"{aligned}/{len(per)} responsibilities closely match resume content.", tuple(dict.fromkeys(refs)))


def _component_d(job: JobForMatch, r: ResumeForMatch, cfg: ScoringConfig) -> ComponentScore:
    dc = cfg["domain"]
    weight = cfg["match_weights"]["D"]
    domains = set(r.domains)
    for item in (*r.projects, *r.experience):
        domains |= item.domains
    if not job.domain:
        return ComponentScore(float(dc["job_unknown"]), weight, "The job's business domain is not stated.")
    if not domains:
        return ComponentScore(float(dc["resume_unknown"]), weight, "This resume does not show a business domain.")
    if job.domain in domains:
        return ComponentScore(float(dc["exact"]), weight, f"Resume shows {job.domain} domain experience.")
    tax = get_taxonomy()
    adjacent = sorted(d for d in domains if tax.domains_adjacent(job.domain, d))
    if adjacent:
        return ComponentScore(float(dc["adjacent"]), weight, f"Adjacent domain experience: {_fmt(adjacent)}.")
    return ComponentScore(0.0, weight, f"No {job.domain} or adjacent domain experience shown.")


# ------------------------------------------------------------------------------------------------ public


def score_resume(job: JobForMatch, r: ResumeForMatch, profile: ProfileSkills, cfg: ScoringConfig, provider: str) -> MatchResult:
    k, breakdown, mand, pref = _component_k(job, r, profile, cfg)
    p, projects, p_limits = _component_p(job, r, cfg, provider)
    e, experience = _component_e(job, r, cfg, provider)
    rr = _component_r(job, r, cfg, provider)
    d = _component_d(job, r, cfg)
    components = {"K": k, "P": p, "E_rel": e, "R": rr, "D": d}
    limitations = list(p_limits)
    if k.score is None:
        limitations.append("The job lists no skills; skill coverage excluded and weights renormalised.")
    if rr.score is None:
        limitations.append("The job lists no responsibilities; responsibility alignment excluded.")
    if job.experience_min is None and job.experience_max is None:
        limitations.append("Experience requirement not stated in the job.")
    if not job.domain:
        limitations.append("Business domain not stated in the job.")
    active = {name: c for name, c in components.items() if c.score is not None}
    total_w = sum(c.weight for c in active.values())
    score = round(sum(c.score * c.weight for c in active.values()) / total_w, 1) if total_w else 0.0  # type: ignore[operator]
    return MatchResult(
        resume_id=r.resume_id,
        version_id=r.version_id,
        created_at=r.created_at,
        score=score,
        components=components,
        mandatory_coverage=None if mand is None else round(mand, 4),
        preferred_coverage=None if pref is None else round(pref, 4),
        skill_breakdown=breakdown,
        missing_skills=[{"skill": b["skill"], "importance": b["importance"], "status": b["status"]}
                        for b in breakdown if b["status"] in MISSING_STATUSES],
        weak_skills=[b["skill"] for b in breakdown if b["status"] == "listed_only"],
        relevant_projects=projects,
        relevant_experience=experience,
        limitations=limitations,
    )


def rank_results(results: list[MatchResult]) -> list[MatchResult]:
    def key(m: MatchResult):
        k = m.components["K"].score or 0.0
        return (-m.score, -k, -(m.mandatory_coverage or 0.0), -m.created_at.timestamp(), str(m.version_id))

    ordered = sorted(results, key=key)
    return [replace(m, rank=i + 1, is_best=(i == 0)) for i, m in enumerate(ordered)]


def result_to_json(m: MatchResult) -> dict[str, Any]:
    return {
        name: {"score": c.score, "weight": c.weight, "explanation": c.explanation, "evidence_refs": list(c.evidence_refs),
               "detail": c.detail}
        for name, c in m.components.items()
    }

"""Deterministic job ranking (FR-RANK; docs/AGENT_DESIGN.md §6).

Job Score = 0.50M + 0.20F + 0.15E_elig + 0.10L + 0.05S — a prioritisation heuristic, never a shortlist probability.
Disqualifiers are flagged, never used to filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.domain.matching import ScoringConfig
from app.domain.normalize import annualize, city_key

_AUTH = re.compile(
    r"citizen(ship)?|security clearance|\bclearance\b|work authori[sz]ation|authori[sz]ed to work|green card|"
    r"no visa sponsorship|without sponsorship|right to work",
    re.IGNORECASE,
)


@dataclass
class RankingInput:
    match_score: float | None
    posted_at: datetime | None
    collected_at: datetime | None
    now: datetime
    experience_min: float | None
    experience_max: float | None
    candidate_years: float | None
    job_locations: list[dict[str, Any]]
    work_mode: str
    preferred_cities: list[str]
    remote_ok: bool
    candidate_country: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    salary_source_type: str
    pref_salary_min: float | None
    pref_salary_currency: str | None
    employment_type: str
    preferred_employment_types: list[str]
    mandatory_texts: list[str] = field(default_factory=list)
    work_authorization: str | None = None
    deadline: date | None = None


@dataclass
class JobScore:
    score: float
    priority: str
    components: dict[str, dict[str, Any]]
    disqualifiers: list[str]
    limitations: list[str]
    salary_known: bool
    recent: bool
    experience_eligible: bool | None

    def to_json(self) -> dict[str, Any]:
        return {
            "score": self.score, "priority": self.priority, "components": self.components,
            "disqualifiers": self.disqualifiers, "limitations": self.limitations, "salary_known": self.salary_known,
            "recent": self.recent, "experience_eligible": self.experience_eligible,
            "disclaimer": "A prioritisation heuristic, not a probability of being shortlisted.",
        }


def band(score: float, cfg: ScoringConfig) -> str:
    b = cfg["bands"]
    if score >= b["excellent"]:
        return "excellent"
    if score >= b["strong"]:
        return "strong"
    if score >= b["moderate"]:
        return "moderate"
    return "low"


def _freshness_from_days(d: float, cfg: ScoringConfig) -> float:
    fc = cfg["freshness"]
    if d <= fc["full_days"]:
        return 100.0
    if d > fc["zero_days"]:
        return 0.0
    span = fc["zero_days"] - fc["full_days"]
    return round(100 - 100 * (d - fc["full_days"]) / span, 2)


def _freshness(i: RankingInput, cfg: ScoringConfig, limits: list[str]) -> tuple[float, str]:
    if i.posted_at is not None:
        d = max(0.0, (i.now - i.posted_at).total_seconds() / 86400)
        return _freshness_from_days(d, cfg), f"Posted {d:.0f} day(s) ago."
    limits.append("Posting date unknown; freshness capped.")
    base = _freshness_from_days(max(0.0, (i.now - i.collected_at).total_seconds() / 86400), cfg) if i.collected_at else 0.0
    return min(float(cfg["freshness"]["unknown_cap"]), base), "Posting date unknown; using first-seen date (capped)."


def _eligibility(i: RankingInput, cfg: ScoringConfig, flags: list[str], limits: list[str]) -> tuple[float, str, bool | None]:
    ec = cfg["eligibility"]
    if i.experience_min is None and i.experience_max is None:
        return float(ec["unknown"]), "The job does not state required experience.", None
    if i.candidate_years is None:
        limits.append("Your total experience is not set in the profile.")
        return float(ec["unknown"]), "Your total experience is unknown.", None
    y, lo, hi = i.candidate_years, i.experience_min or 0, i.experience_max
    if y < lo:
        gap = lo - y
        if gap <= 1:
            return float(ec["short_1y"]), f"Requires {lo:g}+ years; you have {y:g} (stretch).", False
        if gap <= 2:
            return float(ec["short_2y"]), f"Requires {lo:g}+ years; you have {y:g}.", False
        flags.append(f"Requires {lo:g}+ years of experience; you have {y:g}.")
        return 0.0, f"Requires {lo:g}+ years; you have {y:g}.", False
    if hi is not None and y > hi:
        if y - hi <= 1:
            return float(ec["over_1y"]), f"Range is {lo:g}–{hi:g} years; you have {y:g}.", True
        flags.append(f"Possibly overqualified: range {lo:g}–{hi:g} years, you have {y:g}.")
        return float(ec["over_more"]), f"Range is {lo:g}–{hi:g} years; you have {y:g}.", True
    return 100.0, "Experience requirement satisfied.", True


def _location(i: RankingInput, cfg: ScoringConfig, flags: list[str]) -> tuple[float, str]:
    lc = cfg["location"]
    prefs = {(city_key(c) or c).lower() for c in i.preferred_cities}
    countries = {loc.get("country") for loc in i.job_locations if loc.get("country")}
    if i.work_mode == "remote":
        if i.remote_ok and (not countries or i.candidate_country in countries):
            return float(lc["match"]), "Remote role open to your country."
        flags.append("Remote role restricted to another country or remote not in your preferences.")
        return float(lc["other"]), "Remote role outside your preferences."
    cities = [(city_key(loc.get("city")) or "").lower() for loc in i.job_locations if loc.get("city")]
    if any(c in prefs for c in cities):
        return float(lc["match"]), "Location matches your preferences."
    if not i.job_locations:
        return float(lc["unknown"]), "Location not stated."
    if i.candidate_country and i.candidate_country in countries:
        return float(lc["same_country"]), "Same country, different city from your preferences."
    flags.append("Location outside your preferences.")
    return float(lc["other"]), "Location outside your preferences."


def _salary(i: RankingInput, cfg: ScoringConfig, limits: list[str]) -> tuple[float, str, bool]:
    sc = cfg["salary"]
    if i.salary_source_type == "not_disclosed" or (i.salary_min is None and i.salary_max is None):
        return float(sc["unknown"]), "Salary not disclosed.", False
    if i.salary_source_type == "third_party_estimate":
        return float(sc["unknown"]), "Only a third-party estimate is available (not scored).", True
    if i.pref_salary_min is None:
        return float(sc["unknown"]), "No salary preference set.", True
    if i.salary_currency and i.pref_salary_currency and i.salary_currency != i.pref_salary_currency:
        limits.append("Salary currency differs from your preference; not converted.")
        return float(sc["unknown"]), "Salary in a different currency.", True
    jmin = annualize(i.salary_min if i.salary_min is not None else i.salary_max, i.salary_period)
    jmax = annualize(i.salary_max if i.salary_max is not None else i.salary_min, i.salary_period)
    if jmin is None or jmax is None:
        limits.append("Salary pay period unknown; not scored.")
        return float(sc["unknown"]), "Salary period unknown.", True
    pref = float(i.pref_salary_min)
    if jmax >= pref:
        return (float(sc["meets_min"]), "Salary meets your minimum.", True) if jmin >= pref else (
            float(sc["straddles"]), "Salary range includes your minimum.", True)
    score = max(0.0, sc["straddles"] * (1 - (pref - jmax) / (0.5 * pref)))
    return round(score, 2), "Salary is below your minimum.", True


def _flag_requirements(i: RankingInput, flags: list[str]) -> None:
    for text in i.mandatory_texts:
        if _AUTH.search(text) and not (i.work_authorization and _AUTH.search(i.work_authorization)):
            flags.append(f"Mandatory requirement mentions citizenship / work authorisation / clearance: \"{text[:120]}\"")
            break
    if (
        i.preferred_employment_types
        and i.employment_type not in ("unknown", *i.preferred_employment_types)
    ):
        flags.append(f"Employment type '{i.employment_type}' is not in your preferences.")
    if i.deadline and i.deadline < i.now.date():
        flags.append(f"Application deadline {i.deadline.isoformat()} has passed.")


def score_job(i: RankingInput, cfg: ScoringConfig) -> JobScore:
    flags: list[str] = []
    limits: list[str] = []
    w = cfg["job_weights"]
    if i.match_score is None:
        limits.append("No resume match yet; M counted as 0.")
        m, m_exp = 0.0, "No resume has been matched yet."
    else:
        m, m_exp = float(i.match_score), f"Best resume match score {i.match_score:.1f}."
    f, f_exp = _freshness(i, cfg, limits)
    e, e_exp, eligible = _eligibility(i, cfg, flags, limits)
    loc, l_exp = _location(i, cfg, flags)
    s, s_exp, salary_known = _salary(i, cfg, limits)
    _flag_requirements(i, flags)
    components = {
        "M": {"score": m, "weight": w["M"], "explanation": m_exp},
        "F": {"score": f, "weight": w["F"], "explanation": f_exp},
        "E_elig": {"score": e, "weight": w["E_elig"], "explanation": e_exp},
        "L": {"score": loc, "weight": w["L"], "explanation": l_exp},
        "S": {"score": s, "weight": w["S"], "explanation": s_exp},
    }
    total = round(sum(c["score"] * c["weight"] for c in components.values()), 1)
    return JobScore(total, band(total, cfg), components, flags, limits, salary_known, f >= 70, eligible)

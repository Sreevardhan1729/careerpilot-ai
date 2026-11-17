"""Deterministic normalisers: experience, salary, locations, work mode, employment type, seniority, dates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import dateparser

from app.domain.text import normalize_unicode

# ---------------------------------------------------------------------------------------------- experience


@dataclass(frozen=True)
class ExperienceRange:
    minimum_years: float | None
    maximum_years: float | None
    evidence: str


_YEARS = r"(?:years?|yrs?)"
_NUM = r"(\d+(?:\.\d+)?)"
_EXP_WORDS = re.compile(r"experience|exp\b|industry|professional|work(?:ing)?\b|background", re.IGNORECASE)
_NOT_EXPERIENCE_AFTER = re.compile(r"^\s*(?:ago|old|of age|in business|history|warranty)", re.IGNORECASE)

_RANGE = re.compile(rf"{_NUM}\s*(?:-|to)\s*{_NUM}\s*\+?\s*{_YEARS}", re.IGNORECASE)
_PLUS = re.compile(rf"{_NUM}\s*\+\s*{_YEARS}", re.IGNORECASE)
_MIN = re.compile(rf"(?:minimum(?: of)?|min\.?|at ?least)\s*{_NUM}\s*\+?\s*{_YEARS}", re.IGNORECASE)
_PLAIN = re.compile(rf"{_NUM}\s*{_YEARS}\s*(?:of\s+)?(?:[\w/+#.-]+\s+){{0,3}}?(?:experience|exp\b)", re.IGNORECASE)
_MONTHS = re.compile(r"(\d+)\s*months?\s*(?:of\s+)?(?:[\w-]+\s+){0,2}?experience", re.IGNORECASE)
_FRESHER = re.compile(r"\bfreshers?\b|\bno (?:prior )?experience (?:is )?(?:required|needed)\b", re.IGNORECASE)


def _num(s: str) -> float:
    v = float(s)
    return int(v) if v.is_integer() else v  # type: ignore[return-value]


def _window(text: str, start: int, end: int, size: int = 60) -> str:
    return text[max(0, start - size): end + size]


def parse_experience(text: str) -> ExperienceRange | None:
    """Only explicit statements; never inferred (FR-JOB-07)."""
    t = normalize_unicode(text)
    for m in _RANGE.finditer(t):
        if _NOT_EXPERIENCE_AFTER.match(t[m.end():]) or not _EXP_WORDS.search(_window(t, m.start(), m.end())):
            continue
        lo, hi = _num(m.group(1)), _num(m.group(2))
        if lo <= hi <= 40:
            return ExperienceRange(lo, hi, m.group(0))
    for pattern in (_MIN, _PLUS):
        for m in pattern.finditer(t):
            if _NOT_EXPERIENCE_AFTER.match(t[m.end():]):
                continue
            return ExperienceRange(_num(m.group(1)), None, m.group(0))
    m = _PLAIN.search(t)
    if m:
        return ExperienceRange(_num(m.group(1)), None, m.group(0))
    m = _MONTHS.search(t)
    if m:
        return ExperienceRange(round(int(m.group(1)) / 12, 1), None, m.group(0))
    m = _FRESHER.search(t)
    if m:
        return ExperienceRange(0, None, m.group(0))
    return None


# ---------------------------------------------------------------------------------------------- salary


@dataclass(frozen=True)
class SalaryRange:
    minimum: float
    maximum: float
    currency: str | None
    period: str
    evidence: str


_CUR = r"(₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP)"
_AMT = r"(\d+(?:[.,]\d+)*)"
_UNIT = r"(k|K|L|LPA|lpa|lakhs?|lacs?|Lakhs?|crores?|cr)"
_SALARY = re.compile(
    rf"{_CUR}?\s*{_AMT}\s*{_UNIT}?\b\s*(?:(?:-|to)\s*{_CUR}?\s*{_AMT}\s*{_UNIT}?\b)?"
    r"(\s*(?:/|per\s+)\s*(?:annum|year|yr|month|mo|hour|hr)\b|\s*(?:p\.?a\.?|pm|monthly|yearly|annually|hourly)\b)?",
    re.IGNORECASE,
)
_SALARY_KEYWORDS = re.compile(r"salary|ctc|compensation|pay\b|stipend|package|lpa|per annum|remuneration", re.IGNORECASE)
_CURRENCY_MAP = {"₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}


def _parse_amount(raw: str) -> float:
    if raw.count(".") == 1 and len(raw.split(".")[1]) <= 2 and "," not in raw:
        return float(raw)
    return float(raw.replace(",", "").split(".")[0]) if raw.count(".") > 1 else float(raw.replace(",", ""))


def _unit_multiplier(unit: str | None) -> tuple[float, str | None]:
    if not unit:
        return 1, None
    u = unit.lower()
    if u == "k":
        return 1_000, "annual"
    if u in ("l", "lpa", "lakh", "lakhs", "lac", "lacs"):
        return 100_000, "annual"
    if u in ("crore", "crores", "cr"):
        return 10_000_000, "annual"
    return 1, None


def _period_from(text: str) -> str | None:
    s = text.lower()
    if re.search(r"hour|\bhr\b|hourly", s):
        return "hourly"
    if re.search(r"month|\bmo\b|\bpm\b|monthly", s):
        return "monthly"
    if re.search(r"annum|year|\byr\b|p\.?a\.?|yearly|annually|lpa", s):
        return "annual"
    return None


def parse_salary(text: str) -> SalaryRange | None:
    t = normalize_unicode(text)
    for m in _SALARY.finditer(t):
        cur1, a, u1, cur2, b, u2, period_part = m.groups()
        cur = cur1 or cur2
        unit = u1 or u2
        has_signal = bool(cur) or (unit and unit.lower() not in ("k",)) or bool(
            unit and _SALARY_KEYWORDS.search(_window(t, m.start(), m.end(), 40))
        )
        if not has_signal or not a:
            continue
        mult, unit_period = _unit_multiplier(unit)
        lo = _parse_amount(a) * (_unit_multiplier(u1)[0] if u1 else mult)
        hi = _parse_amount(b) * (_unit_multiplier(u2)[0] if u2 else mult) if b else lo
        if hi < lo or lo <= 0:
            continue
        tail = t[m.end(): m.end() + 30]
        period = _period_from(period_part or "") or _period_from(tail) or unit_period
        if period is None and _SALARY_KEYWORDS.search(_window(t, m.start(), m.end(), 40)):
            period = "annual" if lo >= 100_000 or (cur and cur != "₹" and lo >= 10_000) else "unknown"
        currency = _CURRENCY_MAP.get((cur or "").lower()) or ("INR" if unit and unit.lower() not in ("k",) else None)
        return SalaryRange(lo, hi, currency, period or "unknown", m.group(0).strip())
    return None


def annualize(amount: float | None, period: str | None) -> float | None:
    if amount is None:
        return None
    return {"annual": amount, "monthly": amount * 12, "hourly": amount * 2080}.get(period or "")


# ---------------------------------------------------------------------------------------------- locations

_CITIES: dict[str, tuple[str, str, list[str]]] = {
    "Bengaluru": ("Karnataka", "India", ["bengaluru", "bangalore", "blr"]),
    "Hyderabad": ("Telangana", "India", ["hyderabad", "secunderabad"]),
    "Pune": ("Maharashtra", "India", ["pune"]),
    "Chennai": ("Tamil Nadu", "India", ["chennai", "madras"]),
    "Mumbai": ("Maharashtra", "India", ["mumbai", "bombay", "navi mumbai"]),
    "Gurugram": ("Haryana", "India", ["gurugram", "gurgaon"]),
    "Noida": ("Uttar Pradesh", "India", ["noida", "greater noida"]),
    "Delhi": ("Delhi", "India", ["new delhi", "delhi", "delhi ncr", "ncr"]),
    "Kolkata": ("West Bengal", "India", ["kolkata", "calcutta"]),
    "Ahmedabad": ("Gujarat", "India", ["ahmedabad"]),
    "Kochi": ("Kerala", "India", ["kochi", "cochin"]),
    "Thiruvananthapuram": ("Kerala", "India", ["thiruvananthapuram", "trivandrum"]),
    "Coimbatore": ("Tamil Nadu", "India", ["coimbatore"]),
    "Jaipur": ("Rajasthan", "India", ["jaipur"]),
    "Indore": ("Madhya Pradesh", "India", ["indore"]),
    "Chandigarh": ("Chandigarh", "India", ["chandigarh", "mohali"]),
    "Mysuru": ("Karnataka", "India", ["mysuru", "mysore"]),
    "Singapore": ("Singapore", "Singapore", ["singapore"]),
    "London": ("England", "United Kingdom", ["london"]),
    "New York": ("New York", "United States", ["new york", "nyc"]),
    "San Francisco": ("California", "United States", ["san francisco", "sf bay area", "bay area"]),
    "Seattle": ("Washington", "United States", ["seattle"]),
    "Toronto": ("Ontario", "Canada", ["toronto"]),
    "Berlin": ("Berlin", "Germany", ["berlin"]),
    "Dubai": ("Dubai", "United Arab Emirates", ["dubai"]),
}
_COUNTRIES = {"india": "India", "united states": "United States", "usa": "United States", "us": "United States",
              "uk": "United Kingdom", "united kingdom": "United Kingdom", "canada": "Canada", "germany": "Germany",
              "singapore": "Singapore", "uae": "United Arab Emirates"}
_ALIAS_TO_CITY = {alias: city for city, (_, _, aliases) in _CITIES.items() for alias in aliases}
_CITY_PATTERN = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(a) for a in sorted(_ALIAS_TO_CITY, key=len, reverse=True)) + r")(?![a-z])",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\bfully distributed\b", re.IGNORECASE)


def city_key(name: str | None) -> str | None:
    if not name:
        return None
    return _ALIAS_TO_CITY.get(name.strip().lower(), name.strip().title())


def normalize_location(raw: str) -> dict[str, Any]:
    text = normalize_unicode(raw).strip()
    m = _CITY_PATTERN.search(text)
    city = _ALIAS_TO_CITY[m.group(1).lower()] if m else None
    region, country = (_CITIES[city][0], _CITIES[city][1]) if city else (None, None)
    low = text.lower()
    for key, name in _COUNTRIES.items():
        if re.search(rf"(?<![a-z]){re.escape(key)}(?![a-z])", low):
            country = country or name
            break
    if city is None and "," in text:
        region = text.split(",")[1].strip() or None
    return {"city": city, "region": region, "country": country, "remote": bool(_REMOTE.search(text)), "raw": raw}


def find_locations(text: str) -> list[dict[str, Any]]:
    seen: list[str] = []
    for m in _CITY_PATTERN.finditer(normalize_unicode(text)):
        city = _ALIAS_TO_CITY[m.group(1).lower()]
        if city not in seen:
            seen.append(city)
    return [{"city": c, "region": _CITIES[c][0], "country": _CITIES[c][1], "remote": False, "raw": c} for c in seen]


# ---------------------------------------------------------------------------------------------- modes, types


def _line_with(text: str, start: int, end: int) -> str:
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    line = text[ls: le if le >= 0 else len(text)].strip()
    return line[:160]


_MODE_WORDS = {"remote": "remote", "wfh": "remote", "work from home": "remote", "hybrid": "hybrid", "onsite": "onsite",
               "on-site": "onsite", "on site": "onsite", "in-office": "onsite", "in office": "onsite", "wfo": "onsite",
               "work from office": "onsite"}
_MODE_LABEL = re.compile(
    r"(?im)^[ \t]*(?:work(?:place)?[ \t]*(?:mode|type|model|arrangement|setup)|job[ \t]*location|location|mode)[ \t]*[:\-–][^\n]*?"
    r"\b(remote|hybrid|on[\s-]?site|in[\s-]office|wfo|wfh|work from office|work from home)\b")
_NEGATED_BEFORE = re.compile(r"\b(?:no|not|non|without|zero|isn't|is not|never)\b[\w\s-]{0,12}$", re.I)
_NEGATED_AFTER = re.compile(r"^[\w\s-]{0,12}\b(?:is |are )?(?:not|n't)\s+(?:available|possible|allowed|offered|an option|supported)", re.I)
_REMOTE_NOUN = re.compile(r"^\s*(?:-?\s*first\s+)?(?:teams?|colleagues|members|collaborat\w*|stakeholders|engineers|offices?|"
                          r"partners|customers|users|clients|workers|employees|work culture|friendly)\b", re.I)
_WORK_MODES = [
    ("hybrid", re.compile(r"\bhybrid\b", re.IGNORECASE)),
    ("remote", _REMOTE),
    ("onsite", re.compile(r"\bon[\s-]?site\b|\bwork from office\b|\bwfo\b|\bin[\s-]office\b|\bin office\b", re.IGNORECASE)),
]


def _negated(text: str, start: int, end: int) -> bool:
    return bool(_NEGATED_BEFORE.search(text[max(0, start - 30): start]) or _NEGATED_AFTER.search(text[end: end + 40]))


def detect_work_mode(text: str) -> tuple[str, str | None]:
    """Labelled lines win; then the first un-negated keyword (hybrid > remote > onsite). 'remote teams' is not a mode."""
    m = _MODE_LABEL.search(text)
    if m:
        word = re.sub(r"\s+", " ", m.group(1).lower()).replace("on site", "onsite")
        return _MODE_WORDS.get(word, _MODE_WORDS.get(word.replace(" ", "-"), "unknown")), _line_with(text, m.start(), m.end())
    for mode, pattern in _WORK_MODES:
        for m in pattern.finditer(text):
            if _negated(text, m.start(), m.end()):
                continue
            if mode == "remote" and _REMOTE_NOUN.match(text[m.end():]):
                continue
            return mode, _line_with(text, m.start(), m.end())
    return "unknown", None


_EMPLOYMENT_LABEL = re.compile(r"(?im)^[ \t]*(?:employment|job|position|contract)[ \t]*type[ \t]*[:\-–][ \t]*([^\n]+)")
_EMPLOYMENT = [
    ("internship", re.compile(r"\binternship\b|\bintern\b", re.IGNORECASE)),
    ("contract", re.compile(r"\bcontract(?:ual)?\b|\bfreelance\b|\bcontract[\s-]to[\s-]hire\b", re.IGNORECASE)),
    ("part_time", re.compile(r"\bpart[\s-]time\b", re.IGNORECASE)),
    ("temporary", re.compile(r"\btemporary\b|\btemp role\b", re.IGNORECASE)),
    ("full_time", re.compile(r"\bfull[\s-]time\b|\bpermanent\b|\bfte\b", re.IGNORECASE)),
]
_AS_EXPERIENCE_BEFORE = re.compile(r"\b(?:prior|previous|past|any|relevant|earlier|completed)\s+$", re.I)
_AS_EXPERIENCE_AFTER = re.compile(r"^\s*(?:experience|exposure|background|projects?|certificates?)\b", re.I)


def _employment_in(text: str, skip_experience: bool) -> tuple[str, str | None]:
    for etype, pattern in _EMPLOYMENT:
        for m in pattern.finditer(text):
            if _negated(text, m.start(), m.end()):
                continue
            if skip_experience and etype in ("internship", "contract") and (
                _AS_EXPERIENCE_BEFORE.search(text[max(0, m.start() - 20): m.start()]) or _AS_EXPERIENCE_AFTER.match(text[m.end():])
            ):
                continue
            return etype, _line_with(text, m.start(), m.end())
    return "unknown", None


def detect_employment_type(text: str) -> tuple[str, str | None]:
    m = _EMPLOYMENT_LABEL.search(text)
    if m:
        etype, _ = _employment_in(m.group(1), skip_experience=False)
        if etype != "unknown":
            return etype, _line_with(text, m.start(), m.end())
    return _employment_in(text, skip_experience=True)


_SENIORITY = [
    ("intern", re.compile(r"\bintern(ship)?\b", re.IGNORECASE)),
    ("graduate", re.compile(r"\bgraduate\b|\btrainee\b|\bnew grad\b|\bfresher\b|\bcampus\b|\bapprentice\b", re.IGNORECASE)),
    ("principal", re.compile(r"\bprincipal\b|\bdistinguished\b|\barchitect\b", re.IGNORECASE)),
    ("lead", re.compile(r"\blead\b|\bstaff\b|\bhead of\b", re.IGNORECASE)),
    ("senior", re.compile(r"\bsenior\b|\bsr\.?\b", re.IGNORECASE)),
    ("junior", re.compile(r"\bjunior\b|\bjr\.?\b|\bassociate\b|\bentry[\s-]level\b|\b(?:sde|engineer|developer)\s*(?:1|i)\b", re.IGNORECASE)),
    ("mid", re.compile(r"\bmid[\s-]?level\b|\b(?:sde|engineer|developer)\s*(?:2|ii)\b", re.IGNORECASE)),
]


def detect_seniority(title: str | None) -> str:
    if not title:
        return "unknown"
    for level, pattern in _SENIORITY:
        if pattern.search(title):
            return level
    return "unknown"


# ---------------------------------------------------------------------------------------------- dates

_DATE_HINT = re.compile(
    r"\d|\b(today|yesterday|tomorrow|ago|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.IGNORECASE
)


def parse_date(text: str | None, prefer: str = "past", base: datetime | None = None, tz: str = "Asia/Kolkata") -> datetime | None:
    """Parse absolute or relative dates; returns an aware datetime in `tz` (callers convert to UTC)."""
    if not text or not _DATE_HINT.search(text):
        return None
    zone = ZoneInfo(tz)
    base_local = (base or datetime.now(tz=zone)).astimezone(zone).replace(tzinfo=None)
    parsed = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": prefer,
            "RELATIVE_BASE": base_local,
            "TIMEZONE": tz,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DAY_OF_MONTH": "first",
        },
    )
    if parsed is None:
        return None
    return parsed.astimezone(zone)

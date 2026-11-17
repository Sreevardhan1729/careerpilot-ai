"""Multi-signal job deduplication (spec §4.5; docs/AGENT_DESIGN.md §9.3). Title alone never merges."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.normalize import city_key, normalize_location
from app.domain.text import normalize_for_match

POSTING_WINDOW_DAYS = 45

_REQ_ID = re.compile(r"\(?\b(?:req(?:uisition)?|job)?\s*(?:id|#)?\s*[:#]?\s*[A-Z]{0,4}-?\d{3,}\b\)?", re.IGNORECASE)
_BRACKETS = re.compile(r"[\[(]([^\])]*)[\])]")
_TRAILING = re.compile(r"\s+[-–|@,]\s+([^-–|@,]+)$")
_PLACE_WORDS = {"remote", "hybrid", "onsite", "on-site", "wfh", "india", "anywhere", "global", "worldwide", "emea", "apac", "us",
                "usa", "uk", "europe", "remote india", "remote - india", "pan india", "multiple locations"}


def _is_place_note(text: str) -> bool:
    t = normalize_for_match(text).strip(" ,.-")
    if not t:
        return True
    if t in _PLACE_WORDS or re.fullmatch(r"(?:remote|hybrid|onsite|on-site)(?:\s*[-,/(]\s*[a-z ]+\)?)?", t):
        return True
    if _REQ_ID.fullmatch(text.strip()):
        return True
    loc = normalize_location(text)
    return bool(loc["city"]) and len(t.split()) <= 4


def normalize_title(title: str | None) -> str:
    """Lowercase, drop req ids and *location/work-mode* notes only; seniority and specialisms (Backend, ML…) are kept."""
    if not title:
        return ""
    t = _BRACKETS.sub(lambda m: " " if _is_place_note(m.group(1)) else f" {m.group(1)} ", title)
    t = _REQ_ID.sub(" ", t).strip()
    while (m := _TRAILING.search(t)) and _is_place_note(m.group(1)):
        t = t[: m.start()].strip()
    t = re.sub(r"[^a-z0-9+#/ ]", " ", normalize_for_match(t))
    return re.sub(r"\s+", " ", t).strip()


def location_key(locations: list[dict[str, Any]] | None, work_mode: str | None) -> str | None:
    for loc in locations or []:
        city = loc.get("city")
        if city:
            return (city_key(city) or city).lower()
    if work_mode == "remote":
        return "remote"
    return None


@dataclass(frozen=True)
class ListingKey:
    canonical_url: str | None
    source_name: str | None
    source_listing_id: str | None
    application_url: str | None
    description_hash: str | None
    company_id: uuid.UUID | None
    normalized_title: str | None
    location_key: str | None
    posted_at: datetime | None


@dataclass
class ExistingJob:
    job_id: uuid.UUID
    keys: list[ListingKey] = field(default_factory=list)


def _within_window(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return True
    return abs((a - b).days) <= POSTING_WINDOW_DAYS


def _same_source_other_listing(keys: list[ListingKey], candidate: ListingKey) -> bool:
    """Two different postings from one source (different listing ids) are never merged on title similarity."""
    return bool(candidate.source_name and candidate.source_listing_id) and any(
        k.source_name == candidate.source_name and k.source_listing_id and k.source_listing_id != candidate.source_listing_id
        for k in keys)


def find_duplicate(candidate: ListingKey, existing: list[ExistingJob]) -> tuple[uuid.UUID, str] | None:
    """Return (job_id, signal) of the first existing job matched by the strongest signal, else None."""
    c = candidate

    def title_rule(k: ListingKey, job: ExistingJob) -> bool:
        return (c.company_id is not None and k.company_id == c.company_id and bool(c.normalized_title)
                and k.normalized_title == c.normalized_title and c.location_key is not None
                and k.location_key == c.location_key and _within_window(k.posted_at, c.posted_at)
                and not _same_source_other_listing(job.keys, c))

    signals = (
        ("canonical_url", lambda k, job: bool(c.canonical_url) and k.canonical_url == c.canonical_url),
        ("source_listing_id", lambda k, job: bool(c.source_listing_id) and k.source_name == c.source_name
         and k.source_listing_id == c.source_listing_id),
        ("application_url", lambda k, job: bool(c.application_url) and k.application_url == c.application_url),
        ("content_hash", lambda k, job: bool(c.description_hash) and k.description_hash == c.description_hash),
        ("company_title_location", title_rule),
    )
    for name, predicate in signals:
        for job in existing:
            if any(predicate(k, job) for k in job.keys):
                return job.job_id, name
    return None

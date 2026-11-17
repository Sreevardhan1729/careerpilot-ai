"""Automated discovery: source management, per-source runs, prefilter, dedup/merge (spec §4.5, §10)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.db import user_session
from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.domain.dedup import ListingKey, location_key, normalize_title
from app.domain.normalize import normalize_location
from app.domain.text import clean_text, description_hash
from app.domain.urls import canonical_job_key, canonicalize_url
from app.integrations.fetch import SafeFetcher
from app.integrations.sources import NormalizedListing, SourceConfig, get_adapter
from app.models import CrawlRun, CrawlSource, Job, JobSourceRecord, SearchConfig
from app.services import jobs as jobs_svc
from app.services.notifications import notify

log = get_logger(__name__)
AUTO_DISABLE_AFTER = 7
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
_STOP = {"engineer", "developer", "senior", "junior", "the", "and", "of", "sde"}


async def validate_identifier(source_type: str, identifier: str) -> str:
    ident = identifier.strip()
    if source_type in ("greenhouse", "lever", "ashby"):
        m = re.search(r"(?:greenhouse\.io/|lever\.co/|ashbyhq\.com/)([A-Za-z0-9_.-]+)", ident)
        ident = m.group(1) if m else ident
        if not _SLUG.match(ident):
            raise ValidationFailed("Use the company's board token (e.g. 'acme' from boards.greenhouse.io/acme).")
        return ident
    await SafeFetcher().validate_target(ident)
    return ident


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#]+", text.lower()) if t not in _STOP}


def prefilter(listing: NormalizedListing, roles: list[str], locations: list[str], cfg: dict[str, Any]) -> bool:
    """Deterministic pre-LLM filter on title + location (FR-DISC-08)."""
    title = listing.job_title.lower()
    includes = [w.lower() for w in cfg.get("title_include") or []]
    if includes and not any(w in title for w in includes):
        return False
    if roles and not includes:
        title_tokens = _tokens(title) | set(re.findall(r"[a-z]+", title))
        ok = any((toks := _tokens(r)) and toks <= title_tokens for r in roles) or bool(
            title_tokens & {"ai", "ml", "llm", "genai", "backend", "data", "machine", "software", "platform", "python"})
        if not ok:
            return False
    locs = [loc.lower() for loc in (cfg.get("location_include") or locations or [])]
    if locs and listing.location:
        where = listing.location.lower()
        city = (normalize_location(listing.location)["city"] or "").lower()
        if not any(loc.split()[0] in where or loc == city or ("remote" in loc and "remote" in where) for loc in locs):
            return False
    return True


async def ingest_listing(user_id: uuid.UUID, source: CrawlSource, listing: NormalizedListing) -> tuple[str, uuid.UUID | None]:
    """Returns ('new'|'merged', job_id)."""
    body = clean_text("\n".join(filter(None, [f"Role: {listing.job_title}", f"Company: {listing.company}",
                                              listing.location and f"Location: {listing.location}", "", listing.raw_description or ""])))
    digest = description_hash(body)
    company_id = await jobs_svc.upsert_company(listing.company, None)
    canonical = canonical_job_key(listing.job_url)
    loc = normalize_location(listing.location) if listing.location else None
    locations = [loc] if loc and (loc["city"] or loc["remote"]) else []
    work_mode = "remote" if loc and loc["remote"] else "unknown"
    key = ListingKey(canonical_url=canonical, source_name=listing.source_name, source_listing_id=listing.source_listing_id,
                     application_url=canonicalize_url(listing.application_url), description_hash=digest, company_id=company_id,
                     normalized_title=normalize_title(listing.job_title), location_key=location_key(locations, work_mode),
                     posted_at=listing.posted_date)
    now = datetime.now(tz=UTC)
    async with user_session(user_id) as s:
        hit = await jobs_svc.find_db_duplicate(s, user_id, key)
        record = JobSourceRecord(user_id=user_id, crawl_source_id=source.id, source_name=listing.source_name,
                                 source_listing_id=listing.source_listing_id, source_url=listing.job_url, canonical_url=canonical,
                                 application_url=canonicalize_url(listing.application_url), raw_title=listing.job_title,
                                 raw_company=listing.company, raw_location=listing.location, posted_at=listing.posted_date,
                                 collected_at=listing.collected_at, raw_description=body, content_sha256=digest,
                                 metadata_=listing.source_metadata, dedup_signal="new", job_id=uuid.uuid4())
        if hit:
            job_id, signal = hit
            exists = (await s.execute(select(JobSourceRecord.id).where(
                JobSourceRecord.job_id == job_id, JobSourceRecord.source_name == listing.source_name,
                JobSourceRecord.source_listing_id == listing.source_listing_id))).first() if listing.source_listing_id else None
            job = await s.get(Job, job_id)
            job.last_seen_at = now
            job.application_url = job.application_url or listing.application_url
            if not exists:
                record.job_id, record.dedup_signal = job_id, signal
                s.add(record)
            return "merged", job_id
        job = Job(user_id=user_id, company_id=company_id, input_type="discovery", source_url=listing.job_url, canonical_url=canonical,
                  application_url=listing.application_url, title=listing.job_title, normalized_title=normalize_title(listing.job_title),
                  locations=locations, work_mode=work_mode, description_text=body, description_sha256=digest,
                  posted_at=listing.posted_date, posted_at_source="source_api" if listing.posted_date else None,
                  status="queued", last_seen_at=now)
        s.add(job)
        await s.flush()
        record.job_id = job.id
        s.add(record)
        return "new", job.id


async def run_source(user_id: uuid.UUID, source_id: uuid.UUID, agent_run_id: uuid.UUID | None, max_listings: int,
                     fetcher: SafeFetcher | None = None) -> dict[str, Any]:
    fetcher = fetcher or SafeFetcher()
    async with user_session(user_id) as s:
        source = await s.get(CrawlSource, source_id)
        search = (await s.execute(select(SearchConfig).where(SearchConfig.user_id == user_id, SearchConfig.is_active))).scalars().first()
        roles, locations = (list(search.role_filters), list(search.locations)) if search else ([], [])
        run = CrawlRun(user_id=user_id, crawl_source_id=source_id, agent_run_id=agent_run_id, status="running", started_at=datetime.now(tz=UTC))
        s.add(run)
        await s.flush()
        run_id = run.id
        cfg = dict(source.config or {})
        sconf = SourceConfig(identifier=source.identifier, company_name=cfg.get("company_name"),
                             max_listings=min(int(cfg.get("max_listings", max_listings)), max_listings),
                             title_include=cfg.get("title_include") or [], location_include=cfg.get("location_include") or [])
        stype = source.source_type
    stats = {"found": 0, "filtered_out": 0, "new": 0, "merged": 0, "errors": [], "new_job_ids": []}
    status = "completed"
    try:
        listings = await get_adapter(stype, fetcher).discover(sconf)
        stats["found"] = len(listings)
        for listing in listings:
            if not listing.job_title or not prefilter(listing, roles, locations, cfg):
                stats["filtered_out"] += 1
                continue
            try:
                outcome, job_id = await ingest_listing(user_id, source, listing)
                stats[outcome] += 1
                if outcome == "new" and job_id:
                    stats["new_job_ids"].append(str(job_id))
            except Exception as exc:  # one bad listing never sinks the source
                stats["errors"].append({"listing": listing.job_url, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        if stats["errors"]:
            status = "partially_completed"
    except Exception as exc:
        status = "failed"
        stats["errors"].append({"error": f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', str(exc))[:300]}"})
        log.info("source_failed", source_type=stype, error=type(exc).__name__)
    disabled = False
    async with user_session(user_id) as s:
        source = await s.get(CrawlSource, source_id)
        run = await s.get(CrawlRun, run_id)
        run.status, run.completed_at = status, datetime.now(tz=UTC)
        run.listings_found, run.listings_filtered_out = stats["found"], stats["filtered_out"]
        run.listings_new, run.listings_merged = stats["new"], stats["merged"]
        run.errors, run.http_requests = stats["errors"][:50], fetcher.requests_made
        source.last_crawled_at, source.last_status = datetime.now(tz=UTC), status
        source.last_error = stats["errors"][0].get("error") if stats["errors"] and status == "failed" else None
        source.consecutive_failures = source.consecutive_failures + 1 if status == "failed" else 0
        if source.consecutive_failures >= AUTO_DISABLE_AFTER and source.enabled:
            source.enabled, disabled = False, True
        name = source.name
    if disabled:
        await notify(user_id, "source_disabled", f"Source disabled: {name}",
                     f"It failed {AUTO_DISABLE_AFTER} times in a row. Check it in Settings → Sources.", "/settings?tab=sources")
    return {"source_id": str(source_id), "source_type": stype, "status": status, "crawl_run_id": str(run_id), **stats}

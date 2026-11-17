"""Common job-source adapter contract (spec §4.5)."""

from __future__ import annotations

import html as html_lib
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, Field

from app.integrations.fetch import SafeFetcher
from app.integrations.parsing.html import html_to_text


class NormalizedListing(BaseModel):
    source_name: str
    source_listing_id: str | None = None
    job_title: str
    company: str
    location: str | None = None
    job_url: str
    application_url: str | None = None
    posted_date: datetime | None = None
    raw_description: str | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class SourceConfig(BaseModel):
    identifier: str
    company_name: str | None = None
    max_listings: int = 100
    title_include: list[str] = Field(default_factory=list)
    location_include: list[str] = Field(default_factory=list)


class SourceHealth(BaseModel):
    ok: bool
    detail: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class JobSourceAdapter(Protocol):
    source_type: ClassVar[str]
    requires_api_key: ClassVar[bool]
    terms_url: ClassVar[str | None]
    default_rate_limit_per_minute: ClassVar[int]

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]: ...
    async def fetch_details(self, listing: NormalizedListing) -> NormalizedListing: ...
    async def health_check(self, config: SourceConfig) -> SourceHealth: ...


def html_fragment_to_text(fragment: str | None) -> str | None:
    if not fragment:
        return None
    _, text = html_to_text(f"<html><body>{html_lib.unescape(fragment)}</body></html>")
    return text or None


def parse_iso(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class BaseAdapter:
    source_type: ClassVar[str] = "base"
    requires_api_key: ClassVar[bool] = False
    terms_url: ClassVar[str | None] = None
    default_rate_limit_per_minute: ClassVar[int] = 30

    def __init__(self, fetcher: SafeFetcher):
        self.fetcher = fetcher

    async def fetch_details(self, listing: NormalizedListing) -> NormalizedListing:
        return listing

    async def health_check(self, config: SourceConfig) -> SourceHealth:
        try:
            listings = await self.discover(config.model_copy(update={"max_listings": 1}))
            return SourceHealth(ok=True, detail=f"Reachable; {len(listings)} listing(s) sampled.")
        except Exception as exc:  # report, never raise from a health check
            return SourceHealth(ok=False, detail=f"{type(exc).__name__}: {str(exc)[:200]}")

"""Lever public Postings API (documented, no auth): api.lever.co/v0/postings/{company}?mode=json."""

from __future__ import annotations

from urllib.parse import quote

from app.integrations.sources.base import (
    BaseAdapter,
    NormalizedListing,
    SourceConfig,
    html_fragment_to_text,
    parse_iso,
)

API = "https://api.lever.co/v0/postings"
_INTERVAL = {"per-year-salary": "annual", "per-month-salary": "monthly", "per-hour-wage": "hourly"}


class LeverAdapter(BaseAdapter):
    source_type = "lever"
    terms_url = "https://github.com/lever/postings-api"

    def _to_listing(self, p: dict, slug: str, company: str) -> NormalizedListing:
        parts = [p.get("descriptionPlain") or html_fragment_to_text(p.get("description"))]
        for lst in p.get("lists") or []:
            parts.append(lst.get("text", ""))
            parts.append(html_fragment_to_text(lst.get("content")) or "")
        parts.append(p.get("additionalPlain") or html_fragment_to_text(p.get("additional")) or "")
        cats = p.get("categories") or {}
        meta: dict = {"team": cats.get("team"), "commitment": cats.get("commitment"), "workplace_type": p.get("workplaceType")}
        sr = p.get("salaryRange")
        if isinstance(sr, dict) and sr.get("min") is not None:
            meta["salary"] = {"minimum": sr.get("min"), "maximum": sr.get("max"), "currency": sr.get("currency"),
                              "period": _INTERVAL.get(sr.get("interval") or "", "unknown")}
        return NormalizedListing(
            source_name="lever", source_listing_id=p.get("id"), job_title=p.get("text") or "", company=company,
            location=cats.get("location"), job_url=p.get("hostedUrl") or f"https://jobs.lever.co/{slug}/{p.get('id')}",
            application_url=p.get("applyUrl"), posted_date=parse_iso(p.get("createdAt")),
            raw_description="\n".join(x for x in parts if x).strip() or None, source_metadata=meta,
        )

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]:
        slug = config.identifier.strip()
        data = await self.fetcher.get_json(f"{API}/{quote(slug)}?mode=json")
        company = config.company_name or slug.replace("-", " ").title()
        return [self._to_listing(p, slug, company) for p in (data or [])[: config.max_listings]]

    async def get_posting(self, slug: str, posting_id: str, company: str | None = None) -> NormalizedListing:
        p = await self.fetcher.get_json(f"{API}/{quote(slug)}/{quote(posting_id)}?mode=json")
        return self._to_listing(p, slug, company or slug.replace("-", " ").title())

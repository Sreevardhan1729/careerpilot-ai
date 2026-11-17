"""Greenhouse public Job Board API (documented, no auth): boards-api.greenhouse.io/v1/boards/{token}/jobs."""

from __future__ import annotations

from urllib.parse import quote

from app.integrations.sources.base import (
    BaseAdapter,
    NormalizedListing,
    SourceConfig,
    html_fragment_to_text,
    parse_iso,
)

API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseAdapter(BaseAdapter):
    source_type = "greenhouse"
    terms_url = "https://developers.greenhouse.io/job-board.html"

    def _to_listing(self, job: dict, token: str, company: str) -> NormalizedListing:
        departments = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
        return NormalizedListing(
            source_name="greenhouse", source_listing_id=str(job["id"]), job_title=job.get("title") or "",
            company=company, location=(job.get("location") or {}).get("name"),
            job_url=job.get("absolute_url") or f"https://boards.greenhouse.io/{token}/jobs/{job['id']}",
            application_url=job.get("absolute_url"),
            posted_date=parse_iso(job.get("first_published") or job.get("updated_at")),
            raw_description=html_fragment_to_text(job.get("content")),
            source_metadata={"departments": departments, "posted_date_field": "first_published" if job.get("first_published") else "updated_at"},
        )

    async def _company(self, token: str, fallback: str | None) -> str:
        if fallback:
            return fallback
        try:
            meta = await self.fetcher.get_json(f"{API}/{quote(token)}")
            return meta.get("name") or token
        except Exception:
            return token

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]:
        token = config.identifier.strip()
        data = await self.fetcher.get_json(f"{API}/{quote(token)}/jobs?content=true")
        company = await self._company(token, config.company_name)
        return [self._to_listing(j, token, company) for j in (data.get("jobs") or [])[: config.max_listings]]

    async def get_posting(self, token: str, job_id: str, company: str | None = None) -> NormalizedListing:
        job = await self.fetcher.get_json(f"{API}/{quote(token)}/jobs/{quote(job_id)}")
        return self._to_listing(job, token, await self._company(token, company))

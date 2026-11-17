"""Ashby public Job Posting API (documented, no auth): api.ashbyhq.com/posting-api/job-board/{org}."""

from __future__ import annotations

from urllib.parse import quote

from app.core.errors import NotFound
from app.integrations.sources.base import (
    BaseAdapter,
    NormalizedListing,
    SourceConfig,
    html_fragment_to_text,
    parse_iso,
)

API = "https://api.ashbyhq.com/posting-api/job-board"
_INTERVAL = {"1 YEAR": "annual", "1 MONTH": "monthly", "1 HOUR": "hourly"}


class AshbyAdapter(BaseAdapter):
    source_type = "ashby"
    terms_url = "https://developers.ashbyhq.com/docs/public-job-posting-api"

    def _to_listing(self, j: dict, org: str, company: str) -> NormalizedListing:
        meta: dict = {"department": j.get("department"), "team": j.get("team"), "employment_type": j.get("employmentType"),
                      "workplace_type": j.get("workplaceType"), "is_remote": j.get("isRemote")}
        comp = j.get("compensation") or {}
        for c in comp.get("summaryComponents") or []:
            if c.get("compensationType") == "Salary" and c.get("minValue") is not None:
                meta["salary"] = {"minimum": c.get("minValue"), "maximum": c.get("maxValue"), "currency": c.get("currencyCode"),
                                  "period": _INTERVAL.get(str(c.get("interval") or "").upper(), "unknown")}
                break
        if comp.get("compensationTierSummary"):
            meta["compensation_summary"] = comp["compensationTierSummary"]
        location = j.get("location") or ("Remote" if j.get("isRemote") else None)
        return NormalizedListing(
            source_name="ashby", source_listing_id=j.get("id"), job_title=j.get("title") or "", company=company,
            location=location, job_url=j.get("jobUrl") or f"https://jobs.ashbyhq.com/{org}/{j.get('id')}",
            application_url=j.get("applyUrl"), posted_date=parse_iso(j.get("publishedAt")),
            raw_description=j.get("descriptionPlain") or html_fragment_to_text(j.get("descriptionHtml")), source_metadata=meta,
        )

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]:
        org = config.identifier.strip()
        data = await self.fetcher.get_json(f"{API}/{quote(org)}?includeCompensation=true")
        company = config.company_name or org.replace("-", " ").title()
        return [self._to_listing(j, org, company) for j in (data.get("jobs") or [])[: config.max_listings]]

    async def get_posting(self, org: str, posting_id: str, company: str | None = None) -> NormalizedListing:
        for listing in await self.discover(SourceConfig(identifier=org, company_name=company, max_listings=1000)):
            if listing.source_listing_id == posting_id:
                return listing
        raise NotFound("Posting not found on the Ashby board.")

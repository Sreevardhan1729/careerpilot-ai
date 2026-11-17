"""Company career pages: schema.org JobPosting JSON-LD first, then same-site job links (robots, <= 20 pages)."""

from __future__ import annotations

import re

from app.domain.urls import registrable_domain
from app.integrations.parsing.html import extract_jsonld_jobposting, extract_links, html_to_text
from app.integrations.sources.base import BaseAdapter, NormalizedListing, SourceConfig, parse_iso

_JOB_LINK = re.compile(r"/(jobs?|careers?|positions?|openings?|vacanc(y|ies)|roles?)/[^/?#]+", re.I)
MAX_PAGES = 20


class CareerPageAdapter(BaseAdapter):
    source_type = "career_page"

    def _from_jsonld(self, jp: dict, url: str, company: str | None) -> NormalizedListing:
        meta = {"salary": jp["salary"]} if jp.get("salary") else {}
        return NormalizedListing(
            source_name="career_page", source_listing_id=jp.get("identifier") or jp.get("url") or url,
            job_title=jp.get("title") or "", company=jp.get("company") or company or "Unknown", location=jp.get("location"),
            job_url=jp.get("url") or url, application_url=jp.get("url") or url, posted_date=parse_iso(jp.get("date_posted")),
            raw_description=jp.get("description"), source_metadata={**meta, "valid_through": jp.get("valid_through")},
        )

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]:
        res = await self.fetcher.get(config.identifier)
        jp = extract_jsonld_jobposting(res.text, res.url)
        if jp:
            return [self._from_jsonld(jp, res.url, config.company_name)]
        domain = registrable_domain(res.url)
        links = []
        for href, _text in extract_links(res.text, res.url):
            if registrable_domain(href) == domain and _JOB_LINK.search(href) and href not in links and href != res.url:
                links.append(href)
        out: list[NormalizedListing] = []
        for href in links[: min(MAX_PAGES, config.max_listings)]:
            try:
                page = await self.fetcher.get(href)
            except Exception:
                continue
            jp = extract_jsonld_jobposting(page.text, page.url)
            if jp:
                out.append(self._from_jsonld(jp, page.url, config.company_name))
            else:
                title, text = html_to_text(page.text)
                out.append(NormalizedListing(source_name="career_page", source_listing_id=page.url, job_title=title or "",
                                             company=config.company_name or "Unknown", job_url=page.url,
                                             application_url=page.url, raw_description=text))
        return out

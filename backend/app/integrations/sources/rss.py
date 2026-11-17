"""RSS/Atom job feeds (robots.txt applies to the feed host)."""

from __future__ import annotations

import feedparser

from app.integrations.sources.base import (
    BaseAdapter,
    NormalizedListing,
    SourceConfig,
    html_fragment_to_text,
    parse_iso,
)


class RssAdapter(BaseAdapter):
    source_type = "rss"

    async def discover(self, config: SourceConfig) -> list[NormalizedListing]:
        res = await self.fetcher.get(config.identifier)
        feed = feedparser.parse(res.content)
        out = []
        for e in feed.entries[: config.max_listings]:
            link = e.get("link")
            if not link:
                continue
            published = e.get("published") or e.get("updated")
            out.append(NormalizedListing(
                source_name="rss", source_listing_id=e.get("id") or link, job_title=e.get("title") or "",
                company=config.company_name or feed.feed.get("title") or "Unknown", location=None, job_url=link,
                application_url=link, posted_date=parse_iso(published) if published and "T" in str(published) else None,
                raw_description=html_fragment_to_text(e.get("summary") or e.get("description")),
                source_metadata={"published_raw": published},
            ))
        return out

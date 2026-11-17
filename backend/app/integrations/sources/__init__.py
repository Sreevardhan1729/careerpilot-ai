"""Source adapter registry. Wellfound, YC and LinkedIn are intentionally absent (user-provided content only; D9)."""

from __future__ import annotations

from app.integrations.fetch import SafeFetcher
from app.integrations.sources.ashby import AshbyAdapter
from app.integrations.sources.base import BaseAdapter, NormalizedListing, SourceConfig, SourceHealth
from app.integrations.sources.career_page import CareerPageAdapter
from app.integrations.sources.greenhouse import GreenhouseAdapter
from app.integrations.sources.lever import LeverAdapter
from app.integrations.sources.rss import RssAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "ashby": AshbyAdapter,
    "rss": RssAdapter,
    "career_page": CareerPageAdapter,
}


def get_adapter(source_type: str, fetcher: SafeFetcher) -> BaseAdapter:
    try:
        return ADAPTERS[source_type](fetcher)
    except KeyError as exc:
        raise ValueError(f"Unsupported source type: {source_type}") from exc


async def resolve_ats_posting(url: str, fetcher: SafeFetcher) -> NormalizedListing | None:
    """Resolve a Greenhouse/Lever/Ashby posting URL through the board's public API (for analyze-url)."""
    from app.domain.urls import ats_key

    key = ats_key(url)
    if not key:
        return None
    kind, board, posting = key.split(":", 2)
    if kind == "greenhouse":
        return await GreenhouseAdapter(fetcher).get_posting(board, posting)
    if kind == "lever":
        return await LeverAdapter(fetcher).get_posting(board, posting)
    if kind == "ashby":
        return await AshbyAdapter(fetcher).get_posting(board, posting)
    return None


__all__ = ["ADAPTERS", "NormalizedListing", "SourceConfig", "SourceHealth", "get_adapter", "resolve_ats_posting"]

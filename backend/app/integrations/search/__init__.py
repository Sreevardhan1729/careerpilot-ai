"""Optional people-search providers (D10). Disabled (`none`) until SEARCH_PROVIDER and a key are configured.

Only result URL, title and snippet are used; result pages (e.g. LinkedIn profiles) are never fetched.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date

import httpx

from app.core.config import get_settings
from app.core.errors import UpstreamError


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    provider: str


class _Budget:
    def __init__(self) -> None:
        self.day = date.today()
        self.used = 0
        self.lock = threading.Lock()

    def take(self, limit: int) -> bool:
        with self.lock:
            if self.day != date.today():
                self.day, self.used = date.today(), 0
            if self.used >= limit:
                return False
            self.used += 1
            return True


_budget = _Budget()


class SearchProvider:
    name = "none"

    @property
    def enabled(self) -> bool:
        return self.name != "none"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return []


class _HttpProvider(SearchProvider):
    def __init__(self, api_key: str, cse_id: str = ""):
        self.api_key = api_key
        self.cse_id = cse_id

    async def _get(self, url: str, **kw) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(kw.pop("method", "GET"), url, **kw)
        if resp.status_code >= 400:
            raise UpstreamError("Search provider error.", details={"provider": self.name, "status": resp.status_code})
        return resp.json()

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if not _budget.take(get_settings().search_daily_query_budget):
            return []
        return await self._search(query, limit)

    async def _search(self, query: str, limit: int) -> list[SearchResult]:
        raise NotImplementedError


class BraveSearch(_HttpProvider):
    name = "brave"

    async def _search(self, query: str, limit: int) -> list[SearchResult]:
        data = await self._get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": limit},
                               headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        return [SearchResult(r.get("url", ""), r.get("title", ""), r.get("description", ""), self.name)
                for r in (data.get("web") or {}).get("results", [])]


class TavilySearch(_HttpProvider):
    name = "tavily"

    async def _search(self, query: str, limit: int) -> list[SearchResult]:
        data = await self._get("https://api.tavily.com/search", method="POST",
                               json={"api_key": self.api_key, "query": query, "max_results": limit})
        return [SearchResult(r.get("url", ""), r.get("title", ""), r.get("content", ""), self.name) for r in data.get("results", [])]


class GoogleCSE(_HttpProvider):
    name = "google_cse"

    async def _search(self, query: str, limit: int) -> list[SearchResult]:
        data = await self._get("https://www.googleapis.com/customsearch/v1",
                               params={"key": self.api_key, "cx": self.cse_id, "q": query, "num": min(limit, 10)})
        return [SearchResult(r.get("link", ""), r.get("title", ""), r.get("snippet", ""), self.name) for r in data.get("items", [])]


class SerpApi(_HttpProvider):
    name = "serpapi"

    async def _search(self, query: str, limit: int) -> list[SearchResult]:
        data = await self._get("https://serpapi.com/search.json", params={"q": query, "api_key": self.api_key, "num": limit})
        return [SearchResult(r.get("link", ""), r.get("title", ""), r.get("snippet", ""), self.name)
                for r in data.get("organic_results", [])]


_override: SearchProvider | None = None


def set_search_provider(provider: SearchProvider | None) -> None:
    global _override
    _override = provider


def get_search_provider() -> SearchProvider:
    if _override is not None:
        return _override
    s = get_settings()
    key = s.search_api_key.get_secret_value() if s.search_api_key else ""
    if s.search_provider == "none" or not key:
        return SearchProvider()
    return {"brave": BraveSearch, "tavily": TavilySearch, "google_cse": GoogleCSE, "serpapi": SerpApi}[s.search_provider](key, s.search_cse_id)

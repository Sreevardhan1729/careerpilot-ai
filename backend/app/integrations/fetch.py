"""SafeFetcher: the only HTTP client for untrusted URLs (docs/SECURITY.md §6).

- http/https only, ports 80/443, no credentials in URLs
- every resolved IP must be globally routable (blocks private, loopback, link-local/metadata, CGNAT, ULA, mapped)
- connection pinned to the validated IP (SNI/Host preserved) — no DNS-rebinding window
- redirects followed manually (max 5), each hop re-validated
- streamed body cap, content-type allowlist, timeouts
- robots.txt honoured (cached 24h); identifying User-Agent; per-domain pacing
- blocked hosts (LinkedIn etc.) return source_not_permitted
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from protego import Protego

from app.core.config import get_settings
from app.core.errors import FetchFailed, SourceNotPermitted, UnsafeUrl
from app.domain.urls import is_blocked_host

ALLOWED_CONTENT_TYPES = (
    "text/html", "application/xhtml+xml", "application/json", "application/ld+json", "application/xml", "text/xml",
    "application/rss+xml", "application/atom+xml", "text/plain", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
MAX_REDIRECTS = 5
ROBOTS_TTL = 86400

Resolver = Callable[[str], Awaitable[list[str]]]
_TEST_OVERRIDES: dict[str, Any] = {}


def set_test_transport(transport: httpx.AsyncBaseTransport | None, resolver: Resolver | None = None) -> None:
    """Route every SafeFetcher through a mock transport (tests only)."""
    _TEST_OVERRIDES.clear()
    if transport is not None:
        _TEST_OVERRIDES.update({"transport": transport, "resolver": resolver})


async def _system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """IPv4 addresses reachable through IPv6 transition forms (mapped, NAT64, 6to4, Teredo, IPv4-compatible)."""
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if any(ip in net for net in _NAT64) or (int(ip) >> 32) == 0:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    return None


def _ip_is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return embedded.is_global and not embedded.is_multicast
    return ip.is_global and not ip.is_multicast


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import json

        return json.loads(self.content)


class SafeFetcher:
    def __init__(self, resolver: Resolver | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 pin_ips: bool = True, min_interval: float = 2.0):
        s = get_settings()
        if _TEST_OVERRIDES and transport is None:
            transport, resolver = _TEST_OVERRIDES["transport"], resolver or _TEST_OVERRIDES.get("resolver")
            pin_ips, min_interval = False, 0
        self.resolver = resolver or _system_resolver
        self.transport = transport
        self.pin_ips = pin_ips
        self.min_interval = min_interval
        self.timeout = s.fetch_timeout_seconds
        self.max_bytes = s.fetch_max_bytes
        self.user_agent = s.crawler_user_agent
        self.blocked = s.blocked_hosts
        self._robots: dict[str, tuple[Protego | None, float]] = {}
        self._last_hit: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.requests_made = 0

    # ------------------------------------------------------------------ validation
    async def validate_target(self, url: str) -> tuple[str, str]:
        """Return (host, validated_ip) or raise UnsafeUrl / SourceNotPermitted."""
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise UnsafeUrl("Malformed URL.") from exc
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise UnsafeUrl("Only http(s) URLs are allowed.")
        if parts.username or parts.password:
            raise UnsafeUrl("URLs with credentials are not allowed.")
        if parts.port not in (None, 80, 443):
            raise UnsafeUrl("Only standard ports are allowed.")
        if is_blocked_host(url, self.blocked):
            raise SourceNotPermitted(
                "This site requires login or doesn't permit automated access. Paste the text instead.",
                details={"host": parts.hostname, "suggestion": "paste_text"},
            )
        host = parts.hostname.lower()
        try:
            literal = ipaddress.ip_address(host)
            ips = [str(literal)]
        except ValueError:
            try:
                ips = await self.resolver(host)
            except OSError as exc:
                raise FetchFailed("Could not resolve host.", details={"host": host}) from exc
        if not ips or not all(_ip_is_public(ip) for ip in ips):
            raise UnsafeUrl("URL resolves to a non-public address.", details={"host": host})
        return host, ips[0]

    # ------------------------------------------------------------------ low level
    async def _pace(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self.min_interval - (time.monotonic() - self._last_hit.get(host, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()

    async def _single(self, url: str, accept: str) -> httpx.Response | FetchResult:
        host, ip = await self.validate_target(url)
        await self._pace(host)
        parts = urlsplit(url)
        request_url = url
        extensions: dict[str, Any] = {}
        headers = {"User-Agent": self.user_agent, "Accept": accept}
        if self.pin_ips:
            ip_host = f"[{ip}]" if ":" in ip else ip
            netloc = ip_host if parts.port is None else f"{ip_host}:{parts.port}"
            request_url = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
            headers["Host"] = parts.netloc
            extensions["sni_hostname"] = host
        async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout, follow_redirects=False) as client:
            self.requests_made += 1
            req = client.build_request("GET", request_url, headers=headers, extensions=extensions)
            try:
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as exc:
                raise FetchFailed("Request failed.", details={"host": host, "error": type(exc).__name__}) from exc
            try:
                if resp.is_redirect:
                    return resp
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self.max_bytes:
                        raise FetchFailed("Response too large.", details={"limit": self.max_bytes})
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                return FetchResult(url=url, status=resp.status_code, content_type=ctype, content=bytes(body))
            finally:
                await resp.aclose()

    async def _fetch(self, url: str, accept: str = "*/*") -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            result = await self._single(current, accept)
            if isinstance(result, FetchResult):
                return result
            location = result.headers.get("location")
            if not location:
                raise FetchFailed("Redirect without location.")
            current = urljoin(current, location)
        raise FetchFailed("Too many redirects.")

    # ------------------------------------------------------------------ robots
    async def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or cached[1] < time.monotonic():
            parser: Protego | None
            try:
                res = await self._fetch(origin + "/robots.txt", accept="text/plain")
                if res.status >= 500:
                    parser = Protego.parse("User-agent: *\nDisallow: /")
                elif res.status >= 400:
                    parser = None  # no robots.txt → allowed
                else:
                    parser = Protego.parse(res.text)
            except FetchFailed:
                parser = Protego.parse("User-agent: *\nDisallow: /")
            cached = (parser, time.monotonic() + ROBOTS_TTL)
            self._robots[origin] = cached
        parser = cached[0]
        return True if parser is None else parser.can_fetch(url, self.user_agent)

    # ------------------------------------------------------------------ public
    async def get(self, url: str, *, respect_robots: bool = True, allowed_types: tuple[str, ...] = ALLOWED_CONTENT_TYPES,
                  accept: str = "text/html,application/json;q=0.9,*/*;q=0.5") -> FetchResult:
        await self.validate_target(url)
        if respect_robots and not await self.allowed_by_robots(url):
            raise SourceNotPermitted("robots.txt disallows fetching this page.", details={"url": url})
        res = await self._fetch(url, accept)
        if res.status >= 400:
            raise FetchFailed(f"The page returned HTTP {res.status}.", details={"status": res.status})
        if res.content_type and res.content_type not in allowed_types:
            raise FetchFailed("Unsupported content type.", details={"content_type": res.content_type})
        return res

    async def get_json(self, url: str, *, respect_robots: bool = False) -> Any:
        """For documented public JSON APIs (ATS job boards); robots.txt targets crawlers of web pages."""
        res = await self.get(url, respect_robots=respect_robots, allowed_types=("application/json", "text/plain", ""),
                             accept="application/json")
        try:
            return res.json()
        except ValueError as exc:
            raise FetchFailed("Invalid JSON from source.") from exc

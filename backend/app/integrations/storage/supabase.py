"""Supabase Storage via its REST API using the server-side secret key (private bucket)."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from app.core.errors import NotFound, UpstreamError


class SupabaseStorage:
    supports_signed_urls = True

    def __init__(self, base_url: str, secret_key: str, bucket: str):
        self.base = base_url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {"Authorization": f"Bearer {secret_key}", "apikey": secret_key}

    async def _request(self, method: str, path: str, **kw) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, f"{self.base}{path}", headers={**self.headers, **kw.pop("headers", {})}, **kw)
        if resp.status_code == 404 or (resp.status_code == 400 and "not found" in resp.text.lower()):
            raise NotFound("File not found.")
        if resp.status_code >= 400:
            raise UpstreamError("Storage request failed.", details={"status": resp.status_code})
        return resp

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await self._request("POST", f"/object/{self.bucket}/{quote(key)}", content=data,
                            headers={"Content-Type": content_type, "x-upsert": "false"})

    async def get(self, key: str) -> bytes:
        return (await self._request("GET", f"/object/{self.bucket}/{quote(key)}")).content

    async def delete(self, keys: list[str]) -> None:
        if keys:
            await self._request("DELETE", f"/object/{self.bucket}", json={"prefixes": keys})

    async def _list(self, prefix: str) -> list[str]:
        resp = await self._request("POST", f"/object/list/{self.bucket}", json={"prefix": prefix.rstrip("/"), "limit": 1000})
        keys: list[str] = []
        for item in resp.json():
            full = f"{prefix.rstrip('/')}/{item['name']}"
            keys += await self._list(full) if item.get("id") is None else [full]  # id is null for folders
        return keys

    async def delete_prefix(self, prefix: str) -> None:
        keys = await self._list(prefix)
        for i in range(0, len(keys), 100):
            await self.delete(keys[i:i + 100])

    async def signed_url(self, key: str, expires_in: int = 60, download_name: str | None = None) -> str | None:
        resp = await self._request("POST", f"/object/sign/{self.bucket}/{quote(key)}", json={"expiresIn": expires_in})
        signed = resp.json().get("signedURL") or resp.json().get("signedUrl")
        url = f"{self.base}{signed}" if signed and signed.startswith("/") else signed
        if url and download_name:
            url += ("&" if "?" in url else "?") + "download=" + quote(download_name)
        return url

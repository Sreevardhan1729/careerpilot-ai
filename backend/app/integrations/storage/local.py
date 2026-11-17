"""Local filesystem storage for development (private; served only through ownership-checked endpoints)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.core.errors import NotFound


class LocalStorage:
    supports_signed_urls = False

    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise NotFound("Invalid storage key.")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFound("File not found.")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, keys: list[str]) -> None:
        for key in keys:
            path = self._path(key)
            if path.exists():
                await asyncio.to_thread(path.unlink)

    async def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix.rstrip("/"))
        if path.exists():
            await asyncio.to_thread(shutil.rmtree, path)

    async def signed_url(self, key: str, expires_in: int = 60, download_name: str | None = None) -> str | None:
        return None

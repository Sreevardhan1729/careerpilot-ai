"""Text cleaning, normalisation, hashing and chunking (deterministic)."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_ZERO_WIDTH = re.compile(r"[​‌‍⁠﻿]")
_DASHES = re.compile(r"[‐‑‒–—―−]")
_SQUOTES = re.compile(r"[‘’‚‛′]")
_DQUOTES = re.compile(r"[“”„‟″]")
_WS = re.compile(r"[ \t\f\v ]+")
_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH.sub("", text)
    text = _DASHES.sub("-", text)
    text = _SQUOTES.sub("'", text)
    return _DQUOTES.sub('"', text)


def normalize_for_match(text: str) -> str:
    """Lowercase, unify dashes/quotes, collapse all whitespace to single spaces."""
    return re.sub(r"\s+", " ", normalize_unicode(text).lower()).strip()


def clean_text(text: str) -> str:
    """Normalise line endings and spacing; keep line structure (bullets, headings)."""
    text = normalize_unicode(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS.sub(" ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(line)
    return "\n".join(out).strip()


def sha256_hex(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def description_hash(text: str) -> str:
    """Hash of the normalised description (lowercase alphanumerics only, first 20k chars) for dedup."""
    norm = _NON_ALNUM.sub(" ", normalize_for_match(text)).strip()
    return sha256_hex(norm[:20000])


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Split on line boundaries so no chunk exceeds max_chars (hard-splits only over-long single lines)."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        while len(line) > max_chars:
            if current:
                chunks.append("\n".join(current))
                current, size = [], 0
            cut = line.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            chunks.append(line[:cut].strip())
            line = line[cut:].strip()
        extra = len(line) + (1 if current else 0)
        if current and size + extra > max_chars:
            chunks.append("\n".join(current))
            current, size = [], 0
            extra = len(line)
        current.append(line)
        size += extra
    if current and "\n".join(current).strip():
        chunks.append("\n".join(current))
    return [c for c in (c.strip() for c in chunks) if c]


def truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

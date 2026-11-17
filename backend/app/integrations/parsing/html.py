"""Safe HTML → text, and schema.org JobPosting extraction."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.domain.text import clean_text

_DROP = ("script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe", "template", "button")
_BLOCK = ("p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "ul", "ol", "table")
_PERIOD = {"YEAR": "annual", "MONTH": "monthly", "HOUR": "hourly", "WEEK": "unknown", "DAY": "unknown"}


def html_to_text(html: str) -> tuple[str | None, str]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else None
    for tag in soup(_DROP):
        tag.decompose()
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
        li.append("\n")
    for tag in soup.find_all(_BLOCK):
        tag.insert_before("\n")
        tag.append("\n")
    body = soup.body or soup
    text = body.get_text(" ")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    lines = [re.sub(r"^-\s*$", "", ln) for ln in lines]
    return title, clean_text("\n".join(ln for ln in lines if ln))


def _iter_jsonld(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            yield from _iter_jsonld(item)
    elif isinstance(obj, dict):
        if "@graph" in obj:
            yield from _iter_jsonld(obj["@graph"])
        yield obj


def _location(job: dict[str, Any]) -> str | None:
    locs = job.get("jobLocation")
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for loc in locs or []:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        parts = [addr.get("addressLocality"), addr.get("addressRegion") if not addr.get("addressLocality") else None,
                 addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str) else
                 (addr.get("addressCountry") or {}).get("name")]
        joined = ", ".join(p for p in parts if p)
        if joined:
            out.append(joined)
    if job.get("jobLocationType") == "TELECOMMUTE":
        out.append("Remote")
    return "; ".join(out) or None


def _salary(job: dict[str, Any]) -> dict[str, Any] | None:
    base = job.get("baseSalary")
    if not isinstance(base, dict):
        return None
    value = base.get("value")
    if isinstance(value, dict):
        lo, hi, unit = value.get("minValue", value.get("value")), value.get("maxValue", value.get("value")), value.get("unitText")
    else:
        lo = hi = value
        unit = base.get("unitText")
    try:
        lo_f = float(lo) if lo is not None else None
        hi_f = float(hi) if hi is not None else lo_f
    except (TypeError, ValueError):
        return None
    if lo_f is None:
        return None
    as_num = lambda v: int(v) if v is not None and float(v).is_integer() else v  # noqa: E731
    return {"minimum": as_num(lo_f), "maximum": as_num(hi_f), "currency": base.get("currency"),
            "period": _PERIOD.get(str(unit or "").upper(), "unknown")}


def extract_jsonld_jobposting(html: str, base_url: str | None = None) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            types = obj.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" not in types:
                continue
            org = obj.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else org
            desc_html = obj.get("description") or ""
            _, desc = html_to_text(f"<html><body>{desc_html}</body></html>") if desc_html else (None, "")
            identifier = obj.get("identifier")
            ident = identifier.get("value") if isinstance(identifier, dict) else identifier
            url = obj.get("url")
            return {
                "title": obj.get("title"), "company": company, "location": _location(obj),
                "date_posted": obj.get("datePosted"), "valid_through": obj.get("validThrough"),
                "employment_type": obj.get("employmentType"), "description": desc, "salary": _salary(obj),
                "url": urljoin(base_url, url) if base_url and url else url, "identifier": str(ident) if ident else None,
            }
    return None


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        out.append((urljoin(base_url, href), a.get_text(" ", strip=True)[:200]))
    return out

"""URL canonicalisation, ATS job keys, LinkedIn profile normalisation, domains (docs/AGENT_DESIGN.md §9.3)."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {"gh_src", "lever-source", "lever-origin", "ref", "src", "source", "trk", "ccuid", "refid",
                    "trackingid", "fbclid", "gclid", "mc_cid", "mc_eid", "_hsenc", "_hsmi"}
_MULTI_PART_TLDS = {"co.in", "co.uk", "com.au", "co.jp", "com.sg", "com.br", "co.nz", "org.in", "net.in", "ac.in"}
ATS_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com")

_GH = re.compile(r"^(?:boards|job-boards)\.greenhouse\.io$")
_GH_PATH = re.compile(r"^/(?:embed/job_app\?for=)?([^/]+)/jobs/(\d+)")
_LEVER_PATH = re.compile(r"^/([^/]+)/([0-9a-f-]{36})(?:/apply)?/?$", re.IGNORECASE)
_ASHBY_PATH = re.compile(r"^/([^/]+)/([0-9a-f-]{36})(?:/application)?/?$", re.IGNORECASE)
_LINKEDIN_IN = re.compile(r"^/in/([A-Za-z0-9\-_%]+)/?$")


def _split(url: str):
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    return parts


def host_of(url: str) -> str | None:
    parts = _split(url)
    if not parts or not parts.hostname:
        return None
    host = parts.hostname.lower()
    return host[4:] if host.startswith("www.") else host


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return None
    host = host_of(url) or ""
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_PARAMS
    ]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    return urlunsplit(("https" if parts.scheme.lower() in ("http", "https") else parts.scheme, netloc, path,
                       urlencode(sorted(query)), ""))


def ats_key(url: str | None) -> str | None:
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return None
    host = (parts.hostname or "").lower()
    query = dict(parse_qsl(parts.query))
    if _GH.match(host):
        m = _GH_PATH.match(parts.path)
        if m:
            return f"greenhouse:{m.group(1).lower()}:{m.group(2)}"
        if "for" in query and "token" in query:
            return f"greenhouse:{query['for'].lower()}:{query['token']}"
    if "gh_jid" in query and query["gh_jid"].isdigit():
        return f"greenhouse:{(host_of(url) or '').split('.')[0]}:{query['gh_jid']}"
    if host == "jobs.lever.co":
        m = _LEVER_PATH.match(parts.path)
        if m:
            return f"lever:{m.group(1).lower()}:{m.group(2).lower()}"
    if host == "jobs.ashbyhq.com":
        m = _ASHBY_PATH.match(parts.path)
        if m:
            return f"ashby:{m.group(1).lower()}:{m.group(2).lower()}"
    return None


def canonical_job_key(url: str | None) -> str | None:
    """Stable key for dedup: ATS key when recognisable, else the canonical URL."""
    return ats_key(url) or canonicalize_url(url)


def normalize_linkedin_profile(url: str | None) -> str | None:
    if not url:
        return None
    parts = _split(url)
    if parts is None:
        return None
    host = (parts.hostname or "").lower()
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return None
    m = _LINKEDIN_IN.match(parts.path)
    if not m:
        return None
    return f"https://www.linkedin.com/in/{m.group(1).lower()}/"


def registrable_domain(url_or_host: str | None) -> str | None:
    if not url_or_host:
        return None
    host = host_of(url_or_host) if "://" in url_or_host else url_or_host.lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    labels = host.split(".")
    if ".".join(labels[-2:]) in _MULTI_PART_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_ats_host(url_or_host: str | None) -> bool:
    domain = registrable_domain(url_or_host)
    return bool(domain and domain in ATS_HOSTS)


def is_blocked_host(url: str, blocked: list[str]) -> bool:
    host = host_of(url)
    if not host:
        return False
    return any(host == b or host.endswith("." + b) for b in blocked)


# Hosts that carry job posts/links for *other* companies — never a company's own domain.
NON_COMPANY_DOMAINS = {
    "linkedin.com", "lnkd.in", "naukri.com", "indeed.com", "glassdoor.com", "glassdoor.co.in", "monster.com", "foundit.in",
    "instahyre.com", "iimjobs.com", "hirist.com", "hirist.tech", "cutshort.io", "internshala.com", "shine.com", "timesjobs.com",
    "apna.co", "wellfound.com", "angel.co", "ycombinator.com", "workatastartup.com", "google.com", "forms.gle", "goo.gl",
    "bit.ly", "tinyurl.com", "typeform.com", "tally.so", "airtable.com", "notion.site", "notion.so", "office.com",
    "microsoft.com", "myworkdayjobs.com", "workday.com", "smartrecruiters.com", "icims.com", "jobvite.com", "bamboohr.com",
    "recruitee.com", "zohorecruit.com", "zohorecruit.in", "freshteam.com", "keka.com", "darwinbox.in", "darwinbox.com",
    "breezy.hr", "workable.com", "teamtailor.com", "personio.de", "rippling.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "medium.com", "github.com", "youtube.com", "whatsapp.com", "t.me", "telegram.me", "gmail.com",
}
_GENERIC_NAME_WORDS = {"the", "labs", "lab", "technologies", "technology", "tech", "solutions", "systems", "software", "ai",
                       "inc", "group", "global", "india", "private", "limited", "pvt", "ltd", "company", "co", "corp",
                       "corporation", "services", "digital", "consulting", "ventures", "studio", "studios", "hq", "io"}


def company_domain_from_url(company_name: str | None, url: str | None) -> str | None:
    """A company's own registrable domain, only when the URL isn't a job board/form/ATS host and its label matches the
    company name (e.g. 'acme.example' for 'Acme Corp'). Anything else stays unknown rather than guessed."""
    if not company_name or not url:
        return None
    domain = registrable_domain(url)
    if not domain or domain in NON_COMPANY_DOMAINS or is_ats_host(url):
        return None
    label = domain.split(".")[0].replace("-", "")
    words = re.findall(r"[a-z0-9]+", company_name.lower())
    meaningful = [w for w in words if w not in _GENERIC_NAME_WORDS]
    candidates = {"".join(words), "".join(meaningful)} | ({meaningful[0]} if meaningful else set())
    return domain if label in {c for c in candidates if len(c) >= 3} else None

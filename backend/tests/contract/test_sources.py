"""Adapter contract tests against synthetic recorded responses (no live network)."""

import json

import httpx

from app.integrations.fetch import SafeFetcher
from app.integrations.sources import SourceConfig, get_adapter, resolve_ats_posting

GH_JOBS = {"jobs": [{"id": 4012345, "title": "AI Engineer", "updated_at": "2026-11-10T10:00:00-05:00",
                     "first_published": "2026-11-09T09:00:00Z", "location": {"name": "Bengaluru, India"},
                     "absolute_url": "https://boards.greenhouse.io/acme/jobs/4012345",
                     "content": "&lt;p&gt;We need &lt;strong&gt;Python&lt;/strong&gt; and RAG.&lt;/p&gt;",
                     "departments": [{"name": "AI"}]}]}
LEVER = [{"id": "1a2b3c4d-0000-1111-2222-333344445555", "text": "ML Engineer", "createdAt": 1731100000000,
          "hostedUrl": "https://jobs.lever.co/acme/1a2b3c4d-0000-1111-2222-333344445555",
          "applyUrl": "https://jobs.lever.co/acme/1a2b3c4d-0000-1111-2222-333344445555/apply",
          "categories": {"location": "Pune", "team": "ML", "commitment": "Full-time"},
          "descriptionPlain": "Build models.", "lists": [{"text": "Requirements", "content": "<li>PyTorch</li>"}],
          "salaryRange": {"min": 1000000, "max": 1500000, "currency": "INR", "interval": "per-year-salary"}}]
ASHBY = {"jobs": [{"id": "9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd", "title": "Backend Engineer", "location": "Remote",
                   "isRemote": True, "publishedAt": "2026-11-12T00:00:00Z", "employmentType": "FullTime",
                   "jobUrl": "https://jobs.ashbyhq.com/acme/9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd",
                   "descriptionPlain": "FastAPI and PostgreSQL.",
                   "compensation": {"summaryComponents": [{"compensationType": "Salary", "interval": "1 YEAR",
                                                           "currencyCode": "INR", "minValue": 1800000, "maxValue": 2400000}]}}]}
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>Acme Jobs</title>
<item><title>Data Engineer</title><link>https://acme.example/jobs/data-engineer</link><guid>de-1</guid>
<description>Spark and Airflow</description></item></channel></rss>"""
CAREER = """<html><body><a href="/careers/ai-engineer">AI Engineer</a><a href="https://other.com/jobs/x">x</a></body></html>"""
CAREER_JOB = """<html><head><script type="application/ld+json">{"@type":"JobPosting","title":"AI Engineer",
"hiringOrganization":{"name":"Acme"},"datePosted":"2026-11-15","description":"Python, LLMs"}</script></head></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("/robots.txt"):
        return httpx.Response(404)
    routes = {
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true": GH_JOBS,
        "https://boards-api.greenhouse.io/v1/boards/acme": {"name": "Acme Corp"},
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs/4012345": GH_JOBS["jobs"][0],
        "https://api.lever.co/v0/postings/acme?mode=json": LEVER,
        "https://api.lever.co/v0/postings/acme/1a2b3c4d-0000-1111-2222-333344445555?mode=json": LEVER[0],
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true": ASHBY,
    }
    if url in routes:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(routes[url]))
    if url == "https://acme.example/feed.xml":
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=RSS)
    if url == "https://acme.example/careers":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=CAREER)
    if url == "https://acme.example/careers/ai-engineer":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=CAREER_JOB)
    return httpx.Response(500)


def make_fetcher():
    async def resolver(host):
        return ["93.184.216.34"]

    return SafeFetcher(resolver=resolver, transport=httpx.MockTransport(handler), pin_ips=False, min_interval=0)


async def test_greenhouse_normalisation():
    [listing] = await get_adapter("greenhouse", make_fetcher()).discover(SourceConfig(identifier="acme"))
    assert listing.company == "Acme Corp" and listing.source_listing_id == "4012345"
    assert listing.posted_date.isoformat() == "2026-11-09T09:00:00+00:00"
    assert listing.raw_description == "We need Python and RAG."
    assert listing.source_metadata["departments"] == ["AI"]


async def test_lever_normalisation_with_salary():
    [listing] = await get_adapter("lever", make_fetcher()).discover(SourceConfig(identifier="acme"))
    assert listing.job_title == "ML Engineer" and listing.location == "Pune"
    assert "PyTorch" in listing.raw_description
    assert listing.source_metadata["salary"] == {"minimum": 1000000, "maximum": 1500000, "currency": "INR", "period": "annual"}


async def test_ashby_normalisation_with_compensation():
    [listing] = await get_adapter("ashby", make_fetcher()).discover(SourceConfig(identifier="acme", company_name="Acme"))
    assert listing.location == "Remote" and listing.source_metadata["salary"]["minimum"] == 1800000


async def test_rss_and_career_page():
    [r] = await get_adapter("rss", make_fetcher()).discover(SourceConfig(identifier="https://acme.example/feed.xml"))
    assert r.job_title == "Data Engineer" and r.company == "Acme Jobs"
    [c] = await get_adapter("career_page", make_fetcher()).discover(SourceConfig(identifier="https://acme.example/careers"))
    assert c.job_title == "AI Engineer" and c.company == "Acme" and c.raw_description == "Python, LLMs"


async def test_resolve_ats_urls():
    f = make_fetcher()
    gh = await resolve_ats_posting("https://boards.greenhouse.io/acme/jobs/4012345", f)
    assert gh.job_title == "AI Engineer"
    lv = await resolve_ats_posting("https://jobs.lever.co/acme/1a2b3c4d-0000-1111-2222-333344445555/apply", f)
    assert lv.job_title == "ML Engineer"
    assert await resolve_ats_posting("https://example.com/jobs/1", f) is None


async def test_health_check_reports_failure_without_raising():
    health = await get_adapter("greenhouse", make_fetcher()).health_check(SourceConfig(identifier="missing"))
    assert health.ok is False

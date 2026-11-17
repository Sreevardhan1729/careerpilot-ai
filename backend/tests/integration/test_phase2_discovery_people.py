"""Phase 2 acceptance: scheduled run w/o frontend, source isolation, dedup, evidence-backed contacts (AT-07..AT-12)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.fetch import set_test_transport
from app.integrations.search import SearchProvider, SearchResult, set_search_provider
from tests.conftest import make_pdf

DESC = "We need Python, FastAPI and RAG experience to build LLM applications. Requirements: Python, RAG. 0-2 years of experience."
GH = {"jobs": [{"id": 101, "title": "AI Engineer", "first_published": "2026-11-16T09:00:00Z",
                "location": {"name": "Bengaluru, India"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
                "content": DESC}]}
LEVER = [{"id": "1a2b3c4d-0000-1111-2222-333344445555", "text": "ML Engineer", "createdAt": 1763300000000,
          "hostedUrl": "https://jobs.lever.co/acme/1a2b3c4d-0000-1111-2222-333344445555",
          "categories": {"location": "Pune"}, "descriptionPlain": "Build ML models with PyTorch. Requirements: Python, PyTorch."}]
ASHBY = {"jobs": [{"id": "9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd", "title": "Office Manager", "location": "Bengaluru",
                   "jobUrl": "https://jobs.ashbyhq.com/acme/9f9f9f9f-aaaa-bbbb-cccc-dddddddddddd", "descriptionPlain": "Run the office."}]}
CAREER = f"""<html><head><script type="application/ld+json">{json.dumps({"@type": "JobPosting", "title": "AI Engineer",
 "hiringOrganization": {"name": "Acme Corp"}, "datePosted": "2026-11-16",
 "jobLocation": {"address": {"addressLocality": "Bengaluru", "addressCountry": "India"}}, "description": DESC})}</script></head></html>"""
TEAM = """<html><body><h1>Our team</h1>
<div><h3>Meera Iyer</h3><p>Head of AI</p></div>
<div><h3>Arjun Rao</h3><p>Talent Acquisition Lead — write to arjun@acme.example</p></div>
</body></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.endswith("/robots.txt"):
        return httpx.Response(404)
    api = {
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true": GH,
        "https://boards-api.greenhouse.io/v1/boards/acme": {"name": "Acme Corp"},
        "https://api.lever.co/v0/postings/acme?mode=json": LEVER,
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true": ASHBY,
    }
    if url in api:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(api[url]))
    if url == "https://acme.example/careers/ai-engineer":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=CAREER)
    if url == "https://acme.example/":
        return httpx.Response(200, headers={"content-type": "text/html"}, text='<html><body><a href="/team">Team</a></body></html>')
    if url == "https://acme.example/team":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=TEAM)
    return httpx.Response(503)


class FakeSearch(SearchProvider):
    name = "fake"

    async def search(self, query, limit=10):
        return [
            SearchResult("https://in.linkedin.com/in/priya-sharma-acme", "Priya Sharma - Technical Recruiter - Acme Corp | LinkedIn",
                         "Hiring AI engineers in Bengaluru.", "fake"),
            SearchResult("https://www.linkedin.com/in/old-timer", "Old Timer - Former Engineering Manager - Acme Corp | LinkedIn", "x", "fake"),
            SearchResult("https://www.linkedin.com/in/john-doe", "John Doe - Recruiter - OtherCorp | LinkedIn", "x", "fake"),
        ]


@pytest.fixture(autouse=True)
def network():
    async def resolver(host):
        return ["93.184.216.34"]

    set_test_transport(httpx.MockTransport(handler), resolver)
    yield
    set_test_transport(None)
    set_search_provider(None)


async def _add_sources(client, h):
    for body in ({"source_type": "greenhouse", "identifier": "https://boards.greenhouse.io/acme"},
                 {"source_type": "lever", "identifier": "acme", "company_name": "Acme Corp"},
                 {"source_type": "ashby", "identifier": "acme", "company_name": "Acme Corp"},
                 {"source_type": "career_page", "identifier": "https://acme.example/careers/ai-engineer"},
                 {"source_type": "rss", "identifier": "https://broken.example/feed.xml"}):
        r = await client.post("/sources", headers=h, json=body)
        assert r.status_code == 201, r.text


async def test_scheduled_discovery_isolation_and_dedup(client, auth, run_tasks, fixtures_dir):
    h = auth()
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    await run_tasks()
    await _add_sources(client, h)
    sources = (await client.get("/sources", headers=h)).json()
    assert {s["identifier"] for s in sources} >= {"acme", "https://broken.example/feed.xml"}

    r = await client.post("/scheduler/run", headers=h, json={})
    assert r.status_code == 202
    again = await client.post("/scheduler/run", headers=h, json={})
    assert again.status_code == 200 and again.json()["workflow_id"] == r.json()["workflow_id"]  # idempotent per day
    await run_tasks(max_tasks=10)
    run = (await client.get(f"/agent-runs/{r.json()['workflow_id']}", headers=h)).json()
    assert run["status"] == "partially_completed", run  # one broken source, others fine (AT-12)
    assert [p["node"] for p in run["progress"]][:3] == ["discover", "analyze_and_match", "people"]
    assert any(c["workflow_name"] == "job_discovery" for c in run["children"])

    jobs = (await client.get("/jobs", headers=h, params={"sort": "-created_at"})).json()["items"]
    titles = sorted(j["title"] for j in jobs)
    assert titles == ["AI Engineer", "ML Engineer"], titles  # Office Manager filtered; career page merged into GH job
    ai = next(j for j in jobs if j["title"] == "AI Engineer")
    assert set(ai["sources"]) == {"greenhouse", "career_page"}
    assert ai["status"] == "analyzed" and ai["match_score"] is not None
    detail = (await client.get(f"/jobs/{ai['id']}", headers=h)).json()
    signals = {r["source_name"]: r["dedup_signal"] for r in detail["source_records"]}
    # Sources run concurrently: whichever lands first is "new", the other merges into it.
    assert sorted(signals.values())[0] in ("company_title_location", "content_hash") and "new" in signals.values()

    hist = (await client.get("/scheduler/runs", headers=h)).json()
    broken = [c for c in hist["crawl_runs"] if c["status"] == "failed"]
    assert len(broken) == 1 and broken[0]["errors"]
    sources = {s["identifier"]: s for s in (await client.get("/sources", headers=h)).json()}
    assert sources["https://broken.example/feed.xml"]["consecutive_failures"] == 1

    # Re-discovery merges; no duplicate jobs (AT-10)
    d = await client.post("/jobs/discover", headers=h, json={})
    await run_tasks()
    assert (await client.get(f"/agent-runs/{d.json()['workflow_id']}", headers=h)).json()["output"]["new_job_ids"] == []
    assert len((await client.get("/jobs", headers=h)).json()["items"]) == 2


async def test_worker_cli_runs_without_frontend(app, auth, client):
    from app.scheduler.daily import main

    h = auth()
    await client.get("/me", headers=h)  # creates the user + default search config
    code = await main(None, 1, None)
    assert code == 0


async def test_people_discovery_is_evidence_backed(client, auth, run_tasks):
    set_search_provider(FakeSearch())
    h = auth()
    jd = ("Acme Corp is hiring!\nRole: AI Engineer\nLocation: Bengaluru\nRequirements\n- Python and RAG\n"
          "Apply at https://acme.example/careers/ai-engineer")
    a = await client.post("/jobs/analyze", headers=h, json={"text": jd})
    await run_tasks()
    job_id = a.json()["subject"]["id"]
    job = (await client.get(f"/jobs/{job_id}", headers=h)).json()
    assert job["company"]["domain"] == "acme.example"

    r = await client.post(f"/jobs/{job_id}/people/discover", headers=h)
    await run_tasks()
    assert (await client.get(f"/agent-runs/{r.json()['workflow_id']}", headers=h)).json()["status"] == "completed"
    people = (await client.get(f"/jobs/{job_id}/people", headers=h)).json()
    names = {p["name"]: p for p in people["items"]}
    assert set(names) == {"Meera Iyer", "Arjun Rao", "Priya Sharma"}  # former + other-company excluded (AT-07)
    assert 0 < people["verified_count"] <= 15  # AT-08
    for p in people["items"]:
        assert p["evidence"] and all(e["source_url"] for e in p["evidence"])
    assert names["Meera Iyer"]["association_status"] == "verified_current"
    assert names["Meera Iyer"]["role_category"] == "department_head"
    assert names["Priya Sharma"]["association_status"] == "likely_current"
    assert names["Priya Sharma"]["linkedin_url"] == "https://in.linkedin.com/in/priya-sharma-acme/".replace("in.linkedin", "www.linkedin")
    assert names["Arjun Rao"]["public_email"] == "arjun@acme.example"
    assert names["Meera Iyer"]["public_email"] is None and names["Priya Sharma"]["public_email"] is None  # AT-09
    ranks = [p["rank"] for p in people["items"]]
    assert ranks == sorted(ranks)

    manual = await client.post("/people", headers=h, json={"name": "Kiran Das", "designation": "Engineering Manager",
                                                           "linkedin_url": "https://www.linkedin.com/in/kiran-das", "job_id": job_id})
    assert manual.status_code == 201 and manual.json()["association_status"] == "unverified"
    people = (await client.get(f"/jobs/{job_id}/people", headers=h)).json()
    assert "Kiran Das" in {p["name"] for p in people["items"]}
    pid = manual.json()["id"]
    assert (await client.patch(f"/people/{pid}", headers=h, json={"contact_status": "do_not_contact"})).json()["contact_status"] == "do_not_contact"

"""Integration regressions for review findings I-1, I-3, I-4, I-6, I-9, I-10, I-11."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import make_pdf


def _uid(h):
    from app.core.security import verify_token

    return verify_token(h["Authorization"].split()[1]).user_id


async def _job(client, h, run_tasks, text, **extra):
    a = await client.post("/jobs/analyze", headers=h, json={"text": text, **extra})
    await run_tasks()
    return a.json()["subject"]["id"]


# ---------------------------------------------------------------- I-1: a failed/timed-out send never leaves a reusable approval
async def test_timed_out_send_is_not_resendable_with_same_approval(client, auth, run_tasks, fixtures_dir, monkeypatch):
    sent = []

    async def access_token(user_id):
        return "t", "me@example.com"

    async def send_message(token, to, subject, body, sender):
        sent.append(to)  # Gmail accepted it…
        raise httpx.ReadTimeout("read timed out")  # …but the response never arrived

    from app.integrations import gmail
    from app.services import oauth

    monkeypatch.setattr(oauth, "access_token", access_token)
    monkeypatch.setattr(gmail, "send_message", send_message)
    h = auth()
    job_id = await _job(client, h, run_tasks, (fixtures_dir / "jd_ai_engineer.txt").read_text())
    person = (await client.post("/people", headers=h, json={"name": "Priya Sharma", "designation": "Recruiter", "job_id": job_id})).json()
    from app.core.db import user_session
    from app.models import Person

    async with user_session(_uid(h)) as s:
        (await s.get(Person, uuid.UUID(person["id"]))).public_email = "priya@example.ai"
    await client.post("/outreach/generate", headers=h, json={"job_id": job_id, "person_ids": [person["id"]], "message_types": ["recruiter_email"]})
    await run_tasks()
    o = (await client.get("/outreach", headers=h)).json()[0]
    a = (await client.post(f"/outreach/{o['id']}/request-approval", headers=h)).json()
    body = {"approval_id": a["approval_id"], "payload_hash": a["payload_hash"], "confirm": True}
    first = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k"}, json=body)
    assert first.status_code == 502, first.text
    retry = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k"}, json=body)
    assert retry.status_code == 422
    assert len(sent) == 1
    approvals = {x["approval_id"]: x["status"] for x in (await client.get("/approvals", headers=h)).json()}
    assert approvals[a["approval_id"]] == "failed"


# ---------------------------------------------------------------- I-4 + I-3: domains and people validation
async def test_job_board_url_never_becomes_company_domain(client, auth, run_tasks):
    h = auth()
    jd = "Zentrix Labs is hiring!\nRole: AI Engineer\nRequirements\n- Python and RAG experience required"
    job_id = await _job(client, h, run_tasks, jd, source_url="https://www.naukri.com/job-listings-ai-engineer-123")
    job = (await client.get(f"/jobs/{job_id}", headers=h)).json()
    assert job["company"]["name"] == "Zentrix Labs" and job["company"]["domain"] is None
    jd2 = "Zentrix Labs is hiring!\nRole: ML Engineer\nRequirements\n- PyTorch required\nApply at https://forms.gle/abc123"
    job2 = (await client.get(f"/jobs/{await _job(client, h, run_tasks, jd2)}", headers=h)).json()
    assert job2["company"]["domain"] is None


async def test_validate_person_rules(app):
    from datetime import UTC, datetime

    from app.models import Company, PersonEvidence
    from app.schemas.llm.other import ClassifiedPerson
    from app.services.people import validate_person

    company = Company(id=uuid.uuid4(), name="Zentrix Labs", normalized_name="zentrix labs", domain="zentrix.ai")

    def ev(i, snippet, st="search_result", url="https://example.org/x"):
        return PersonEvidence(id=uuid.uuid4(), source_type=st, source_url=url, source_title=None, snippet=snippet,
                              content_sha256=i, retrieved_at=datetime.now(tz=UTC))

    e1 = ev("1", "John Mehta, Talent Partner at Zentrix Labs — write to hr.john@zentrix.ai")
    p = ClassifiedPerson(name="John Mehta", designation="Talent Partner", evidence_ids=["1"], public_email="john@zentrix.ai")
    keep, _ = validate_person(p, {"1": e1}, company)
    assert keep and p.public_email is None  # substring of hr.john@… is not the person's address
    e2 = ev("2", "Jane Doe, former Engineering Manager at Zentrix Labs")
    assert not validate_person(ClassifiedPerson(name="Jane Doe", evidence_ids=["2"]), {"2": e2}, company)[0]
    e3, e4 = ev("3", "Ravi Nair spoke about ML platforms"), ev("4", "Zentrix Labs sponsors the meetup")
    assert not validate_person(ClassifiedPerson(name="Ravi Nair", evidence_ids=["3", "4"]), {"3": e3, "4": e4}, company)[0]
    e5 = ev("5", "Asha Rao, Recruiter at Zentrix Labs. asha@gmail.com")
    p5 = ClassifiedPerson(name="Asha Rao", evidence_ids=["5"], public_email="asha@gmail.com")
    assert validate_person(p5, {"5": e5}, company)[0] and p5.public_email is None  # not on the company domain


# ---------------------------------------------------------------- I-6: resume verification
async def test_verify_parsed_drops_invented_resume_content():
    from app.schemas.llm.resume import ResumeAchievement, ResumeExperience, ResumeParsed, ResumeSkill
    from app.services.resumes import verify_parsed

    text = ("Dev Patel\nSKILLS\nFastAPI, PostgreSQL\nEXPERIENCE\nBackend Intern | Acme | Jan 2024 - Jun 2024\n"
            "- Built FastAPI services backed by PostgreSQL for the billing team\nACHIEVEMENTS\nWon the campus coding contest")
    parsed = ResumeParsed(
        skills=[ResumeSkill(name="FastAPI"), ResumeSkill(name="Kubernetes", section="experience")],
        experience=[ResumeExperience(title="Backend Intern", technologies=["FastAPI", "PostgreSQL", "Kubernetes", "LangGraph", "AWS"],
                                     bullets=["Built FastAPI services backed by PostgreSQL for the billing team, cutting p95 latency by 70% for 2M users"])],
        achievements=[ResumeAchievement(text="Won the campus coding contest and won Best Intern award 2024")],
    )
    out, _ = verify_parsed(parsed, text)
    assert {s.name for s in out.skills} == {"FastAPI"}
    assert out.experience[0].technologies == ["FastAPI", "PostgreSQL"]
    assert out.experience[0].bullets == []
    assert out.achievements == []


# ---------------------------------------------------------------- I-9: discovery keeps user-added people
async def test_find_people_keeps_user_added_contacts(client, auth, run_tasks):
    h = auth()
    job_id = await _job(client, h, run_tasks, "Acme Corp is hiring!\nRole: AI Engineer\nRequirements\n- Python required")
    await client.post("/people", headers=h, json={"name": "Priya Sharma", "designation": "Recruiter", "job_id": job_id})
    await client.post(f"/jobs/{job_id}/people/discover", headers=h)
    await run_tasks()
    names = [p["name"] for p in (await client.get(f"/jobs/{job_id}/people", headers=h)).json()["items"]]
    assert names == ["Priya Sharma"]


# ---------------------------------------------------------------- I-11: resume deletion after an application
async def test_resume_deletable_after_application(client, auth, run_tasks, fixtures_dir):
    h = auth()
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    job_id = await _job(client, h, run_tasks, (fixtures_dir / "jd_ai_engineer.txt").read_text())
    r = await client.post("/applications/prepare", headers=h, json={"job_id": job_id})
    await run_tasks()
    resume_id = (await client.get("/resumes", headers=h)).json()[0]["id"]
    d = await client.delete(f"/resumes/{resume_id}", headers=h)
    assert d.status_code == 200, d.text
    app = (await client.get(f"/applications/{r.json()['subject']['id']}", headers=h)).json()
    assert app["resume_version_id"] is None and app["preview"]["resume_version"]["version_number"] == 1


# ---------------------------------------------------------------- I-10: deletion is final and complete
async def test_deleted_account_cannot_be_recreated_and_files_are_gone(client, auth, run_tasks, fixtures_dir):
    from app.core.config import get_settings

    h = auth()
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    await run_tasks()
    e = await client.post("/account/export", headers=h)
    await run_tasks()
    user_dir = get_settings().local_storage_dir / str(_uid(h))
    assert user_dir.exists()
    assert (await client.request("DELETE", "/account", headers=h, json={"confirm": "DELETE"})).status_code == 200
    assert not user_dir.exists()
    again = await client.get("/me", headers=h)
    assert again.status_code == 403
    from app.core.db import system_session
    from app.models import SearchConfig, User

    async with system_session() as s:
        assert await s.get(User, _uid(h)) is None
        assert (await s.execute(select(SearchConfig).where(SearchConfig.user_id == _uid(h)))).first() is None
    _ = e


@pytest.fixture(autouse=True)
def _no_network():
    from app.integrations.fetch import set_test_transport

    async def resolver(host):
        return ["93.184.216.34"]

    set_test_transport(httpx.MockTransport(lambda r: httpx.Response(404)), resolver)
    yield
    set_test_transport(None)

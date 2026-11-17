"""Phase 3 acceptance: verified-fact drafts, editable, claim checks, nothing sent without approval (AT-14, AT-15)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.conftest import make_pdf


@pytest.fixture
def fake_gmail(monkeypatch):
    sent: list[dict] = []

    async def access_token(user_id):
        return "test-token", "me@example.com"

    async def send_message(token, to, subject, body, sender):
        sent.append({"to": to, "subject": subject, "body": body})
        return f"msg-{len(sent)}"

    async def create_draft(token, to, subject, body, sender):
        return "draft-1"

    from app.integrations import gmail
    from app.services import oauth

    monkeypatch.setattr(oauth, "access_token", access_token)
    monkeypatch.setattr(gmail, "send_message", send_message)
    monkeypatch.setattr(gmail, "create_draft", create_draft)
    return sent


async def _setup(client, h, run_tasks, fixtures_dir):
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    a = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await run_tasks()
    job_id = a.json()["subject"]["id"]
    person = (await client.post("/people", headers=h, json={"name": "Priya Sharma", "designation": "Technical Recruiter",
                                                             "job_id": job_id})).json()
    await client.put("/profile", headers=h, json={"full_name": "Asha Verma"})
    return job_id, person["id"]


async def _verify_email(h, person_id: str, email: str):
    from app.core.db import user_session
    from app.core.security import verify_token
    from app.models import Person

    uid = verify_token(h["Authorization"].split()[1]).user_id
    async with user_session(uid) as s:
        p = await s.get(Person, uuid.UUID(person_id))
        p.public_email = email  # as if discovered verbatim in public evidence


async def test_drafts_use_verified_facts_and_pass_claims(client, auth, run_tasks, fixtures_dir):
    h = auth()
    job_id, person_id = await _setup(client, h, run_tasks, fixtures_dir)
    r = await client.post("/outreach/generate", headers=h, json={"job_id": job_id, "person_ids": [person_id],
                                                                 "message_types": ["linkedin_connection", "referral_request", "recruiter_email",
                                                                                   "hiring_manager_message", "linkedin_follow_up"]})
    assert r.status_code == 202
    await run_tasks()
    drafts = (await client.get("/outreach", headers=h, params={"job_id": job_id})).json()
    types = {d["message_type"] for d in drafts}
    assert types == {"linkedin_connection", "referral_request", "recruiter_email", "hiring_manager_message"}  # follow-up needs history
    for d in drafts:
        assert d["claim_check"]["passed"], d
        assert d["requires_review"] and d["status"] == "draft"
        assert d["recipient_email"] is None  # no verified public email (unknown email stays null)
    conn = next(d for d in drafts if d["message_type"] == "linkedin_connection")
    assert len(conn["body"]) <= 200 and conn["body"].startswith("Hi Priya")
    email = next(d for d in drafts if d["message_type"] == "recruiter_email")
    assert email["personalization_evidence"] and "30%" in email["body"]
    assert "attached" not in email["body"].lower()

    edited = await client.patch(f"/outreach/{email['id']}", headers=h, json={"body": email["body"] + "\nI also scaled systems to 10x traffic."})
    assert edited.json()["status"] == "edited"
    assert not edited.json()["claim_check"]["passed"]
    assert any(v["code"] == "unsupported_metric" for v in edited.json()["claim_check"]["violations"])


async def test_linkedin_is_manual_and_email_needs_verified_recipient(client, auth, run_tasks, fixtures_dir, fake_gmail):
    h = auth()
    job_id, person_id = await _setup(client, h, run_tasks, fixtures_dir)
    await client.post("/outreach/generate", headers=h, json={"job_id": job_id, "person_ids": [person_id],
                                                             "message_types": ["linkedin_connection", "recruiter_email"]})
    await run_tasks()
    drafts = {d["message_type"]: d for d in (await client.get("/outreach", headers=h)).json()}
    r = await client.post(f"/outreach/{drafts['linkedin_connection']['id']}/request-approval", headers=h)
    assert r.status_code == 422 and r.json()["error"]["details"]["reason"] == "manual_channel"
    ms = await client.post(f"/outreach/{drafts['linkedin_connection']['id']}/mark-sent", headers=h)
    assert ms.json()["status"] == "manually_sent"
    r = await client.post(f"/outreach/{drafts['recruiter_email']['id']}/request-approval", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "unverified_recipient"
    assert fake_gmail == []


async def test_send_requires_matching_approval_and_is_idempotent(client, auth, run_tasks, fixtures_dir, fake_gmail):
    h = auth()
    job_id, person_id = await _setup(client, h, run_tasks, fixtures_dir)
    await _verify_email(h, person_id, "priya@example.ai")
    await client.post("/outreach/generate", headers=h, json={"job_id": job_id, "person_ids": [person_id], "message_types": ["recruiter_email"]})
    await run_tasks()
    o = (await client.get("/outreach", headers=h)).json()[0]
    assert o["recipient_email"] == "priya@example.ai"

    a = (await client.post(f"/outreach/{o['id']}/request-approval", headers=h)).json()
    assert a["payload_preview"]["to"] == "priya@example.ai" and a["payload_hash"].startswith("sha256:")
    body = {"approval_id": a["approval_id"], "payload_hash": a["payload_hash"], "confirm": True}

    assert (await client.post(f"/outreach/{o['id']}/approve", headers=h, json=body)).status_code == 422  # no Idempotency-Key
    wrong = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "w"},
                              json={**body, "payload_hash": "sha256:bogus"})
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "approval_mismatch"
    assert (await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "x"},
                              json={**body, "confirm": False})).status_code == 422

    # editing after requesting approval invalidates it
    await client.patch(f"/outreach/{o['id']}", headers=h, json={"subject": "Changed subject"})
    stale = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k-stale"}, json=body)
    assert stale.status_code == 422 and stale.json()["error"]["code"] in ("approval_mismatch", "approval_required")
    assert fake_gmail == []

    a = (await client.post(f"/outreach/{o['id']}/request-approval", headers=h)).json()
    body = {"approval_id": a["approval_id"], "payload_hash": a["payload_hash"], "confirm": True}
    ok = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k1"}, json=body)
    assert ok.status_code == 200 and ok.json()["status"] == "sent", ok.text
    replay = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k1"}, json=body)
    assert replay.json() == ok.json()
    again = await client.post(f"/outreach/{o['id']}/approve", headers={**h, "Idempotency-Key": "k2"}, json=body)
    assert again.status_code == 200 and again.json()["status"] == "sent"
    assert len(fake_gmail) == 1 and fake_gmail[0]["subject"] == "Changed subject"

    approvals = (await client.get("/approvals", headers=h)).json()
    assert {x["status"] for x in approvals} >= {"executed", "expired"}
    from app.core.db import user_session
    from app.core.security import verify_token
    from app.models import AuditEvent

    uid = verify_token(h["Authorization"].split()[1]).user_id
    async with user_session(uid) as s:
        actions = set((await s.execute(select(AuditEvent.action).where(AuditEvent.user_id == uid))).scalars())
    assert {"approval.requested", "approval.decided", "approval.executed", "outreach.sent"} <= actions


async def test_resume_optimisation_keeps_original(client, auth, run_tasks, fixtures_dir):
    h = auth()
    job_id, _ = await _setup(client, h, run_tasks, fixtures_dir)
    resume = (await client.get("/resumes", headers=h)).json()[0]
    before = (await client.get(f"/resumes/{resume['id']}", headers=h)).json()
    r = await client.post(f"/resumes/{resume['id']}/optimize", headers=h, params={"job_id": job_id})
    assert r.status_code == 202
    await run_tasks()
    run = (await client.get(f"/agent-runs/{r.json()['workflow_id']}", headers=h)).json()
    assert run["status"] == "completed"
    imp = run["output"]["improvement"]
    assert imp["method"] == "heuristic" and imp["updated_summary"] is None
    after = (await client.get(f"/resumes/{resume['id']}", headers=h)).json()
    assert after["versions"] == before["versions"] and after["current_version"]["approval_status"] == "original"  # AT-18

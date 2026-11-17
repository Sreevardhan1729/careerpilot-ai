"""Phase 4 (recovery, AT-16) and Phase 5 (applications, AT-17) acceptance, plus account export/delete."""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from sqlalchemy import select, text, update

from tests.conftest import make_pdf


def _uid(h):
    from app.core.security import verify_token

    return verify_token(h["Authorization"].split()[1]).user_id


async def test_failed_run_resumes_from_checkpoint_without_redoing_nodes(client, auth, run_tasks, fixtures_dir, monkeypatch):
    from app import agents
    from app.core.errors import AppError

    real = agents.extract_job
    calls = {"n": 0}

    async def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AppError("simulated crash in extract", code="simulated_crash")  # non-retryable → task fails
        return await real(*a, **kw)

    monkeypatch.setattr(agents, "extract_job", flaky)
    h = auth()
    r = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    run_id = r.json()["workflow_id"]
    await run_tasks()
    run = (await client.get(f"/agent-runs/{run_id}", headers=h)).json()
    assert run["status"] == "failed" and run["error"]["code"] == "simulated_crash"
    assert (await client.post(f"/agent-runs/{run_id}/retry", headers=h)).status_code == 202
    await run_tasks()
    run = (await client.get(f"/agent-runs/{run_id}", headers=h)).json()
    assert run["status"] == "completed", run
    nodes = [p["node"] for p in run["progress"]]
    assert nodes.count("fetch_content") == 1 and nodes.count("dedup_check") == 1  # resumed at extract
    assert (await client.get(f"/jobs/{r.json()['subject']['id']}", headers=h)).json()["status"] == "analyzed"


async def test_expired_lease_is_reclaimed(client, auth, run_tasks, fixtures_dir):
    from app.core.db import system_session
    from app.models import ScheduledTask
    from app.tasks import queue

    h = auth()
    r = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text() + "\nUnique 7"})
    claimed = await queue.claim("dead-worker", 300, [_uid(h)])
    assert claimed is not None
    async with system_session() as s:  # the worker "crashed": its lease runs out
        await s.execute(update(ScheduledTask).where(ScheduledTask.id == claimed.id).values(locked_until=text("now() - interval '1 minute'")))
    await run_tasks()
    assert (await client.get(f"/agent-runs/{r.json()['workflow_id']}", headers=h)).json()["status"] == "completed"


async def _prepared(client, h, run_tasks, fixtures_dir):
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    a = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await run_tasks()
    await client.put("/profile", headers=h, json={"full_name": "Asha Verma", "preferred_email": "asha@example.com"})
    job_id = a.json()["subject"]["id"]
    r = await client.post("/applications/prepare", headers=h, json={"job_id": job_id})
    assert r.status_code == 202, r.text
    await run_tasks()
    return job_id, r.json()["subject"]["id"], r.json()["workflow_id"]


async def test_application_needs_approval_and_evidence(client, auth, run_tasks, fixtures_dir):
    h = auth()
    job_id, app_id, run_id = await _prepared(client, h, run_tasks, fixtures_dir)
    run = (await client.get(f"/agent-runs/{run_id}", headers=h)).json()
    assert run["status"] == "awaiting_approval" and run["approval"]["action_type"] == "submit_application"
    app = (await client.get(f"/applications/{app_id}", headers=h)).json()
    assert app["status"] == "awaiting_approval" and app["resume_version_id"]
    answers = {a["question"]: a for a in app["answers"]}
    assert answers["Full name"]["answer"] == "Asha Verma"
    for q in ("I certify that the information provided is true", "Are you authorised to work in this country?", "Expected salary"):
        assert answers[q]["needs_user_input"] and answers[q]["answer"] is None

    bad = await client.patch(f"/applications/{app_id}", headers=h, json={"status": "applied"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_state_transition"
    from app.core.db import user_session

    async with user_session(_uid(h)) as s:  # the DB itself refuses 'applied' without evidence
        with pytest.raises(Exception, match="applied_needs_evidence"):
            await s.execute(text("UPDATE applications SET status = 'applied' WHERE id = :i"), {"i": uuid.UUID(app_id)})

    appr = run["approval"]
    body = {"approval_id": appr["approval_id"], "payload_hash": appr["payload_hash"], "confirm": True}
    ok = await client.post(f"/applications/{app_id}/approve", headers={**h, "Idempotency-Key": "ap1"}, json=body)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ready_to_submit" and ok.json()["submission_method"] == "manual"
    assert any("Upload resume version 1" in s for s in ok.json()["manual_steps"])
    assert (await client.get(f"/agent-runs/{run_id}", headers=h)).json()["status"] == "completed"
    replay = await client.post(f"/applications/{app_id}/approve", headers={**h, "Idempotency-Key": "ap1"}, json=body)
    assert replay.json() == ok.json()

    done = await client.post(f"/applications/{app_id}/confirm-submission", headers=h,
                             json={"evidence_type": "external_receipt", "detail": "Confirmation email #A-123"})
    assert done.json()["status"] == "applied" and done.json()["confirmation_evidence"]["type"] == "external_receipt"
    dup = await client.post("/applications/prepare", headers=h, json={"job_id": job_id})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"  # never apply twice
    moved = await client.patch(f"/applications/{app_id}", headers=h, json={"status": "interview_scheduled", "follow_up_date": (__import__("datetime").date.today() + __import__("datetime").timedelta(days=3)).isoformat()})
    assert moved.json()["status"] == "interview_scheduled"
    dash = (await client.get("/dashboard/summary", headers=h)).json()
    assert dash["applications_submitted"] == 1 and dash["follow_ups_due"]


async def test_approval_resumes_even_without_checkpoint(client, auth, run_tasks, fixtures_dir):
    """Memory checkpoints vanish on restart; approval must still execute through the same atomic consume."""
    from app.graphs import runtime

    h = auth()
    _job_id, app_id, run_id = await _prepared(client, h, run_tasks, fixtures_dir)
    appr = (await client.get(f"/agent-runs/{run_id}", headers=h)).json()["approval"]
    runtime._memory_saver = runtime.InMemorySaver()  # simulate an API restart
    ok = await client.post(f"/applications/{app_id}/approve", headers={**h, "Idempotency-Key": "x1"},
                           json={"approval_id": appr["approval_id"], "payload_hash": appr["payload_hash"], "confirm": True})
    assert ok.status_code == 200 and ok.json()["status"] == "ready_to_submit"


async def test_account_export_and_delete(client, auth, run_tasks, fixtures_dir):
    h = auth()
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await run_tasks()
    r = await client.post("/account/export", headers=h)
    await run_tasks()
    z = await client.get(f"/account/exports/{r.json()['workflow_id']}", headers=h)
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "data/jobs.json" in names and any(n.startswith("resumes/") and n.endswith(".pdf") for n in names)

    assert (await client.request("DELETE", "/account", headers=h, json={"confirm": "nope"})).status_code == 422
    assert (await client.request("DELETE", "/account", headers=h, json={"confirm": "DELETE"})).status_code == 200
    from app.core.db import system_session
    from app.models import AuditEvent, Job, User

    uid = _uid(h)
    async with system_session() as s:
        assert await s.get(User, uid) is None
        assert (await s.execute(select(Job).where(Job.user_id == uid))).first() is None
        assert (await s.execute(select(AuditEvent).where(AuditEvent.action == "account.deleted"))).first() is not None

"""Tailored resume versions (spec §4.2 versioning, FR-RES-13, AT-18): new DOCX version, original untouched, approval to activate."""

from __future__ import annotations

from tests.conftest import make_pdf

BULLET = "Built a RAG chatbot with LangChain and pgvector that reduced support tickets by 30%"


async def _setup(client, h, run_tasks, fixtures_dir):
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    a = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await run_tasks()
    resume = (await client.get("/resumes", headers=h)).json()[0]
    return resume, a.json()["subject"]["id"]


async def test_tailored_version_needs_approval_and_preserves_original(client, auth, run_tasks, fixtures_dir):
    h = auth()
    resume, job_id = await _setup(client, h, run_tasks, fixtures_dir)
    v1 = resume["current_version_id"]
    body = {"job_id": job_id, "change_summary": "Lead with the RAG work for the AI Engineer role",
            "changes": [{"section": "experience", "before": BULLET,
                         "after": "Reduced support tickets by 30% by building a RAG chatbot with LangChain and pgvector"}],
            "skill_order": ["LangChain", "Python", "FastAPI"]}
    r = await client.post(f"/resumes/{resume['id']}/versions", headers=h, json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    v2 = out["version"]
    assert v2["version_number"] == 2 and v2["parent_version_id"] == v1 and v2["approval_status"] == "pending_approval"
    assert v2["job_id"] == job_id and v2["mime_type"].endswith("wordprocessingml.document")
    detail = (await client.get(f"/resumes/{resume['id']}", headers=h)).json()
    assert detail["current_version_id"] == v1  # not active until approved

    appr = out["approval"]
    bad = await client.post(f"/resumes/{resume['id']}/versions/{v2['id']}/activate", headers={**h, "Idempotency-Key": "a0"},
                            json={"approval_id": appr["approval_id"], "payload_hash": "sha256:nope", "confirm": True})
    assert bad.status_code == 422
    ok = await client.post(f"/resumes/{resume['id']}/versions/{v2['id']}/activate", headers={**h, "Idempotency-Key": "a1"},
                           json={"approval_id": appr["approval_id"], "payload_hash": appr["payload_hash"], "confirm": True})
    assert ok.status_code == 200, ok.text
    detail = (await client.get(f"/resumes/{resume['id']}", headers=h)).json()
    assert detail["current_version_id"] == v2["id"]
    statuses = {v["version_number"]: v["approval_status"] for v in detail["versions"]}
    assert statuses == {1: "original", 2: "approved"}
    assert "Reduced support tickets by 30%" in str(detail["parsed_data"])
    original = await client.get(f"/resumes/{resume['id']}/versions/{v1}/download", headers=h)
    assert original.status_code == 200 and original.content[:5] == b"%PDF-"  # untouched original file
    tailored = await client.get(f"/resumes/{resume['id']}/versions/{v2['id']}/download", headers=h)
    assert tailored.content[:2] == b"PK"


async def test_tailored_version_rejects_invented_content(client, auth, run_tasks, fixtures_dir):
    h = auth()
    resume, job_id = await _setup(client, h, run_tasks, fixtures_dir)
    for change in ({"section": "experience", "before": BULLET, "after": BULLET + " and cut cloud costs by 45%"},
                   {"section": "experience", "before": BULLET, "after": "Ran Kubernetes clusters in production"},
                   {"section": "experience", "before": "Text that is not in the resume", "after": "Anything"}):
        r = await client.post(f"/resumes/{resume['id']}/versions", headers=h, json={"job_id": job_id, "changes": [change]})
        assert r.status_code == 422, (change, r.text)
    bad_order = await client.post(f"/resumes/{resume['id']}/versions", headers=h, json={"skill_order": ["Kubernetes", "Python"]})
    assert bad_order.status_code == 422
    assert len((await client.get(f"/resumes/{resume['id']}", headers=h)).json()["versions"]) == 1


async def test_rejecting_activation_marks_version_rejected(client, auth, run_tasks, fixtures_dir):
    h = auth()
    resume, job_id = await _setup(client, h, run_tasks, fixtures_dir)
    out = (await client.post(f"/resumes/{resume['id']}/versions", headers=h, json={"skill_order": ["Python", "FastAPI"]})).json()
    assert (await client.post(f"/approvals/{out['approval']['approval_id']}/reject", headers=h)).status_code == 200
    versions = {v["version_number"]: v["approval_status"] for v in (await client.get(f"/resumes/{resume['id']}", headers=h)).json()["versions"]}
    assert versions == {1: "original", 2: "rejected"}


async def test_user_written_draft_is_checked_against_the_users_resume(client, auth, run_tasks, fixtures_dir):
    h = auth()
    await _setup(client, h, run_tasks, fixtures_dir)
    d = await client.post("/outreach/drafts", headers=h, json={
        "message_type": "linkedin_connection", "subject": None,
        "body": "Hi Priya, I'm keen on the AI Engineer role. I build RAG apps with LangChain and pgvector."})
    assert d.status_code == 201
    assert d.json()["claim_check"]["passed"], d.json()["claim_check"]

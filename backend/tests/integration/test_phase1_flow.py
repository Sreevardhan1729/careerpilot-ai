"""Phase 1 acceptance (spec §15): upload resumes, paste a JD, extract, rank all resumes, persist across restart."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.conftest import make_docx, make_pdf

RESUME_BACKEND = """Ravi Kumar
Pune, India | ravi@example.com
SUMMARY
Backend engineer building APIs.
SKILLS
Languages: Java, SQL
Frameworks: Spring Boot
EXPERIENCE
Software Engineer | Example Corp | Jan 2024 - Present
- Built REST and Spring Boot services backed by MySQL
PROJECTS
Inventory Service
- Java microservice with MySQL and Docker
EDUCATION
B.E. in Information Technology, Example University, 2023
"""


async def _wait_run(client, headers, run_id, run_tasks):
    await run_tasks()
    r = await client.get(f"/agent-runs/{run_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["db"] == "ok" and r.json()["migration"] == "0004"


async def test_dev_login_and_me(client):
    r = await client.post("/dev/login", json={"email": "owner@example.com"})
    token = r.json()["access_token"]
    me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["llm"]["mode"] == "heuristic"
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Authorization": "Bearer nope"})).json()["error"]["code"] == "unauthorized"


async def test_full_phase1_flow(client, auth, run_tasks, fixtures_dir):
    h = auth()
    asha_pdf = make_pdf((fixtures_dir / "resume_asha.txt").read_text())
    r1 = await client.post("/resumes/upload", headers=h, files={"file": ("asha.pdf", asha_pdf, "application/pdf")})
    assert r1.status_code == 202, r1.text
    r2 = await client.post("/resumes/upload", headers=h, data={"label": "Backend"},
                           files={"file": ("ravi.docx", make_docx(RESUME_BACKEND), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r2.status_code == 202
    run = await _wait_run(client, h, r1.json()["workflow_id"], run_tasks)
    assert run["status"] == "completed", run
    assert [p["node"] for p in run["progress"]] == ["extract_text", "structure", "verify", "persist"]

    resumes = (await client.get("/resumes", headers=h)).json()
    assert len(resumes) == 2 and all(r["status"] in ("parsed", "needs_review") for r in resumes)
    detail = (await client.get(f"/resumes/{r1.json()['subject']['id']}", headers=h)).json()
    skills = {s["name"] for s in detail["parsed_data"]["skills"]}
    assert {"Python", "FastAPI", "LangChain"} <= skills
    assert detail["current_version"]["approval_status"] == "original"
    assert detail["label_suggested"] in ("GenAI / LLM Engineer", "AI Engineer")

    dup = await client.post("/resumes/upload", headers=h, files={"file": ("again.pdf", asha_pdf, "application/pdf")})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate"

    jd = (fixtures_dir / "jd_ai_engineer.txt").read_text()
    a = await client.post("/jobs/analyze", headers={**h, "Idempotency-Key": "k1"}, json={"text": jd})
    assert a.status_code == 202, a.text
    job_id = a.json()["subject"]["id"]
    replay = await client.post("/jobs/analyze", headers={**h, "Idempotency-Key": "k1"}, json={"text": jd})
    assert replay.status_code == 202 and replay.json() == a.json()
    await run_tasks()

    job = (await client.get(f"/jobs/{job_id}", headers=h)).json()
    assert job["status"] == "analyzed" and job["title"] == "AI Engineer"
    assert job["company"]["name"] == "Example AI Technologies"
    assert job["experience"] == {"min_years": 0.0, "max_years": 2.0, "explicit": True, "evidence": "0-2 years"}
    assert job["salary"]["source_type"] == "jd" and job["salary"]["minimum"] == 1200000
    mandatory = {s["name"] for s in job["skills"] if s["importance"] == "mandatory"}
    assert {"Python", "FastAPI", "RAG"} <= mandatory
    assert all(s["evidence_verified"] for s in job["skills"])
    assert job["analysis_method"] == "heuristic"
    assert job["job_score"] is not None and job["priority"] in ("excellent", "strong", "moderate", "low")

    matches = (await client.get(f"/jobs/{job_id}/matches", headers=h)).json()
    assert len(matches["items"]) == 2
    best = matches["items"][0]
    assert best["resume"]["id"] == r1.json()["subject"]["id"], "AI resume should beat the Java backend resume"
    assert best["score"] > matches["items"][1]["score"]
    assert set(best["components"]) == {"K", "P", "E_rel", "R", "D"}
    assert "mandatory skills with strong evidence" in best["components"]["K"]["explanation"]
    assert "not a probability" in matches["disclaimer"]

    again = await client.post("/jobs/analyze", headers=h, json={"text": jd})
    assert again.status_code == 200 and again.json() == {"job_id": job_id, "deduplicated": True}

    listing = (await client.get("/jobs", headers=h, params={"priority": job["priority"]})).json()
    assert [j["id"] for j in listing["items"]] == [job_id]
    assert (await client.get("/jobs", headers=h, params={"skills": "Kubernetes"})).json()["items"] == []

    # Restart persistence (AT-06): drop the engine/pool and read again.
    from app.core.db import dispose_engine

    await dispose_engine()
    assert (await client.get(f"/jobs/{job_id}", headers=h)).json()["job_score"] == job["job_score"]


async def test_linkedin_url_not_fetched_and_post_text_works(client, auth, run_tasks, fixtures_dir):
    h = auth()
    r = await client.post("/jobs/analyze-url", headers=h, json={"url": "https://www.linkedin.com/posts/someone-123"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "source_not_permitted"
    assert r.json()["error"]["details"]["suggestion"] == "paste_text"
    bad = await client.post("/jobs/analyze-url", headers=h, json={"url": "http://127.0.0.1/admin"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "unsafe_url"
    post = (fixtures_dir / "linkedin_post.txt").read_text()
    a = await client.post("/jobs/analyze", headers=h, json={"text": post})
    await run_tasks()
    job = (await client.get(f"/jobs/{a.json()['subject']['id']}", headers=h)).json()
    assert job["salary"]["source_type"] == "not_disclosed" and "Salary" in job["missing_information"]
    assert job["posted_by"]["name"] == "Priya Sharma"


async def test_confirmed_missing_skill_changes_status(client, auth, run_tasks, fixtures_dir):
    h = auth()
    await client.post("/resumes/upload", headers=h, files={"file": ("a.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    a = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await run_tasks()
    job_id = a.json()["subject"]["id"]
    m = (await client.get(f"/jobs/{job_id}/matches", headers=h)).json()["items"][0]
    pinecone = next(b for b in m["skill_breakdown"] if b["skill"] == "Pinecone")
    assert pinecone["status"] == "related"  # sibling of pgvector under "Vector Databases"
    f = await client.post("/profile/facts", headers=h, json={"fact_type": "skill", "data": {"name": "Pinecone", "has_skill": False}})
    assert f.status_code == 201
    await client.post(f"/resumes/match/{job_id}", headers=h)
    await run_tasks()
    m = (await client.get(f"/jobs/{job_id}/matches", headers=h)).json()["items"][0]
    assert next(b for b in m["skill_breakdown"] if b["skill"] == "Pinecone")["status"] == "confirmed_missing"


async def test_user_isolation_api_and_rls(client, auth, run_tasks, fixtures_dir):
    a, b = auth(), auth()
    r = await client.post("/jobs/analyze", headers=a, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text()})
    await client.post("/resumes/upload", headers=a, files={"file": ("x.pdf", make_pdf((fixtures_dir / "resume_asha.txt").read_text()), "application/pdf")})
    await run_tasks()
    job_id = r.json()["subject"]["id"]
    for path in (f"/jobs/{job_id}", f"/jobs/{job_id}/matches", f"/agent-runs/{r.json()['workflow_id']}"):
        assert (await client.get(path, headers=b)).status_code == 404, path
    assert (await client.patch(f"/jobs/{job_id}", headers=b, json={"saved": True})).status_code == 404
    assert (await client.get("/jobs", headers=b)).json()["items"] == []
    assert (await client.get("/resumes", headers=b)).json() == []

    from app.core.db import user_session
    from app.core.security import verify_token

    uid_a = verify_token(a["Authorization"].split()[1]).user_id
    uid_b = verify_token(b["Authorization"].split()[1]).user_id
    owned = ["jobs", "job_skills", "job_evidence", "job_source_records", "resumes", "resume_versions", "resume_chunks",
             "resume_matches", "candidate_profiles", "candidate_profile_facts", "search_configs", "agent_runs"]
    async with user_session(uid_b) as s:
        for table in owned:
            n = (await s.execute(text(f"SELECT count(*) FROM {table} WHERE user_id = :a"), {"a": uid_a})).scalar_one()
            assert n == 0, f"RLS leak on {table}"
        # writes for another user are rejected by WITH CHECK
        try:
            await s.execute(text("INSERT INTO search_configs (id, user_id, name) VALUES (:i, :a, 'x')"), {"i": uuid.uuid4(), "a": uid_a})
            raise AssertionError("RLS allowed a cross-user insert")
        except Exception as exc:
            assert "row-level security" in str(exc).lower()
            await s.rollback()


async def test_every_progress_step_records_completion(client, auth, run_tasks, fixtures_dir):
    h = auth()
    a = await client.post("/jobs/analyze", headers=h, json={"text": (fixtures_dir / "jd_ai_engineer.txt").read_text() + "\nUnique 42"})
    await run_tasks()
    run = (await client.get(f"/agent-runs/{a.json()['workflow_id']}", headers=h)).json()
    assert run["progress"] and all(p["status"] == "completed" and p.get("finished_at") for p in run["progress"]), run["progress"]

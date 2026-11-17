# CareerPilot AI — Implementation Plan

Phase order and acceptance criteria follow spec §15. Estimates are the spec's planning figures for one developer (25–35 days total), not delivery dates. Requirement IDs refer to `PRD.md`.

---

## Status (2026-11-17)

| Phase | Status | Evidence |
|---|---|---|
| 1 Foundation + job & resume intelligence | Done | AT-01–AT-06, AT-13, AT-19 green; real-server smoke run |
| 2 Discovery, ranking, people | Done | AT-07–AT-12 green, including the worker CLI and a mutation check on dedup |
| 3 Outreach, Gmail, optimisation | Done | AT-14, AT-15, AT-18 green; Gmail calls faked in tests |
| 4 LangGraph hardening | Done | AT-16 (checkpoint resume, lease re-claim) green |
| 5 Applications | Done | AT-17 green, including the DB constraint and the no-checkpoint approval path |
| 6 Deployment & hardening | Code done | Dockerfile, entrypoint, CI and daily workflows, export/delete, scripts. **Not deployed:** this needs your Supabase, Render, Vercel, GitHub and (optionally) NVIDIA and Google accounts (§8). |

Backend suite: `cd backend && uv run pytest` → 236 passed. A fresh-context review found 0 Critical and 12 Important issues; all 12, plus 2 Minor issues regraded to Important, are fixed, each with a regression test. Deferred minors are listed in the final report. Eval harness: `uv run python -m evals.run jd_extraction` (synthetic set only so far).

## 0. Working rules (spec §19 "Development process")

- Build one phase at a time. **Phase 1 starts only after these documents are approved.**
- Test-first for every `domain/` module (scoring, dedup, normalisation, evidence, claims). Integration tests use real Postgres and FakeLLM.
- No mock data is ever presented as a real result. Fixtures are labelled `synthetic`.

**End of every phase:**

1. Run all tests and fix failures.
2. Verify the APIs (pytest API tests, plus a manual smoke run).
3. Verify DB persistence across a restart.
4. Update the docs.
5. Report completed functionality, remaining work, risks, and assumptions.

A phase is not done while critical functionality is broken.

---

## 1. Phase overview

| Phase | Scope | Spec acceptance | Est. |
|---|---|---|---|
| 1 | Foundation + job intelligence + resume intelligence | Upload 5 resumes; paste a JD; extract structured requirements; rank all resumes; results survive restart | 7–9 d |
| 2 | Discovery + ranking + people intelligence | Scheduled run with the frontend closed; one source failure doesn't stop others; no duplicate jobs; contacts have evidence links | 7–10 d |
| 3 | Outreach + Gmail drafts + resume optimisation | Drafts use verified facts; unknown emails stay null; drafts editable; nothing sent without approval | 2–3 d |
| 4 | LangGraph hardening | Workflow resumes after interruption; failed nodes retry safely; approval enforced server-side; state persisted | 3–4 d |
| 5 | Application preparation | No duplicate applications; no submission without approval; exact resume version recorded; status backed by evidence | 4–6 d |
| 6 | Deployment + hardening | Prod env configured; no exposed secrets; scheduled execution observable; data user-isolated; recovery documented | 2–3 d |

---

## 2. Phase 1 — Foundation and job intelligence (detailed)

### 2.1 Tasks

Ordered. Each task ends with its tests passing.

| # | Task | Output | Tests |
|---|---|---|---|
| 1.1 | **Scaffold backend:** `uv init`, Python 3.12, deps (fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], psycopg[binary,pool], alembic, pgvector, langgraph, langchain-core, langchain-nvidia-ai-endpoints, httpx, beautifulsoup4, lxml, pymupdf, python-docx, rapidfuzz, dateparser, protego, structlog, pyjwt[crypto], cryptography); dev deps (pytest, pytest-asyncio, respx, hypothesis, ruff, mypy). `requirements.txt` export. | `backend/` skeleton | `pytest` runs (empty) |
| 1.2 | **Scaffold frontend:** Next.js (App Router, TS), Tailwind, shadcn/ui init, TanStack Query, `@supabase/ssr`, Vitest; pnpm. | `frontend/` skeleton | `pnpm build`, `pnpm test` |
| 1.3 | **Repo hygiene:** `.gitignore`, `.env.example`, `ci.yml` (ruff, mypy, pytest + Postgres service, pnpm lint/tsc/test, gitleaks), README quickstart. | CI green | CI run |
| 1.4 | **Core:** settings (fail-fast), structlog with redaction, error envelope + exception handlers, request-ID middleware, CORS, app factory, `GET /health`. | `app/core/*`, `api/v1/health.py` | unit: redaction, settings validation; API: health |
| 1.5 | **DB layer:** async engine, system session, user-scoped session (`SET LOCAL ROLE` + claims), Alembic env. Migration `0001_supabase_compat`. | `core/db.py`, migration | integration: `auth.uid()` returns the set claim |
| 1.6 | **Phase 1 migrations:** users, candidate_profiles, candidate_profile_facts, search_configs, companies, skills, resumes, resume_versions, resume_chunks (HNSW), jobs, job_source_records, job_evidence, job_skills, resume_matches, scheduled_tasks, agent_runs, llm_calls, audit_events, idempotency_keys; `updated_at` trigger; RLS forced + policies + grants. | `alembic/versions/0002…0006` | integration: **RLS isolation harness (AT-19)** per table; `relforcerowsecurity` check |
| 1.7 | **Auth:** JWT verification (JWKS + HS256), allowlist, dev mode with prod guard, `users` upsert, `GET /me`. Frontend: login (magic link), callback, session, API client with bearer. | `core/security.py`, `api/deps.py`, frontend auth | unit: bad iss/aud/exp/alg; API: 401s; dev-mode prod guard |
| 1.8 | **Idempotency + rate limit** dependencies. | `api/deps.py` | API: replay, conflict, 429 |
| 1.9 | **Task queue + runner:** enqueue, claim (`SKIP LOCKED`), lease heartbeat, sweeper, retry/backoff, dead state, registry; `agent_runs` progress; `GET /agent-runs/{id}`, `GET /agent-runs`, `POST /agent-runs/{id}/retry`. | `app/tasks/*` | integration: concurrent claim exclusivity, lease expiry re-queue, retry → dead, idempotency key reuse |
| 1.10 | **LLM layer:** protocol, `NvidiaLLMClient`, `FakeLLMClient`, prompt registry (YAML), structured output (native/prompt modes, reasoning strip, repair once), cache, budget, `llm_calls`. `scripts/check_llm.py`. | `integrations/llm/*`, `prompts/` | unit: rendering, delimiter escaping, repair path, cache hit, budget exhaustion; **manual: `check_llm` against your key** |
| 1.11 | **Embeddings + storage:** NVIDIA embeddings client (passage/query), local + Supabase storage adapters, signed URLs. | `integrations/embeddings`, `integrations/storage` | unit with respx; integration: local storage round-trip |
| 1.12 | **Domain basics (TDD):** text cleaning + hashing + chunking; skills taxonomy YAML (spec §3.3 skills plus the 12 categories, ~300 entries) + normaliser; locations, dates, salary normalisers; URL canonicalisation + ATS keys; evidence verifier. `scripts/seed.py`. | `domain/*`, `data/skills_taxonomy.yaml` | unit + hypothesis: normaliser idempotence, alias collapse, LPA parsing, evidence fuzzy-match bounds |
| 1.13 | **Parsing + fetching:** PDF/DOCX/HTML parsers (page/section metadata, JSON-LD JobPosting); upload validation (magic bytes, zip-bomb, page cap); `SafeFetcher`; Greenhouse/Lever/Ashby single-posting resolvers for `analyze-url`. | `integrations/parsing`, `integrations/fetch.py` | unit: SSRF matrix, redirects, oversize, blocked hosts, `.docm`, encrypted PDF; contract cassettes for ATS resolvers |
| 1.14 | **Profile + search config API:** profile GET/PUT, facts CRUD + confirm/reject, search configs CRUD seeded with spec §3.3 defaults; settings GET/PUT. | `api/v1/profile.py`, `search_configs.py` | API + isolation |
| 1.15 | **Resume ingestion graph** + endpoints (upload, list, detail, patch, parsed-data PUT, download, delete). Prompt `resume_parse@v1`. | `graphs/resume_ingestion.py` | integration with FakeLLM: version 1 immutable, chunks + embeddings stored, suggested facts don't overwrite confirmed; duplicate file → 409 |
| 1.16 | **Job extraction graph** + endpoints (analyze, analyze-url, analyze-file, list with filters, detail, patch). Prompt `jd_extraction@v1`. | `graphs/job_extraction.py` | integration: AT-01, AT-02 (LinkedIn URL → 422), AT-13, dedup (FR-JOB-08), evidence rejection nulls the field |
| 1.17 | **Matching + ranking (TDD):** `domain/matching.py` (K, P, E_rel, R, D, statuses, renormalisation, ties), `domain/ranking.py` (M, F, E_elig, L, S, bands, disqualifiers), `scoring_config.yaml`; resume matching graph; `POST /resumes/match/{job_id}`, `GET /jobs/{id}/matches`. Prompt `resume_match_explain@v1`. | `domain/*`, `graphs/resume_matching.py` | unit: every component edge case, determinism (same input → same output), no synonym double count; integration: AT-04, AT-05 |
| 1.18 | **Frontend pages:** app shell + nav; Dashboard (Phase 1 metrics only); Job Search (list + filters); Analyze dialog (text / URL / file / manual); Job Intelligence page (evidence popovers, provenance badges, match table with component breakdown, missing evidence, disclaimer); Resume Library (upload, parse review/correction, label/default, versions, download); Settings (profile, facts review, preferences, LLM model display). `useAgentRun` progress UI. Only actions that work are rendered. | `frontend/app/*` | Vitest component tests; Playwright smoke: login (dev) → upload → analyse → view matches |
| 1.19 | **Evaluation harness:** `evals/run.py`, `jd_extraction` and `resume_ranking` suites; synthetic fixtures + a private dataset slot. | `backend/evals/` | Run on synthetic set; run on your real JDs once provided |
| 1.20 | **Phase close:** full test run; restart-persistence check (AT-06); docs updated; Phase 1 report. | Report | All AT for Phase 1 green |

### 2.2 Phase 1 exit criteria

- AT-01–AT-06, AT-13, and AT-19 pass.
- `check_llm` passes against the chosen NVIDIA model.
- The `jd_extraction` eval has been run on ≥ 10 real JDs, with results reported (no target enforced yet).
- Spec acceptance, end to end in the UI: 5 resumes uploaded and parsed → a JD pasted → structured requirements with evidence → all 5 resumes ranked with explanations → API restarted → everything still there.

---

## 3. Phase 2 — Discovery, ranking, people intelligence

Order: people discovery first (it completes the manual flow toward M1), then discovery automation.

1. Migrations: people, people_evidence, job_people, crawl_sources, crawl_runs, notifications.
2. Search provider protocol + `none` / `brave` / `tavily` / `google_cse` adapters, with the query budget.
3. People discovery graph (§7 of `AGENT_DESIGN.md`): company-page collection, `posted_by` from extraction, user-provided people (`POST /people`), `people_classify@v1`, `validate_people`, scoring, top-15. Endpoints `/jobs/{id}/people`, `/jobs/{id}/people/discover`, `/people` CRUD. People Discovery page.
4. Source adapters: greenhouse, lever, ashby, rss, career_page (JSON-LD), with contract cassettes and health checks. Sources settings UI.
5. `domain/dedup.py` (TDD: every signal, title-only never merges, merge records kept).
6. Job discovery graph (per-source fan-out with isolated failures) + prefilter + caps.
7. `daily_pipeline` task + `app/scheduler/daily.py` worker + `daily-discovery.yml`. `POST /scheduler/run`, `POST /jobs/discover`, `GET /scheduler/runs`.
8. Ranking for discovered jobs; dashboard complete (new today, bands, scheduler status, failures, LLM budget); notifications + daily digest (`job_recommendation_summary@v1`).
9. Retention step.

**Tests:** AT-07–AT-12. A simulated source outage (respx 500 / timeout) gives `partially_completed`. The worker runs from the CLI against the local DB with the frontend closed.

---

## 4. Phase 3 — Outreach generation

1. Migrations: outreach, approvals, oauth_connections.
2. `domain/claims.py` (TDD with red-team cases).
3. Outreach graph, with prompts `outreach_linkedin@v1` and `outreach_email@v1` (all 7 message types). Endpoints: generate, list, drafts, patch (re-runs the claim check), mark-sent.
4. Google OAuth (state + PKCE, `gmail.compose`, MultiFernet), `POST /outreach/{id}/gmail-draft`, disconnect + revoke.
5. Approval service (request / approve / consume / execute) and the email send executor. `GET /approvals`, `POST /approvals/{id}/reject`.
6. Resume optimisation graph (`resume_improvement@v1`), with the before/after UI.
7. Outreach Center UI: editable previews, copy, approval dialog showing the exact payload, contact history.

**Tests:** AT-14, AT-15, AT-18 (suggestions never alter the original). Gmail calls are mocked in CI. One manual end-to-end draft to your own inbox.

---

## 5. Phase 4 — LangGraph orchestration hardening

1. `AsyncPostgresSaver` in schema `langgraph`, plus thread cleanup in retention and account deletion.
2. Switch the runner to the persistent checkpointer. Resume a run from its last checkpoint after a lease expires.
3. `interrupt()`-based approval gates; the approve endpoint resumes via `Command(resume=…)`.
4. Per-node `RetryPolicy` tuning, a dead-letter view, and a run-history UI (Dashboard → failures → detail → retry).
5. Error monitoring: failure notifications and a structured error taxonomy.

**Tests:** AT-16 (kill the process mid-run, restart, the run completes without duplicate rows). Approval cannot be bypassed by calling the executor directly. Replayed approval is a no-op.

---

## 6. Phase 5 — Application preparation

1. Migrations: applications (unique user+job; `applied` requires evidence), application_events; `resume_versions.approval_id`.
2. Tailored DOCX rendering (python-docx) → draft version → activation approval.
3. Application preparation graph (`application_answers@v1`), with `needs_user_input` for legal or unsupported questions.
4. Endpoints: prepare, list, patch, approve, confirm-submission. Manual-completion checklist (the default for all platforms).
5. Application Tracker UI (Kanban per D13, plus a table view) and follow-up dates on the dashboard.

**Tests:** AT-17, AT-18. A duplicate prepare returns 409. `applied` without evidence is rejected by the DB constraint and by the API.

---

## 7. Phase 6 — Deployment and hardening

1. Supabase project, Render service, Vercel project, GitHub secrets and variables (`DEPLOYMENT.md` §3–§6).
2. Verify the free-tier assumptions (`DEPLOYMENT.md` §8) and record the findings in the docs.
3. Account export and delete (`/account/*`), end to end.
4. Security checklist (`SECURITY.md` §12) in full; bundle secret scan; dependency audit.
5. Failure tests: DB unavailable, LLM 429 storm, source outage, host sleep mid-task. Light load test of the API, using Postman CLI performance runs or a simple script.
6. Post-deploy smoke collection, plus an optional monitor on `/health` (Postman CLI is available locally).
7. Final docs: README quickstart, runbooks verified.

---

## 8. What I need from you, and when

| When | Item | Notes |
|---|---|---|
| Now | **Approval of these documents** (or changes) | Implementation starts after this |
| Start of Phase 1 | OK to run `brew install postgresql@17 pgvector` | Local DB for development and tests (no Docker on this machine) |
| Phase 1, task 1.10 | NVIDIA API key, placed by you in `backend/.env` | I'll run `check_llm` to choose the model ID; don't paste the key in chat |
| Phase 1, task 1.15 | Your 5–10 resumes | Stored in local dev storage only; never committed |
| Phase 1, task 1.19 | 10+ real JDs you care about | Private eval set (gitignored) |
| Phase 1, task 1.7 (or later) | A Supabase project (URL, publishable key, secret key, pooler URL) | Until then, local Postgres + dev auth |
| Phase 2 | Target companies / boards; optional search-provider key | I can look up which companies use Greenhouse, Lever, or Ashby |
| Phase 3 | Google Cloud OAuth client (Testing mode) | Steps in `DEPLOYMENT.md` §7.2 |
| Phase 6 | Render + Vercel accounts; GitHub repo (public or private) | Public repos get free Actions minutes |

---

## 9. Risks and assumptions

| Risk / assumption | Mitigation |
|---|---|
| Nemotron structured-output reliability varies by model | `check_llm` probe; prompt-mode fallback; one repair call; eval before choosing |
| Cosine thresholds (`similarity_scale`) depend on the embedding model | Calibrate on the `resume_ranking` eval; thresholds are versioned config |
| People discovery yields far fewer than 15 without a search provider | Coverage is reported honestly; user-provided URLs; provider optional |
| Free hosts sleep and are memory-limited | Durable leased tasks; daily pipeline on GitHub Actions; no Playwright in the API |
| Free-tier terms change | §8 verification before deploy; every provider sits behind an interface |
| ATS public APIs change shape | Contract tests with cassettes; health checks; per-source isolation |
| LLM quota exhaustion during discovery | Daily budget, pre-filtering, analysis caps, caching, queue-and-wait |
| Resume parsing quality on unusual layouts | `needs_review` status plus a correction UI; corrections re-chunk and re-embed |
| Gmail Testing-mode token expiry | Reconnect notification; drafts are also copyable without Gmail |
| Scope: 25–35 days is a large build | Strict phase gates; M1 (end of Phase 3) is useful on its own |

**Assumptions to confirm:**

- you are the only user (D1);
- Singapore region for Supabase and Render;
- DOCX-only output for tailored resumes;
- English-language JDs;
- INR as the default salary currency for your preferences.

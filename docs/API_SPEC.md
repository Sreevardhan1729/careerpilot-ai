# CareerPilot AI — API Specification

All endpoints live under **`/api/v1`**. FastAPI generates the authoritative OpenAPI document at `/api/v1/openapi.json` from the Pydantic models. This document defines the contract those models implement.

Endpoints marked **(spec)** come from spec §8. Endpoints marked **(added)** are needed by spec §9 (UI) or §12 (security) but were not listed in §8.

---

## 1. Conventions

### 1.1 Authentication

- `Authorization: Bearer <Supabase access token>` on every endpoint except `GET /health` and the Google OAuth callback.
- The token is verified against Supabase JWKS (or the legacy HS256 secret): signature, `exp`, `iss = <SUPABASE_URL>/auth/v1`, `aud = authenticated`.
- `401 unauthorized` if the token is missing or invalid. Another user's resource returns **`404 not_found`**, never `403`, so IDs can't be probed.
- `POST /scheduler/run` also accepts `X-Scheduler-Token` (constant-time compare to `SCHEDULER_TOKEN`) for an external trigger. It runs for the configured owner user.

### 1.2 Request and response

- JSON bodies (UTF-8), except multipart uploads. Timestamps are ISO 8601 UTC (`2026-11-17T02:30:00Z`); the client formats them for display.
- Every response includes `X-Request-ID` (echoed if the client sent one).
- Unknown fields in request bodies are rejected (`extra="forbid"`).

### 1.3 Error envelope

```json
{
  "error": {
    "code": "source_not_permitted",
    "message": "LinkedIn pages can't be fetched. Paste the post text instead.",
    "details": {"host": "www.linkedin.com"},
    "request_id": "8f2c…"
  }
}
```

| HTTP | `code` values |
|---|---|
| 400 | `bad_request`, `unsafe_url` |
| 401 | `unauthorized` |
| 403 | `forbidden` (signed-in account not in `ALLOWED_USER_EMAILS`) |
| 404 | `not_found` |
| 409 | `conflict`, `duplicate`, `idempotency_conflict`, `invalid_state_transition` |
| 413 | `file_too_large` |
| 415 | `unsupported_file_type` |
| 422 | `validation_error` (with `details.fields[]`), `source_not_permitted`, `approval_required`, `approval_mismatch`, `approval_expired`, `integration_not_connected`, `unverified_recipient` |
| 429 | `rate_limited` (with a `Retry-After` header), `llm_quota_exhausted` |
| 502 | `fetch_failed`, `upstream_error` |
| 503 | `llm_unavailable`, `maintenance` |
| 500 | `internal_error` |

### 1.4 Pagination and filtering

- Cursor pagination: `?limit=25&cursor=<opaque>`. The response is `{"items": [...], "next_cursor": "…" | null}`. Max `limit` is 100.
- Sorting: `?sort=-job_score` (prefix `-` for descending). Each list endpoint documents its allowed sort fields.

### 1.5 Idempotency

- Every `POST` that creates work or performs an action accepts an `Idempotency-Key` header (UUID recommended; required on `…/approve`).
- The same key with the same body (hashed) replays the stored response. The same key with a different body returns `409 idempotency_conflict`. Keys expire after 24 h.

### 1.6 Asynchronous operations

Long-running endpoints return **`202 Accepted`**:

```json
{
  "workflow_id": "3c1e…",
  "status": "queued",
  "status_url": "/api/v1/agent-runs/3c1e…",
  "subject": {"type": "job", "id": "a91b…"}
}
```

Clients poll `status_url` (every 2 s recommended) until the status is terminal: `completed`, `partially_completed`, `failed`, or `cancelled`. `awaiting_approval` is a pause, not terminal.

### 1.7 Rate limits (defaults, configurable)

| Bucket | Limit |
|---|---|
| All authenticated requests | 120 / min / user |
| Endpoints that enqueue LLM work | 30 / hour / user |
| Uploads | 20 / hour / user |
| `/scheduler/run`, `/jobs/discover` | 6 / hour / user |
| LLM calls (all sources) | `LLM_DAILY_CALL_BUDGET` / day / user, enforced at task execution |

---

## 2. Endpoint index

| Method | Path | Purpose | Phase | Origin |
|---|---|---|---|---|
| GET | `/health` | Liveness + DB + migration version | 1 | spec |
| POST | `/dev/login` | Local dev sign-in, `{email}` → `{access_token}` (AUTH_MODE=dev only; refused in production) | 1 | added |
| GET | `/me` | Current user + profile completeness + integrations | 1 | added |
| GET / PUT | `/profile` | Candidate profile scalar fields | 1 | added |
| GET | `/profile/facts` | List profile facts (`?fact_type&status`) | 1 | added |
| POST | `/profile/facts` | Add a user-entered fact | 1 | added |
| PATCH / DELETE | `/profile/facts/{id}` | Edit, confirm/reject a suggestion, delete | 1 | added |
| GET / POST | `/search-configs` | List / create search configuration | 1 | added |
| PATCH / DELETE | `/search-configs/{id}` | Edit / delete | 1 | added |
| POST | `/jobs/analyze` | Analyse pasted text or manual fields | 1 | spec |
| POST | `/jobs/analyze-url` | Analyse a permitted public URL | 1 | spec |
| POST | `/jobs/analyze-file` | Analyse a PDF or DOCX job description | 1 | added |
| GET | `/jobs` | List and filter jobs | 1 | spec |
| GET | `/jobs/{id}` | Job detail with skills, evidence, sources, match summary | 1 | spec |
| PATCH | `/jobs/{id}` | Save/unsave, archive, correct extracted fields | 1 | added |
| GET | `/jobs/{id}/matches` | Resume match results for the job | 1 | added |
| POST | `/resumes/upload` | Upload a resume | 1 | spec |
| GET | `/resumes` | List resumes | 1 | spec |
| GET | `/resumes/{id}` | Resume detail with versions and parsed data | 1 | spec |
| PATCH | `/resumes/{id}` | Label, category, default | 1 | added |
| PUT | `/resumes/{id}/versions/{vid}/parsed-data` | Save user corrections to parsed data | 1 | added |
| GET | `/resumes/{id}/versions/{vid}/download` | Short-lived signed download URL | 1 | added |
| DELETE | `/resumes/{id}` | Delete a resume and all its versions | 1 | added |
| POST | `/resumes/match/{job_id}` | (Re-)match all resumes to a job | 1 | spec |
| GET | `/agent-runs/{id}` | Workflow status | 1 | spec |
| GET | `/agent-runs` | List runs (`?status=failed&workflow_name`) | 1 | added |
| POST | `/agent-runs/{id}/retry` | Re-queue a failed or dead run | 1 | added |
| GET | `/dashboard/summary` | Dashboard metrics | 1 (partial), 2+ | spec |
| GET | `/jobs/{id}/people` | Related contacts with evidence | 2 | spec |
| POST | `/jobs/{id}/people/discover` | Run people discovery for a job | 2 | added |
| POST | `/people` | Add a person manually (user-provided URL) | 2 | added |
| GET | `/people` | List people (`?company_id&contact_status`) | 2 | added |
| PATCH | `/people/{id}` | Contact status, notes | 2 | added |
| POST | `/jobs/discover` | Run discovery now for the current user | 2 | spec |
| POST | `/scheduler/run` | Trigger the full daily pipeline (manual rerun) | 2 | spec |
| GET | `/scheduler/runs` | Daily pipeline and crawl run history | 2 | added |
| GET / POST | `/sources` | List / add source configuration | 2 | added |
| PATCH / DELETE | `/sources/{id}` | Enable/disable, limits, delete | 2 | added |
| POST | `/sources/{id}/health-check` | Run the adapter health check | 2 | added |
| POST | `/outreach/generate` | Generate drafts | 3 | spec |
| GET | `/outreach` | List drafts and messages | 3 | added |
| POST | `/outreach/drafts` | Save a new (user-written) draft | 3 | spec |
| PATCH | `/outreach/{id}` | Edit or discard a draft | 3 | added |
| POST | `/outreach/{id}/gmail-draft` | Create a Gmail draft from it (explicit user action) | 3 | added |
| POST | `/outreach/{id}/request-approval` | Create a send approval with a payload preview | 3 | added |
| POST | `/outreach/{id}/approve` | Approve and execute a supported send | 3 | spec |
| POST | `/outreach/{id}/mark-sent` | Record a manual LinkedIn send | 3 | added |
| POST | `/resumes/{id}/optimize` | Generate improvement suggestions for a job | 3 | added |
| GET | `/integrations` | Connected integrations and status | 3 | added |
| GET | `/integrations/google/authorize` | Start Google OAuth (returns the consent URL) | 3 | added |
| GET | `/integrations/google/callback` | OAuth redirect target (state + PKCE) | 3 | added |
| DELETE | `/integrations/google` | Revoke and delete tokens | 3 | added |
| GET | `/approvals` | Pending and past approvals | 3 | added |
| POST | `/approvals/{id}/reject` | Reject a pending approval | 3 | added |
| GET | `/notifications` | List notifications | 2 | added |
| POST | `/notifications/{id}/read` | Mark as read | 2 | added |
| POST | `/applications/prepare` | Prepare an application | 5 | spec |
| GET | `/applications` | List applications (table/kanban) | 5 | spec |
| GET | `/applications/{id}` | Application detail | 5 | added |
| PATCH | `/applications/{id}` | Status change, notes, follow-up date | 5 | added |
| POST | `/applications/{id}/approve` | Approve a supported submission | 5 | spec |
| POST | `/applications/{id}/confirm-submission` | Record manual submission evidence | 5 | added |
| POST | `/resumes/{id}/versions` | Create a tailored draft version from accepted suggestions | 5 | added |
| POST | `/resumes/{id}/versions/{vid}/activate` | Request activation (approval-gated) | 5 | added |
| GET / PUT | `/settings` | Scheduler time, notifications, scoring overrides, LLM display | 1 | added |
| POST | `/account/export` | Build a data export (async) | 6 | added |
| GET | `/account/exports/{run_id}` | Download a finished export ZIP | 6 | added |
| DELETE | `/account` | Delete account and all data (body `{"confirm": "DELETE"}`) | 6 | added |

---

## 3. Key endpoint contracts

Bodies are abbreviated. The full schemas are the Pydantic models in `backend/app/schemas/api/`.

### 3.1 `POST /jobs/analyze`

```json
// request
{
  "input_type": "text",                // "text" | "manual"
  "text": "Paste the full job description here",
  "source_url": null,                  // optional provenance for pasted text (stored, not fetched)
  "company_hint": null,
  "manual_fields": null                // when input_type="manual": {company, job_title, location, …}
}
```

Responses:

- `202` with the async envelope (§1.6) and `subject.type = "job"`.
- `200 {"job_id": "…", "deduplicated": true}` if the same normalised text already exists for this user (FR-JOB-08). No LLM call is made.
- `422 validation_error` if the text is under 40 characters (D18) or over 60,000.

### 3.2 `POST /jobs/analyze-url`

```json
{ "url": "https://boards.greenhouse.io/example/jobs/123" }
```

- `202` async. Recognised ATS URLs (Greenhouse, Lever, Ashby) are resolved through their public APIs. Other URLs go through `SafeFetcher` (robots, SSRF guard).
- `422 source_not_permitted` for blocked hosts (LinkedIn and others), with `details.suggestion = "paste_text"`.
- `400 unsafe_url` for non-http(s) schemes or private addresses. `502 fetch_failed` if fetching fails (status and reason in `details`).

### 3.3 `POST /jobs/analyze-file`

`multipart/form-data`: `file` (PDF or DOCX, ≤ 5 MB), optional `source_url`. Returns `202`, or `413` / `415`.

### 3.4 `GET /jobs`

Query parameters, all optional:

| Param | Meaning |
|---|---|
| `q` | Text search over title + company |
| `role` | Normalised title contains |
| `company_id` | Company |
| `location` | City or "remote" |
| `work_mode` | `remote`, `hybrid`, `onsite`, `unknown` (multi) |
| `experience_max` | Jobs whose minimum ≤ this (unknown included unless `experience_known=true`) |
| `salary_min` | Disclosed max ≥ value (`salary_disclosed=true` to exclude unknown) |
| `source` | `source_name` (multi) |
| `skills` | Canonical skill names (multi; all must be present) |
| `posted_after` | ISO date |
| `min_score` | `job_score` ≥ value |
| `priority` | `excellent`, `strong`, `moderate`, `low` (multi) |
| `status` | Job pipeline status |
| `saved` | `true` / `false` |
| `sort` | `-job_score` (default), `-posted_at`, `-created_at`, `company` |

Item shape:

```json
{
  "id": "…", "title": "AI Engineer", "company": {"id": "…", "name": "Example AI Technologies"},
  "locations": ["Bengaluru, India"], "work_mode": "unknown",
  "experience": {"min_years": 0, "max_years": 2, "explicit": true},
  "salary": {"source_type": "not_disclosed"},
  "job_score": 81.5, "priority": "strong", "match_score": 84.0,
  "best_resume": {"id": "…", "label": "GenAI / LLM Engineer"},
  "posted_at": "2026-11-16T00:00:00Z", "sources": ["greenhouse"],
  "status": "analyzed", "saved": false, "has_application": false
}
```

### 3.5 `GET /jobs/{id}`

Everything in the list item, plus:

- `extraction`: all spec §4.1 fields.
- `skills[]`: `{name, category, importance, evidence_text, evidence_verified, confidence, skill_id}`.
- `evidence[]`: `{field, value, evidence_text, explicit, verified, confidence}`.
- `missing_information[]`.
- `description_text`.
- `source_records[]`: `{source_name, source_url, collected_at, dedup_signal}`.
- `application_url`.
- `job_score_breakdown`: `{components: {M, F, E_elig, L, S}, explanations, disqualifiers[]}`.
- `match_summary`: top 3 resumes with scores.
- `latest_run`: `{workflow_id, status}`.

### 3.6 `GET /jobs/{id}/matches`

```json
{
  "job_id": "…", "scoring_config_version": "2026-11-17.1",
  "best_resume_id": "…",
  "items": [{
    "rank": 1, "resume": {"id": "…", "label": "GenAI / LLM Engineer", "version_number": 1},
    "score": 84.0,
    "components": {
      "K": {"score": 88.0, "weight": 0.35, "explanation": "5 of 6 mandatory skills with strong evidence…", "evidence_refs": ["chunk:…"]},
      "P": {"score": 80.0, "weight": 0.25, "explanation": "…", "evidence_refs": []},
      "E_rel": {"score": 75.0, "weight": 0.15, "explanation": "…"},
      "R": {"score": 82.0, "weight": 0.15, "explanation": "…"},
      "D": {"score": 100.0, "weight": 0.10, "explanation": "…"}
    },
    "mandatory_coverage": 0.83, "preferred_coverage": 0.5,
    "skill_breakdown": [{"skill": "FastAPI", "importance": "mandatory", "status": "listed_only", "evidence_refs": ["chunk:…"]}],
    "missing_skills": [{"skill": "Kubernetes", "importance": "preferred", "status": "no_evidence"}],
    "weakly_highlighted_skills": ["FastAPI"],
    "relevant_projects": [{"ref": "projects[0]", "title": "…", "score": 86}],
    "relevant_experience": [],
    "suggestions": {"summary": "…", "bullet_rewrites": [{"before": "…", "after": "…", "evidence_refs": ["chunk:…"]}]},
    "explanation": "…", "limitations": ["Job does not state work mode."]
  }],
  "disclaimer": "Match scores rank your resumes for this job. They are not a probability of being shortlisted."
}
```

### 3.7 `POST /resumes/upload`

`multipart/form-data`: `file` (PDF or DOCX), optional `label`. Returns `202` with `subject.type = "resume"`, or `413` / `415`. A duplicate file (same SHA-256 as an existing version for this user) returns `409 duplicate` with the existing resume ID.

### 3.8 `GET /resumes/{id}`

Returns:

- `{id, label, label_suggested, category, is_default, status}`;
- `current_version`: `{id, version_number, approval_status, page_count, parsed_data, parse_warnings, created_at}`;
- `versions[]`: `{id, version_number, parent_version_id, change_summary, approval_status, job_id, created_at}`.

### 3.9 `POST /resumes/match/{job_id}`

No body. Returns `202`. If every resume version already has a match for the current scoring config, it returns `200` with the existing results (no LLM call), unless `?force=true`.

### 3.10 `GET /agent-runs/{id}`

```json
{
  "id": "…", "workflow_name": "job_extraction", "status": "running",
  "current_node": "verify_evidence",
  "progress": [
    {"node": "fetch_content", "status": "completed", "started_at": "…", "finished_at": "…"},
    {"node": "llm_extract", "status": "completed", "detail": {"model_id": "…", "prompt_version": "jd_extraction@v1"}},
    {"node": "verify_evidence", "status": "running"}
  ],
  "subject": {"type": "job", "id": "…"},
  "error": null,
  "approval": null,          // when awaiting_approval: {approval_id, action_type, payload_preview}
  "children": [{"id": "…", "workflow_name": "resume_matching", "status": "queued"}]
}
```

### 3.11 `GET /jobs/{id}/people`

```json
{
  "job_id": "…", "company": {"id": "…", "name": "…", "domain": "example.com"},
  "verified_count": 6, "unavailable_count": 9, "target": 15,
  "coverage_note": "No search provider configured; results limited to company pages and the job post.",
  "items": [{
    "rank": 1, "person_id": "…", "name": "…", "designation": "Technical Recruiter",
    "department": "Talent Acquisition", "role_category": "technical_recruiter",
    "linkedin_url": "https://www.linkedin.com/in/…/",
    "public_email": null,
    "association_status": "likely_current",
    "relevance_score": 87.5, "components": {"T": 94, "D": 80, "C": 70, "S": 60},
    "relevance_reason": "…", "confidence": 0.7,
    "evidence": [{"source_type": "search_result", "source_url": "…", "source_title": "…", "snippet": "…", "retrieved_at": "…"}],
    "contact_status": "new", "outreach_count": 0
  }]
}
```

### 3.12 `POST /outreach/generate`

```json
{
  "job_id": "…",
  "person_ids": ["…"],                 // optional; default = top 3 by rank
  "message_types": ["linkedin_connection", "recruiter_email"],
  "resume_id": null                    // default = best match
}
```

Returns `202`. The run output is a list of `outreach` IDs. Drafts are never sent by this endpoint.

### 3.13 `POST /outreach/{id}/request-approval` → `POST /outreach/{id}/approve`

Step 1, `request-approval`. Valid only for `channel=email` with a verified recipient email and an active Google connection. Returns:

```json
{
  "approval_id": "…", "action_type": "send_email", "expires_at": "…",
  "payload_hash": "sha256:…",
  "payload_preview": {"to": "recruiter@example.com", "subject": "…", "body": "…", "attachments": []}
}
```

Step 2, `approve`. Requires the `Idempotency-Key` header.

```json
{ "approval_id": "…", "payload_hash": "sha256:…", "confirm": true }
```

The server recomputes the hash from the current draft:

- If the draft changed: `422 approval_mismatch`.
- If the approval is expired: `422 approval_expired`.
- If it was already executed: the original result is replayed.
- On success: the email is sent via the Gmail API, and the response is `200 {"status": "sent", "gmail_message_id": "…", "sent_at": "…"}`. The approval is marked `executed` and an audit event is written.

For `channel=linkedin`, `approve` returns `422 approval_required` with `details.reason = "manual_channel"`. LinkedIn messages are copied and sent by the user, then recorded with `mark-sent`.

### 3.14 `POST /applications/prepare` → `POST /applications/{id}/approve`

`prepare` takes `{ "job_id": "…", "resume_version_id": null }`. It returns `202`. The run ends `awaiting_approval` with an application preview:

```json
{
  "resume_version": {…},
  "answers": [{"question": "…", "answer": "…", "source_fact_ids": [], "needs_user_input": false}],
  "submission_method": "manual",
  "manual_steps": ["Open application URL", "Upload resume v2", "…"]
}
```

`approve` takes `{approval_id, payload_hash, confirm: true}`:

- With a supported integration, it submits and records the external confirmation.
- Otherwise (the default for every platform in the MVP), it marks the application `ready_to_submit` and returns the manual checklist. The user later calls `confirm-submission` with `{evidence_type: "external_receipt" | "user_attestation", detail}`, which moves the application to `applied`.

A duplicate application for the same job returns `409 duplicate` (FR-APP-02).

### 3.15 `GET /dashboard/summary`

```json
{
  "jobs_total": 214, "jobs_new_today": 12,
  "matches": {"excellent": 3, "strong": 11},
  "people_discovered": 41, "outreach_awaiting_review": 7,
  "applications_submitted": 5, "follow_ups_due": [{"application_id": "…", "date": "2026-11-18"}],
  "scheduler": {"last_run_at": "…", "last_status": "partially_completed", "next_run_at": "…", "failed_sources": 1},
  "latest_jobs": [/* top 10 by job_score posted in last 7 days */],
  "recent_failures": [{"workflow_id": "…", "workflow_name": "…", "error_code": "…", "at": "…"}],
  "llm_budget": {"used_today": 38, "limit": 200}
}
```

`jobs_new_today` uses the user's timezone (default Asia/Kolkata) to define "today".

### 3.16 `POST /scheduler/run` and `POST /jobs/discover`

- `/jobs/discover` takes `{source_ids?: []}` and returns `202`. It runs discovery, extraction, matching, and ranking only.
- `/scheduler/run` takes `{date?: "YYYY-MM-DD"}` and returns `202`. It runs the full daily pipeline (spec §10.1), idempotent per user and date. A second call for the same date returns the existing run (`200`).

### 3.17 `GET /health` (no auth)

```json
{ "status": "ok", "version": "0.1.0", "db": "ok", "migration": "0007_…", "time": "…" }
```

If the database is unreachable, it returns `503 {"status": "degraded", "db": "error"}`.

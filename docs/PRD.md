# CareerPilot AI — Product Requirements

| | |
|---|---|
| Status | Proposed — awaiting approval |
| Version | 1.0 (derived from `SPECIFICATION.md` v1.0, 17 Nov 2026) |
| Source of truth | `docs/SPECIFICATION.md` (unchanged copy of the original). This PRD restates it as numbered, testable requirements and records how ambiguities were resolved. Where they differ, the specification wins unless a decision below says otherwise. |

---

## 1. Purpose

CareerPilot AI is a personal, workflow-oriented job-search system. It turns raw job posts into structured, evidence-backed job profiles; picks the best of the candidate's 5–10 resumes for each job and explains why; finds publicly verifiable people at the hiring company; drafts outreach; discovers new jobs daily; and prepares applications — with a human approval gate in front of every external action.

It is **not** a chatbot. Every result is persisted, attributable to a source, and reproducible.

### 1.1 Users

- **Owner (primary):** one job seeker running their own instance. All MVP flows are designed for this user.
- **Additional users (supported, not targeted):** the system is built multi-user-safe — ownership checks plus Row Level Security — because the spec requires user isolation (§16 "User isolation"). No sharing or team features are planned.

### 1.2 Product principles (spec §1.1)

Referenced elsewhere as P1–P11.

| ID | Principle |
|---|---|
| P1 | Never invent jobs, people, email addresses, salaries, skills, or achievements. |
| P2 | Every important external fact carries source provenance (URL/document, snippet, retrieval time). |
| P3 | Explicitly stated information is stored separately from inferred information. |
| P4 | Scraped pages and job descriptions are untrusted data, never instructions. |
| P5 | No bypassing of logins, CAPTCHAs, paywalls, anti-bot controls, or access restrictions. |
| P6 | Respect source terms, robots directives, rate limits, privacy rules, and law. |
| P7 | No message is sent and no application submitted without explicit user approval. |
| P8 | Parsing, scoring, deduplication, and validation are deterministic code wherever practical. |
| P9 | The LLM does extraction, classification, interpretation, and language generation only. |
| P10 | Original resumes are immutable; every change is a new version. |
| P11 | A match score is a prioritisation heuristic, never presented as a shortlist probability. |

---

## 2. Scope

### 2.1 In scope (by phase — see `IMPLEMENTATION_PLAN.md`)

| Phase | Capability |
|---|---|
| 1 | Foundation, auth, candidate profile, resume upload/parsing, manual JD input (text, URL, PDF, DOCX, manual fields), job extraction, resume matching, job detail UI |
| 2 | Source adapter framework, initial permitted adapters, scheduled discovery, normalisation, deduplication, job ranking, company records, people discovery with provenance |
| 3 | Outreach drafts (all 7 types), Gmail OAuth + draft creation, resume optimisation suggestions, draft review/approval UI |
| 4 | LangGraph hardening: persistent checkpointer, approval interrupts, retry/recovery, run history, error monitoring |
| 5 | Application preparation, tailored resume versions, approval workflow, manual-completion fallback, tracker |
| 6 | Deployment, production hardening, monitoring, security review, documentation |

**Milestone M1** (spec §20 — paste JD → extract → rank resumes → contacts → drafts → save) is complete at the end of Phase 3. Phase 2 discovery is limited to a few configured boards, which satisfies §20's "not at scale until M1 works".

### 2.2 Out of scope (spec §2.2)

Unrestricted crawling; bypassing LinkedIn or other access controls; guessed or unverified emails; unsupervised mass messaging; automatic acceptance of legal declarations; automated submission where a platform prohibits it; shortlist predictions; any assumption of unlimited free-tier capacity.

---

## 3. Functional requirements

Each requirement has an ID used by tests, plans, and code comments. "Spec" gives the governing section.

### 3.1 Candidate profile — FR-PROF (spec §3)

| ID | Requirement |
|---|---|
| FR-PROF-01 | Store every §3.1 field. Phone and work authorisation are optional and never sent to the LLM unless a workflow needs them. |
| FR-PROF-02 | The user can view and edit every field. |
| FR-PROF-03 | List-type facts (education, projects, experience, certifications, achievements, skills) are stored as individual facts with `source ∈ {user_entered, resume_derived, inferred}` and `status ∈ {confirmed, suggested, rejected}`. |
| FR-PROF-04 | Resume parsing produces `suggested` facts only; it never overwrites a `confirmed` fact. |
| FR-PROF-05 | The user can mark a skill as "I do not have this", which is the only way a skill becomes a *confirmed missing* skill (see D4). |
| FR-PROF-06 | Initial search preferences are seeded from spec §3.3 and are fully editable (roles, experience bands, locations, skills, work modes). |
| FR-PROF-07 | The user can export all of their data (JSON plus original files) and delete their account and all of their data. |

### 3.2 Job intelligence — FR-JOB (spec §4.1)

| ID | Requirement |
|---|---|
| FR-JOB-01 | Accept pasted text (LinkedIn post or JD), a public job URL, a career-page URL, a PDF, a DOCX, or manually entered fields. |
| FR-JOB-02 | URLs are fetched only through the safe fetcher (robots-aware, SSRF-guarded, rate-limited). LinkedIn and other login-walled hosts are never fetched; the user is asked to paste the text instead. |
| FR-JOB-03 | The original input text and source URL are preserved for audit. Full raw HTML is never stored. |
| FR-JOB-04 | Extraction returns every field in spec §4.1 "Required extracted fields", validated by a Pydantic schema. |
| FR-JOB-05 | Each extracted skill has a name, one of 12 taxonomy categories, an importance (`mandatory`/`preferred`/`mentioned`), an evidence snippet, a confidence, and a normalised skill ID where the taxonomy has one. |
| FR-JOB-06 | Important fields (experience, salary, location, work mode, mandatory skills, deadline) have evidence snippets that are **verified deterministically to occur in the source text**. A field whose evidence fails verification is nulled and listed in `missing_information`. |
| FR-JOB-07 | Experience years are never inferred. Salary is `not_disclosed` unless evidence supports it. Unknown values are `null` or `not_disclosed`, never guessed. |
| FR-JOB-08 | Re-submitting identical content (same normalised-text hash or canonical URL) returns the existing job instead of re-running the LLM. |
| FR-JOB-09 | Analysis runs asynchronously: the API returns `202` with a workflow ID, and progress can be polled. |

### 3.3 Resume intelligence — FR-RES (spec §4.2)

| ID | Requirement |
|---|---|
| FR-RES-01 | Upload PDF or DOCX, up to 5 MB and 20 pages each (configurable). Validated by magic bytes, not just extension. |
| FR-RES-02 | The original file goes to private object storage and is never modified. It becomes version 1 with `approval_status = original`. |
| FR-RES-03 | Text extraction uses PyMuPDF / python-docx and keeps page and section boundaries. Sections: summary, skills, experience, education, projects, certifications, achievements. |
| FR-RES-04 | Structured resume data (technologies normalised to the taxonomy) is produced and shown to the user, who can correct it. Corrections are stored without touching the original file. |
| FR-RES-05 | Content is chunked by section, embedded, and stored in pgvector. |
| FR-RES-06 | A label (e.g. "GenAI / LLM Engineer") is suggested from the content and is editable. One resume can be set as the default. |
| FR-RES-07 | Matching compares **every** parsed resume against the job using `Match = 0.35K + 0.25P + 0.15E_rel + 0.15R + 0.10D`, each component 0–100 and computed deterministically (algorithm in `AGENT_DESIGN.md` §5). |
| FR-RES-08 | Matching distinguishes, per skill: strong evidence, listed-only (weakly highlighted), present in profile but missing from this resume, no evidence, and confirmed missing. |
| FR-RES-09 | Synonyms are collapsed to one canonical skill before scoring, so nothing is double-counted. Mandatory skills outweigh preferred ones. |
| FR-RES-10 | The output contains every field in spec §4.2 "Resume matching output". Each component has a templated explanation that cites evidence. |
| FR-RES-11 | Same inputs plus the same scoring-config version give the same scores. The config version is stored with every match. |
| FR-RES-12 | Optimisation suggestions (summary, bullets, skill order, section order, supported vs missing keywords, before/after) never add unsupported skills, metrics, responsibilities, or experience. Suggestions that fail claim validation are dropped and reported. |
| FR-RES-13 | An approved change creates a new resume version (all spec §4.2 version fields). Making a materially changed version the active one requires approval. |

### 3.4 People intelligence — FR-PPL (spec §4.3)

| ID | Requirement |
|---|---|
| FR-PPL-01 | Target up to 15 people per job, in the spec's 15-level priority order. Return fewer when fewer can be verified. |
| FR-PPL-02 | Evidence is gathered **first** by retrieval tools (company pages, configured search provider, the job post, user-provided URLs). The LLM only classifies and ranks gathered evidence. |
| FR-PPL-03 | Every person cites ≥ 1 evidence item. Their name must appear in the cited evidence, and the company association must be supported by it. Otherwise the person is discarded. |
| FR-PPL-04 | An email is stored only if that exact address appears in retrieved evidence. Pattern-based guessing is never done, and the field is otherwise `null`. |
| FR-PPL-05 | Association status is one of `verified_current`, `likely_current`, `unverified`. Only `verified_current` is displayed as "current". |
| FR-PPL-06 | `People Score = 0.35T + 0.30D + 0.20C + 0.15S` is computed deterministically from classified attributes. |
| FR-PPL-07 | Duplicates are merged by normalised LinkedIn URL, else by normalised name + company. |
| FR-PPL-08 | LinkedIn pages are never fetched. LinkedIn URLs come only from search-provider results or the user. |
| FR-PPL-09 | The user can add a person manually (name, URL, notes) and set a contact status, including `do_not_contact`. |

### 3.5 Outreach — FR-OUT (spec §4.4)

| ID | Requirement |
|---|---|
| FR-OUT-01 | Generate the 7 message types in spec §4.4 with every listed output field. |
| FR-OUT-02 | Personalisation uses only verified facts: confirmed profile facts, resume evidence, job data, and person evidence. The facts used are stored as `personalization_evidence`. |
| FR-OUT-03 | A deterministic claim check rejects drafts that: contain a metric not present in the evidence; mention a skill the candidate has no evidence for; claim familiarity, a referral, or a prior meeting with no recorded relationship; use an email not verified for the recipient; or claim an attachment that won't be attached. |
| FR-OUT-04 | LinkedIn connection notes respect a configurable character limit (default 200). |
| FR-OUT-05 | Every output is a draft with `requires_review = true`. The user can edit, copy, discard, or approve it. |
| FR-OUT-06 | Gmail: OAuth with the `gmail.compose` scope; tokens encrypted at rest and kept server-side. Creating a Gmail draft is an explicit user action. Sending is a separate, approval-gated action. |
| FR-OUT-07 | LinkedIn messages are sent manually by the user, who marks them `manually_sent`. |

### 3.6 Automated discovery — FR-DISC (spec §4.5, §10)

| ID | Requirement |
|---|---|
| FR-DISC-01 | Every source implements one adapter contract (`discover`, `fetch_details`, `health_check`). New sources need no orchestration changes. |
| FR-DISC-02 | Initial adapters: Greenhouse, Lever, and Ashby public job-board APIs; RSS; career pages exposing schema.org `JobPosting`; user-provided URLs (see D9). |
| FR-DISC-03 | A normalised listing has every field in spec §4.5. |
| FR-DISC-04 | Deduplication uses, in order: canonical URL, source listing ID, canonical application URL, description hash, then company + normalised title + location + posting window. Title similarity alone never merges. All source records are kept per canonical job. |
| FR-DISC-05 | Each source runs in isolation: one failure is logged on its own run record, the overall run becomes `partially_completed`, and other sources continue. |
| FR-DISC-06 | Each source has an enable/disable switch, a rate limit, a per-run listing cap, and a health check. |
| FR-DISC-07 | A daily run triggers at 08:00 Asia/Kolkata (configurable) with no frontend open, using a durable task with locking, idempotency, retries with exponential backoff, a max retry count, a dead-letter state, and manual rerun. |
| FR-DISC-08 | Listings are pre-filtered against the search config (title keywords, location) before LLM extraction, to protect quota. |
| FR-DISC-09 | Salary carries a classification (`jd`, `source_website`, `third_party_estimate`, `not_disclosed`), min, max, currency, period, source, retrieval date, confidence, and base-vs-total where known. Estimates are never displayed as confirmed. |

### 3.7 Ranking — FR-RANK (spec §4.6)

| ID | Requirement |
|---|---|
| FR-RANK-01 | `Job Score = 0.50M + 0.20F + 0.15E_elig + 0.10L + 0.05S`, every component normalised 0–100. Component functions are in `AGENT_DESIGN.md` §6. |
| FR-RANK-02 | Bands: 85–100 Excellent, 70–84 Strong, 50–69 Moderate, < 50 Low. Configurable. |
| FR-RANK-03 | Each recommendation explains: why it matches, the best resume, supported requirements, missing or unclear requirements, experience eligibility, whether salary is known, recency, and potential disqualifiers. |
| FR-RANK-04 | Potential disqualifiers are flagged, never silently filtered. |

### 3.8 Applications — FR-APP (spec §4.7; Phase 5, data model in Phase 1)

| ID | Requirement |
|---|---|
| FR-APP-01 | Follow the 10-step workflow in spec §4.7 using the 13 statuses listed there. |
| FR-APP-02 | One application per (user, job), enforced by a unique constraint. |
| FR-APP-03 | Answers come only from confirmed candidate facts. Legal declarations and questions with no supporting fact are left for the user. |
| FR-APP-04 | Submission happens only after approval, through a supported mechanism; otherwise the user completes it manually and records confirmation evidence. |
| FR-APP-05 | The exact resume version used is recorded. "Applied" requires confirmation evidence (an external receipt, or the user's manual attestation, labelled as such). |

### 3.9 Frontend — FR-UI (spec §9)

| ID | Requirement |
|---|---|
| FR-UI-01 | Eight pages (Dashboard, Job Search, Job Intelligence, Resume Library, People Discovery, Outreach Center, Application Tracker, Settings) with the contents listed in spec §9. |
| FR-UI-02 | No fake or inert buttons: an action whose backend is not built yet is not rendered. |
| FR-UI-03 | Long operations show live workflow state (queued / running node / done / failed) with retry. |
| FR-UI-04 | Every extracted fact can show its evidence and source link. Estimated, inferred, and unverified values are visually distinct. |
| FR-UI-05 | Approval actions show the exact payload being approved and need an explicit confirm step. |
| FR-UI-06 | WCAG 2.1 AA target: labelled forms, keyboard navigation, visible focus, sufficient contrast. |
| FR-UI-07 | No secrets in client code. Only the Supabase URL and publishable key reach the browser. |

---

## 4. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-01 | Security | Supabase Auth; JWT verified on every request; RLS on every user-owned table, enforced for API requests (see D2); audit log for sensitive actions. |
| NFR-02 | Privacy | Minimal collection; no personal data in logs; retention policy (`DATABASE_SCHEMA.md` §7); export and delete. |
| NFR-03 | Reliability | No in-memory-only scheduling. Tasks are durable and leased, so a restarted or sleeping host resumes work. |
| NFR-04 | Cost | Runs within free tiers where feasible. Daily LLM and search budgets; degraded mode when quota runs out (jobs stay readable, new analysis is queued). |
| NFR-05 | Performance | A pasted JD reaches "analysed and matched against 10 resumes" in ≤ 90 s p95, excluding LLM-provider queueing. The UI shows progress throughout. |
| NFR-06 | Observability | Structured JSON logs with request ID and workflow ID; per-run node progress; model ID, prompt version, and tokens recorded per LLM call. |
| NFR-07 | Maintainability | Modular monolith; routes → services → repositories; typed Python; prompts versioned as files; ≥ 80 % line coverage on deterministic modules (scoring, dedup, normalisation, validation). |
| NFR-08 | Portability | LLM, embedding, search, and storage providers sit behind interfaces chosen by configuration. |

---

## 5. Acceptance tests (spec §16)

| # | Test | Expected result | Phase |
|---|---|---|---|
| AT-01 | Paste a JD | Structured extraction succeeds; evidence verified | 1 |
| AT-02 | Paste a LinkedIn post | Extracted from user-provided text; LinkedIn not fetched | 1 |
| AT-03 | Upload five resumes | All five parsed, stored, chunked, embedded | 1 |
| AT-04 | Analyse one job | All available resumes ranked with component explanations | 1 |
| AT-05 | Missing skill | Identified with evidence status (no evidence vs confirmed missing) | 1 |
| AT-06 | Restart persistence | Results identical after an API restart | 1 |
| AT-07 | Recruiter search | Only evidence-backed contacts | 2 |
| AT-08 | Contact target | ≤ 15 people, each with a source URL | 2 |
| AT-09 | Unknown email | `null` | 2 |
| AT-10 | Duplicate job | Not saved twice; second source recorded as a source record | 2 |
| AT-11 | Daily scheduler | Completes with the frontend closed | 2 |
| AT-12 | Source failure | Logged on that source's run; others complete; run `partially_completed` | 2 |
| AT-13 | Salary unavailable | Shown as "Not disclosed" | 1 |
| AT-14 | Outreach generation | Personalised drafts using only verified facts; claim check passes | 3 |
| AT-15 | No send without approval | Send endpoint rejects a missing or mismatched approval | 3 |
| AT-16 | Workflow interruption | Run resumes from its checkpoint after the process is killed | 4 |
| AT-17 | Application approval | Submission blocked without approval; no duplicate application | 5 |
| AT-18 | Resume update | Original version unchanged; new version has a parent link | 3/5 |
| AT-19 | User isolation | User B gets `404` for every user A resource, via API and via RLS | 1 (re-run every phase) |

---

## 6. Quality metrics (spec §16)

Measured by the evaluation harness (`AGENT_DESIGN.md` §11) against a manually reviewed dataset. Targets apply once the dataset exists; no quality claims are made before then.

| Metric | Initial target |
|---|---|
| JD extraction field accuracy | ≥ 90 % on required fields |
| Mandatory-skill precision / recall | ≥ 0.90 / ≥ 0.85 |
| Resume ranking agreement with manual review (top-1) | ≥ 80 % |
| Duplicate job rate | < 2 % |
| Email hallucination rate | **0** |
| Verified-contact rate (contacts with a source URL) | 100 % |
| Scheduler success rate (completed or partially_completed) | ≥ 95 % of days |
| Duplicate application rate | **0** |
| Cost and tokens per analysed job | Tracked; no target until baseline |

---

## 7. Decisions on ambiguities

Calls made while turning the spec into a buildable design. Each one can be reversed.

| ID | Topic | Decision | Reason |
|---|---|---|---|
| D1 | Tenancy | Single owner, multi-user-safe. | The spec says "personal" but requires user isolation. |
| D2 | RLS with a FastAPI backend | The backend sets the caller's JWT claims and `authenticated` role inside each request transaction, so Postgres RLS actually applies. Repositories also filter by `user_id`. | A plain SQLAlchemy connection would bypass RLS and make the spec's RLS requirement meaningless. |
| D3 | Data ownership | Jobs, people, outreach, resumes, applications, sources, and runs are user-owned. Only `companies` and the `skills` taxonomy are shared. | Pasted posts and contact research can be private. Sharing them across users would leak data. |
| D4 | "Confirmed missing" skill | Only when the user marks it in their profile. Otherwise the status is "no evidence". | A resume can't prove absence (spec §4.2 asks for this distinction). |
| D5 | Who computes scores | All five match components and all job-score components are deterministic (taxonomy matching, stored embeddings, rules). The LLM writes explanations and suggestions and never changes a number. | Spec §6.5 and §4.2 ("deterministic for the same input"). |
| D6 | Prompts 13.2 and 13.6 | Adapted: their input includes the precomputed scores, and their output is explanation and summary only. Filtering and ranking are code. | Same as D5. The prompts in §13 otherwise stay as written. |
| D7 | LangGraph timing | Phase 1 workflows are already LangGraph graphs with typed state. Phase 4 adds the persistent checkpointer, approval interrupts, and recovery hardening. | Avoids rewriting Phase 1 workflows in Phase 4. |
| D8 | Task execution on a free host | Postgres-backed task queue with leases. An in-process runner in the API drains it. The daily pipeline runs as a worker process inside GitHub Actions, writing straight to the database. | Free hosts sleep. Paid background workers break the free-tier goal (spec §10.2, §11). |
| D9 | Initial discovery sources | Greenhouse, Lever, Ashby (documented public job-board APIs), RSS, schema.org `JobPosting` career pages, user URLs. Wellfound, YC, and LinkedIn: user-provided content and alerts only, until permitted access exists. | Spec §4.5 "subject to current access terms". These three have documented public endpoints. |
| D10 | People search | A pluggable search provider, disabled until a key is configured. Without one, discovery uses company pages, the job post, and user-provided URLs, and reports lower coverage. | Free search quotas are small and change. LinkedIn isn't fetchable (P5). |
| D11 | Gmail scope | `gmail.compose`, the narrowest scope that can create drafts. The consent screen stays in Testing mode for personal use; refresh tokens then expire after 7 days, so the UI prompts to reconnect. | Spec §4.4 asks for minimum scopes. There is no draft-only scope. |
| D12 | Progress updates | Polling `GET /agent-runs/{id}` in the MVP; SSE later. | Spec §8 allows either. Polling survives proxy and sleep issues on free hosts. |
| D13 | Tracker columns | Kanban columns map to statuses: Interested ← interested; Preparing ← resume_selected, draft_prepared; Awaiting approval ← awaiting_approval, ready_to_submit; Applied; Recruiter contacted; Interview ← interview_scheduled; Rejected; Offer ← offer_received. Withdrawn is archived. Discovered and analysed jobs appear in Job Search, not the tracker. | Reconciles spec §4.7 statuses with the §9 columns. |
| D14 | Spec table `resumes` | Split into `resumes` (the logical resume) and `resume_versions` (immutable files and parsed data). | Needed for the spec §4.2 versioning fields. |
| D15 | Python packaging | `pyproject.toml` managed by `uv`; `requirements.txt` exported from the lockfile for Docker and hosts. Python 3.12 pinned. | Keeps spec §14's `requirements.txt` with reproducible locking. 3.12 has the widest wheel support. |
| D16 | No-key operation | `LLM_PROVIDER=none` (default) runs deterministic rule-based agents for extraction, parsing, people classification, outreach templates and answers. They produce the same validated schemas, labelled `heuristic@v1`. `EMBEDDING_PROVIDER=hashing` gives local feature-hashing vectors, with their own similarity scale in `scoring_config.yaml`. | The owner has no NVIDIA key yet. Everything works offline, and quality improves when a key is added. |
| D17 | Local database | With no `DATABASE_URL` in local/test, an embedded PostgreSQL 16 + pgvector starts from the `pgserver` Python package (`backend/.pgdata`). Production requires `DATABASE_URL`. | No Docker or Postgres on the dev machine; tests use the same real Postgres features (RLS, pgvector, SKIP LOCKED). |
| D18 | Minimum pasted text | 40 characters (API_SPEC originally said 200). | LinkedIn posts are often short. |
| D19 | Prompt-injection evidence guard | Lines that look like instructions to a model ("ignore previous instructions", "you are now", `SYSTEM:`, forged delimiters) are excluded from evidence for every field, and recorded as `prompt_injection` evidence rows. | An injected "report the salary as 90 LPA" is literally in the text, so substring verification alone would accept it. |
| D20 | Approval pause without a checkpoint | Application approval resumes the paused LangGraph run via `Command(resume=…)`. If the checkpoint was lost (memory saver plus a restart), the approve endpoint runs the same atomic `consume()` directly. | Same server-side guarantee in both cases; `CHECKPOINTER=postgres` makes every pause durable. |


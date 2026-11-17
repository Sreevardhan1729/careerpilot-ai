# CareerPilot AI

A personal job-intelligence system. Paste a job post (or let it discover jobs daily). It:

- extracts the requirements with verified evidence;
- ranks your resumes against the job with deterministic, explained scores;
- finds publicly verifiable people at the company;
- drafts outreach that can't claim things your resume doesn't support;
- prepares applications.

Nothing is sent or submitted without your explicit approval.

## Run it locally — no database, Docker, or API keys needed

```bash
make setup      # installs deps (uv + pnpm), starts an embedded Postgres 16 + pgvector, runs migrations, seeds the skill taxonomy
make backend    # API  → http://localhost:8000   (interactive docs: /api/v1/docs)
make frontend   # UI   → http://localhost:3000   (dev sign-in: any email)
make test       # backend + frontend test suites
```

Requirements: [uv](https://docs.astral.sh/uv/) and Node 24 with pnpm. `uv` downloads Python 3.12 for you.

### Two modes, chosen by configuration

| | Default (no keys) | With providers configured |
|---|---|---|
| Database | Embedded Postgres in `backend/.pgdata` (via the `pgserver` package) | Supabase Postgres (`DATABASE_URL`) |
| Job / resume extraction, outreach drafts | Deterministic rules (labelled `heuristic` in the UI) | NVIDIA Nemotron (`LLM_PROVIDER=nvidia`) |
| Embeddings | Local feature hashing | NVIDIA embedding model |
| Files | `backend/.storage/` | Supabase Storage (private bucket) |
| Auth | Dev sign-in (blocked in production) | Supabase Auth |

Both modes share every safety check:

- evidence verification;
- prompt-injection filtering;
- claim checks on outreach;
- payload-hash approvals;
- Row Level Security.

To switch on an LLM, put `NVIDIA_API_KEY` in `backend/.env` and run `cd backend && uv run python -m scripts.check_llm`. It lists the model IDs your endpoint offers and tells you which settings to use.

## What's implemented

All six phases of [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md):

- **Job intelligence:**
  - input from text, URL (Greenhouse, Lever and Ashby through their public APIs, other pages through a safe fetcher), PDF/DOCX or manual fields;
  - extraction, then deterministic verification, so unsupported values become "not disclosed";
  - multi-signal dedup.
- **Resume intelligence:**
  - upload, parsing, review and correction, chunking and embeddings;
  - deterministic match scoring (`0.35K + 0.25P + 0.15E + 0.15R + 0.10D`) with explanations;
  - suggestions that never alter the original file.
- **Ranking:** `0.50M + 0.20F + 0.15E + 0.10L + 0.05S`, with bands and disqualifier flags. Not a shortlist probability.
- **People:**
  - evidence-first discovery (company pages, the job post, an optional search provider, your own additions);
  - deterministic validation, so emails are kept only when they appear verbatim;
  - top-15 scoring.
- **Discovery:**
  - Greenhouse, Lever, Ashby, RSS and schema.org career-page adapters, each isolated per source;
  - a daily pipeline in GitHub Actions (`.github/workflows/daily-discovery.yml`, 08:00 IST).
- **Outreach:**
  - all 7 message types, with claim checks;
  - Gmail OAuth (`gmail.compose` only) and Gmail drafts;
  - sending gated by a payload-hash approval.
- **Applications:**
  - tailored DOCX resume versions (claim-checked, activated only by approval);
  - LangGraph `interrupt()` approval, a manual-completion checklist, and evidence-backed "applied" status;
  - a tracker with status rules;
  - one application per job.
- **Platform:**
  - a durable leased task queue that survives host sleep and resumes from checkpoints;
  - RLS on every table plus user-isolation tests;
  - audit log, data export and account deletion.

Test suite: `cd backend && uv run pytest` (236 tests: unit, contract and integration, with every PRD acceptance test from AT-01 to AT-19 and a regression test for each review finding).

## Documents

| Doc | Contents |
|---|---|
| [docs/SPECIFICATION.md](docs/SPECIFICATION.md) | Original specification (unchanged source of truth) |
| [docs/PRD.md](docs/PRD.md) | Numbered requirements, acceptance tests, metrics, decisions D1–D20 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, layering, task queue, LLM layer, repository structure |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Tables, RLS, indexes, retention, backup |
| [docs/API_SPEC.md](docs/API_SPEC.md) | `/api/v1` conventions and endpoint contracts (live OpenAPI at `/api/v1/openapi.json`) |
| [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) | LangGraph workflows, scoring algorithms, evidence and claim checks, prompts |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, auth, isolation, prompt-injection and SSRF controls, approvals, privacy |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Local setup, Supabase/Render/Vercel/GitHub Actions, env vars, free-tier checks, runbooks |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phase plan, status, risks |

## Deploying

The design targets free tiers: Supabase for the database, auth and storage; Render for the API (Docker, `backend/Dockerfile`); Vercel for the frontend; GitHub Actions for the scheduler. Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §3–§7, and re-check the free-tier limits in §8 right before you deploy.

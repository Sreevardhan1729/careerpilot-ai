# CareerPilot AI — Deployment and Operations

Free-tier-first, quota-aware (spec §11). **Every provider limit in §8 must be re-checked immediately before deploying.** Free tiers change, and the values below are design assumptions, not guarantees.

---

## 1. Environments

| Env | Frontend | API | Database | Storage | LLM | Auth |
|---|---|---|---|---|---|---|
| `local` | `pnpm dev` (localhost:3000) | `uvicorn --reload` (localhost:8000) | Local Postgres 17 + pgvector | Local filesystem (`STORAGE_BACKEND=local`) | NVIDIA (real key), or FakeLLM for offline UI work | `AUTH_MODE=dev`, or a Supabase dev project |
| `test` (CI) | Vitest | pytest | Postgres service container (`pgvector/pgvector:pg17`) | Local tmp | FakeLLM only (no network) | Dev tokens |
| `production` | Vercel Hobby | Render free web service (Docker) | Supabase free | Supabase Storage (private) | NVIDIA endpoint | Supabase Auth + email allowlist |

---

## 2. Local development (no database, Docker or keys)

```bash
make setup      # uv sync (Python 3.12 auto-installed) + pnpm install; embedded Postgres 16 + pgvector in backend/.pgdata;
                # migrations (scripts/migrate.py, under an advisory lock) + skill taxonomy seed
make backend    # uvicorn app.main:app --reload  → http://localhost:8000/api/v1/docs
make frontend   # pnpm dev                       → http://localhost:3000 (dev sign-in with any email)
make test       # backend pytest (embedded Postgres per session) + frontend vitest
```

Defaults: `APP_ENV=local`, `AUTH_MODE=dev`, `STORAGE_BACKEND=local`, `LLM_PROVIDER=none` (rule-based, D16), `EMBEDDING_PROVIDER=hashing`. To use NVIDIA:

1. Add `NVIDIA_API_KEY` to `backend/.env`.
2. Run `uv run python -m scripts.check_llm`; it prints the exact env lines to add.
3. If you switch embeddings, set `EMBEDDING_DIMENSIONS` first, then run `scripts/reembed.py`.

To use an external Postgres instead of the embedded one, set `DATABASE_URL`.

## 3. Supabase (production database, auth, storage)

1. Create a project in **Singapore** (`ap-southeast-1`), next to the Render Singapore region (Mumbai also works). Save the DB password.
2. **Extensions:** the migrations run `CREATE EXTENSION IF NOT EXISTS vector` / `pgcrypto`. Enable `vector` in the dashboard if the migration role lacks permission.
3. **Auth:**
   - enable the Email provider (magic link) and optionally Google sign-in;
   - Site URL = the Vercel production URL;
   - redirect URLs: `https://<app>.vercel.app/auth/callback` and `http://localhost:3000/auth/callback`;
   - disable public sign-ups once the owner account exists, or rely on `ALLOWED_USER_EMAILS`.
4. **Storage:** create the **private** bucket `resumes` (public access off). No Storage RLS policies are needed, because only the backend, using the secret key, accesses it.
5. **Keys:**
   - publishable key → frontend;
   - secret key → backend only;
   - note `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` for `SUPABASE_JWKS_URL`.
   - Older projects show "anon" and "service_role" keys instead; they map to the same variables.
6. **Connection string:** use the **Session pooler** URI. It is IPv4-compatible; Render and GitHub Actions runners don't reliably support the IPv6-only direct host. Convert it to `postgresql+psycopg://postgres.<ref>:<password>@<pooler-host>:5432/postgres?sslmode=require`.
7. **Data API:** the frontend doesn't use it. Either disable it, or leave it on (RLS plus no `anon` grants deny everything).
8. **Migrate and seed:** from a trusted machine, run `DATABASE_URL=… uv run alembic upgrade head && uv run python -m scripts.seed --owner-email you@example.com`. Later deploys migrate automatically (§4).

---

## 4. Backend on Render (free web service)

- **Service:** Web Service from the GitHub repo, root `backend/`, runtime **Docker**, instance type Free, region Singapore.
- **Dockerfile:**
  - multi-stage; `python:3.12-slim`;
  - `uv sync --frozen --no-dev` (or `pip install -r requirements.txt`);
  - non-root user;
  - Playwright **not** installed (memory).
- **Entrypoint** (`docker-entrypoint.sh`):
  1. `alembic upgrade head`, wrapped in `pg_advisory_lock(727172)` so concurrent starts can't race;
  2. `exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'`.
  - Exactly **one worker**, because the in-process task runner and rate limiter assume a single instance.
- **Health check path:** `/api/v1/health`.
- **Environment:** see §9 (API column).
- **Free-tier behaviour:** the service sleeps after a period without traffic and cold-starts on the next request (tens of seconds). Leased tasks resume after wake (`ARCHITECTURE.md` §5). The daily pipeline does **not** depend on this host.
- **Alternatives** if Render's terms or limits change: Koyeb free, Google Cloud Run (needs a billing account; generous free tier, scales to zero), or Hugging Face Spaces (Docker). All need the same env vars and a single-instance setting.

---

## 5. Frontend on Vercel (Hobby)

- Import the repo, set the root directory to `frontend/`. Framework: Next.js; package manager: pnpm.
- Env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_API_BASE_URL=https://<render-service>.onrender.com/api/v1`.
- Set the backend's `FRONTEND_ORIGIN` to the Vercel production URL (CORS). Preview deployments use the Supabase dev project and a local or dev API only; they are not allowed by production CORS.
- Hobby is for personal, non-commercial use, which matches this project. Re-check the terms if that changes.

---

## 6. Scheduler on GitHub Actions

`.github/workflows/daily-discovery.yml`:

```yaml
name: daily-discovery
on:
  schedule:
    - cron: "30 2 * * *"        # 02:30 UTC = 08:00 Asia/Kolkata (spec §10.1)
  workflow_dispatch:
    inputs:
      date: { description: "Pipeline date YYYY-MM-DD (optional, for reruns)", required: false }
concurrency: { group: daily-discovery, cancel-in-progress: false }
permissions: { contents: read }
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v5          # pin to commit SHA at implementation time
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen --no-dev
      - run: uv run python -m app.scheduler.daily --date "${{ inputs.date }}" --time-budget-minutes 100
        env:
          APP_ENV: production
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
          NVIDIA_BASE_URL: ${{ vars.NVIDIA_BASE_URL }}
          NVIDIA_MODEL: ${{ vars.NVIDIA_MODEL }}
          NVIDIA_EMBEDDING_MODEL: ${{ vars.NVIDIA_EMBEDDING_MODEL }}
          EMBEDDING_DIMENSIONS: ${{ vars.EMBEDDING_DIMENSIONS }}
          SEARCH_PROVIDER: ${{ vars.SEARCH_PROVIDER }}
          SEARCH_API_KEY: ${{ secrets.SEARCH_API_KEY }}
          CRAWLER_USER_AGENT: ${{ vars.CRAWLER_USER_AGENT }}
```

**What the worker does:**

1. For each user with an active search config, insert or claim the `daily_pipeline:{user_id}:{date}` task. This is idempotent.
2. Drain queued tasks for those users until the queue is empty or the time budget runs out. Anything left stays queued for the API runner or the next run.
3. Write `crawl_runs` and `agent_runs`, plus notifications.
4. Exit code `1` if the pipeline `failed` (GitHub emails the repo owner: the failure alert); `0` for `completed` and `partially_completed` (in-app notification).

**Notes:**

- Cron start times can be delayed under load. The pipeline doesn't assume fixed completion times.
- In public repos, GitHub disables scheduled workflows after 60 days of no repository activity, and the dashboard shows "Scheduler: stale" when `last_run_at` is older than 36 h. Private repos consume Actions minutes (§8).
- The daily run also keeps the Supabase free project from pausing for inactivity.

---

## 7. Third-party setup

### 7.1 NVIDIA inference

1. Create an API key at build.nvidia.com (NVIDIA developer program).
2. `NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1` (OpenAI-compatible). A self-hosted NIM uses its own URL.
3. Choose `NVIDIA_MODEL` **after** running `uv run python -m scripts.check_llm`. It lists `GET /v1/models`, sends a structured-output probe, checks JSON validity and any reasoning-trace format, and prints a recommended `LLM_STRUCTURED_OUTPUT_MODE`.
   - Candidate Nemotron families to evaluate: Nemotron Super, Nano, and Ultra variants. **The exact identifiers must come from the endpoint listing** (spec §5.4), not from this document.
4. Choose `NVIDIA_EMBEDDING_MODEL` (e.g. an `nv-embedqa` / `nemotron-embed` family model) and set `EMBEDDING_DIMENSIONS` to its output size **before the first migration**. Changing it later means a migration plus `scripts/reembed.py`.
5. Run the `jd_extraction` eval suite on 10+ JDs before trusting a model choice.

### 7.2 Google OAuth (Gmail drafts, Phase 3)

1. Create a Google Cloud project and enable the Gmail API.
2. OAuth consent screen: External, publishing status **Testing**, with the owner added as a test user.
3. Scope: `https://www.googleapis.com/auth/gmail.compose` only.
4. Create a Web OAuth client. Redirect URI: `https://<render-service>.onrender.com/api/v1/integrations/google/callback` (plus localhost for dev).
5. **Caveat:** in Testing mode, refresh tokens expire after 7 days, so the app shows a "Reconnect Google" notification. Publishing the app for wider use would require Google's restricted-scope verification; that isn't planned.

### 7.3 Search provider (optional, Phase 2)

Set `SEARCH_PROVIDER` (`brave` | `tavily` | `google_cse` | `serpapi` | `none`) and `SEARCH_API_KEY`, plus `SEARCH_CSE_ID` for Google. Leave it `none` to run people discovery on company pages, job posts, and user-provided URLs only. Set `SEARCH_DAILY_QUERY_BUDGET` below the provider's free quota.

---

## 8. Free-tier assumptions — verify before deploying

| Provider | Design assumption | Impact if wrong | Check |
|---|---|---|---|
| Render free web service | Sleeps when idle; ~512 MB RAM; monthly free instance-hours cap; no paid background workers | Tasks pause until wake; OOM if RAM is lower | Render pricing / free-tier docs |
| Supabase free | ~500 MB DB, ~1 GB storage; project pauses after ~1 week inactive; limited backups; Session pooler available on IPv4 | Retention tuning; backup script becomes mandatory | Supabase pricing + "pausing" docs |
| Vercel Hobby | Free for personal non-commercial use | Must move plan if commercial | Vercel fair-use / Hobby terms |
| GitHub Actions | Public repo: free minutes; private: limited monthly minutes; cron delays; 60-day inactivity disable | Daily run duration budget; keep-alive commits | GitHub Actions billing docs |
| NVIDIA API | Free developer access with rate limits; model catalogue changes | Lower `LLM_DAILY_CALL_BUDGET`; switch model via env | build.nvidia.com account / docs |
| Search provider | Small free monthly quota | Lower `SEARCH_DAILY_QUERY_BUDGET` or `none` | Provider pricing page |
| Gmail API | Testing-mode 7-day refresh-token expiry; per-user quotas ample for drafts | Weekly reconnect | Google OAuth docs |
| LinkedIn | Connection-note character limit (free accounts lower than Premium); personalised-invite caps | Set `LINKEDIN_CONNECTION_NOTE_MAX_CHARS` | LinkedIn Help |

**Cost controls** (spec §11):

- `LLM_DAILY_CALL_BUDGET`;
- `DISCOVERY_MAX_*` caps;
- `SEARCH_DAILY_QUERY_BUDGET`;
- the LLM cache;
- deterministic pre-filtering;
- no paid overages enabled on any provider;
- the dashboard shows LLM usage against budget.

---

## 9. Environment variables

Scopes: **A** = API (Render), **W** = worker (GitHub Actions), **F** = frontend (Vercel), **L** = local only. Secrets are marked 🔒.

| Variable | Scope | Required | Default | Purpose |
|---|---|---|---|---|
| `APP_ENV` | A W L | yes | `local` | `local` / `test` / `production` |
| `LOG_LEVEL` | A W | no | `INFO` | |
| `FRONTEND_ORIGIN` | A | prod | — | CORS allowlist (one origin) |
| `BACKEND_PUBLIC_URL` | A | prod | — | Builds the OAuth redirect URI |
| `DATABASE_URL` 🔒 | A W L | yes | — | `postgresql+psycopg://…?sslmode=require` (Session pooler in prod) |
| `EMBEDDED_PG_DIR` | L | no | `./.pgdata` | Embedded Postgres data dir when `DATABASE_URL` is empty (local/test only, D17) |
| `DEV_AUTH_SECRET` 🔒 | L | no | built-in dev value | Signs dev tokens; dev auth is refused in production |
| `CHECKPOINTER` | A W | no | `memory` | `postgres` = durable LangGraph checkpoints in schema `langgraph` |
| `TASK_POLL_SECONDS` | A | no | `1` | Task-runner poll interval |
| `DB_POOL_SIZE` | A W | no | `5` | Keep small for the pooler's client limits |
| `AUTH_MODE` | A L | yes | `supabase` | `supabase` or `dev` (blocked in production) |
| `ALLOWED_USER_EMAILS` | A W | **prod** | — | Comma list; single-owner allowlist. Production refuses to start without it unless `ALLOW_OPEN_SIGNUP=true` |
| `ALLOW_OPEN_SIGNUP` | A W | no | `false` | Explicit opt-in to let any Supabase user sign in |
| `SUPABASE_URL` | A | prod | — | `https://<ref>.supabase.co` |
| `SUPABASE_JWKS_URL` | A | prod* | derived | *Or `SUPABASE_JWT_SECRET` |
| `SUPABASE_JWT_SECRET` 🔒 | A | legacy | — | HS256 projects only |
| `SUPABASE_JWT_AUDIENCE` | A | no | `authenticated` | |
| `SUPABASE_SECRET_KEY` 🔒 | A | prod | — | Storage + admin (account deletion) |
| `DEV_AUTH_EMAIL` | L | dev | `owner@careerpilot.local` | Default dev identity |
| `STORAGE_BACKEND` | A L | yes | `supabase` | `supabase` or `local` |
| `STORAGE_BUCKET_RESUMES` | A | no | `resumes` | |
| `LOCAL_STORAGE_DIR` | L | local | `./.storage` | |
| `MAX_UPLOAD_MB` | A | no | `5` | |
| `MAX_RESUME_PAGES` | A | no | `20` | |
| `LLM_PROVIDER` | A W | yes | `none` | `none` (rule-based, D16) / `nvidia` / `fake` (tests only) |
| `NVIDIA_API_KEY` 🔒 | A W | if nvidia | — | |
| `NVIDIA_BASE_URL` | A W | yes | `https://integrate.api.nvidia.com/v1` | |
| `NVIDIA_MODEL` | A W | if nvidia | — | From `check_llm` (spec §5.4) |
| `LLM_TEMPERATURE` | A W | no | `0.1` | |
| `LLM_TIMEOUT_SECONDS` | A W | no | `60` | |
| `LLM_MAX_RETRIES` | A W | no | `3` | |
| `LLM_STRUCTURED_OUTPUT_MODE` | A W | no | `auto` | `auto` / `native` / `prompt` |
| `LLM_DAILY_CALL_BUDGET` | A W | no | `200` | Per user per day |
| `LLM_MAX_CONCURRENCY` | A W | no | `2` | Process-wide semaphore |
| `EMBEDDING_PROVIDER` | A W | no | `hashing` | `hashing` (local) / `nvidia` |
| `NVIDIA_EMBEDDING_MODEL` | A W | if nvidia embeddings | — | |
| `EMBEDDING_DIMENSIONS` | A W | yes | `1024` | Must match the migration |
| `TASK_RUNNER_ENABLED` | A | no | `true` | In-process runner |
| `TASK_RUNNER_CONCURRENCY` | A W | no | `2` | |
| `TASK_LEASE_SECONDS` | A W | no | `300` | |
| `SCHEDULER_TOKEN` 🔒 | A | optional | — | Only for an HTTP-triggered scheduler |
| `DEFAULT_TIMEZONE` | A W | no | `Asia/Kolkata` | Display and "today" boundary |
| `CRAWLER_USER_AGENT` | A W | yes | `CareerPilotBot/1.0 (+<contact URL>)` | Identifies the crawler |
| `FETCH_TIMEOUT_SECONDS` | A W | no | `15` | |
| `FETCH_MAX_BYTES` | A W | no | `2097152` | |
| `BLOCKED_FETCH_HOSTS` | A W | no | `linkedin.com` | Comma list; always includes LinkedIn |
| `PLAYWRIGHT_ALLOWED_DOMAINS` | W | no | empty | Enables JS rendering only for these |
| `DISCOVERY_MAX_SOURCES_PER_RUN` | W A | no | `20` | |
| `DISCOVERY_MAX_LISTINGS_PER_SOURCE` | W A | no | `100` | |
| `DISCOVERY_MAX_NEW_JOBS_ANALYZED_PER_RUN` | W A | no | `40` | LLM quota guard |
| `PEOPLE_DISCOVERY_MAX_JOBS_PER_RUN` | W A | no | `5` | |
| `SEARCH_PROVIDER` | A W | no | `none` | |
| `SEARCH_API_KEY` 🔒 | A W | if provider | — | |
| `SEARCH_CSE_ID` | A W | google only | — | |
| `SEARCH_DAILY_QUERY_BUDGET` | A W | no | `30` | |
| `GOOGLE_OAUTH_CLIENT_ID` | A | Phase 3 | — | |
| `GOOGLE_OAUTH_CLIENT_SECRET` 🔒 | A | Phase 3 | — | |
| `TOKEN_ENCRYPTION_KEYS` 🔒 | A | Phase 3 | — | Comma list of Fernet keys; first is active |
| `LINKEDIN_CONNECTION_NOTE_MAX_CHARS` | A W | no | `200` | |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | A | no | `120` | |
| `RATE_LIMIT_LLM_ENQUEUE_PER_HOUR` | A | no | `30` | |
| `NEXT_PUBLIC_SUPABASE_URL` | F | yes | — | |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | F | yes | — | Publishable (anon) key only |
| `NEXT_PUBLIC_API_BASE_URL` | F | yes | — | `…/api/v1` |
| `NEXT_PUBLIC_AUTH_MODE` | F L | no | `supabase` | `dev` shows the dev sign-in locally |

The same list, without values, is in `.env.example`.

---

## 10. Observability

- **Logs:** JSON to stdout (Render log stream; GitHub Actions job logs for the worker). Correlation fields: `request_id`, `workflow_id`, `task_id`, `node`. An external free log sink is optional.
- **Run history:** `agent_runs`, `crawl_runs`, and `llm_calls` are the source of truth. The Dashboard shows the scheduler status, recent failures, and LLM budget.
- **Alerts:**
  - a failed daily pipeline → GitHub failure email plus an in-app notification;
  - a source auto-disabled, LLM quota exhausted, or Google reconnect needed → in-app notification;
  - scheduler stale (> 36 h) → a dashboard banner.
- **Health:** `/api/v1/health` (Render health check). The dashboard also shows the last successful daily run.

---

## 11. Runbooks

| Situation | Steps |
|---|---|
| Daily run failed | 1. Open the GitHub Actions log. 2. `GET /agent-runs?status=failed`. 3. Fix the cause (key, quota, source). 4. `POST /agent-runs/{id}/retry` or the Actions "Run workflow" button with the date. Idempotent per date. |
| Task stuck in `running` | The sweeper re-queues it when the lease expires. To force: `UPDATE scheduled_tasks SET status='queued', locked_until=NULL WHERE id=…` (system session). |
| Source auto-disabled | Run its health check from Settings → Sources, fix the identifier or URL, re-enable. |
| LLM quota exhausted | Tasks wait until the next window. Lower the caps, or switch `NVIDIA_MODEL` and redeploy. Check the `llm_calls` aggregates. |
| Supabase project paused | Restore from the dashboard, then check `/health`. The daily workflow resumes the next day. |
| Google tokens expired | Settings → Integrations → Reconnect. |
| Key rotation | NVIDIA, search, `SCHEDULER_TOKEN`: replace in env, redeploy. `SUPABASE_SECRET_KEY`: rotate in Supabase, update Render. `TOKEN_ENCRYPTION_KEYS`: prepend the new key, deploy, run `scripts/rotate_tokens.py`, then remove the old key. |
| Restore database | Create a project, `pg_restore` the latest `scripts/backup.sh` dump, `alembic stamp head`, re-upload storage objects from an export ZIP, update `DATABASE_URL`. |
| Suspected secret leak | Rotate the affected key at once. Check `audit_events`. Purge it from git history if committed (then force-push only with owner approval). |

---

## 12. Release process

1. Feature branch → PR → CI (`ci.yml`): `ruff`, `mypy`, `pytest` with Postgres; `pnpm lint`, `tsc`, `vitest`; gitleaks; `pip-audit` / `pnpm audit`.
2. Merge to `main` → Render auto-deploys (migrations run at container start under the advisory lock) and Vercel auto-deploys.
3. Migrations follow **expand → migrate → contract**, so the previous app version keeps working during a deploy.
4. After the deploy: `/health` reports the new migration version; run a smoke flow (paste a sample JD, analyse, match).

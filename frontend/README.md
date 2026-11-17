# CareerPilot AI — frontend

Next.js (App Router) + TypeScript, Tailwind CSS v4, shadcn/ui primitives (vendored in `components/ui/`), TanStack Query, and
types generated from the FastAPI OpenAPI document. Every data call goes to the FastAPI backend with a bearer token; the
browser never talks to the database.

## Setup

Requires Node 24 and pnpm 10.

```bash
cp .env.example .env.local   # then edit if needed
pnpm install
pnpm gen:api                 # needs the backend toolchain (uv); see below
pnpm dev                     # http://localhost:3000
```

Run the backend alongside it (embedded Postgres, rule-based LLM by default):

```bash
cd ../backend
APP_ENV=local uv run alembic upgrade head   # first run only, creates the schema in backend/.pgdata
APP_ENV=local uv run uvicorn app.main:app --port 8000
```

The backend's `FRONTEND_ORIGIN` must match the frontend origin (default `http://localhost:3000`) for CORS.

### Environment

Only these variables are read by the browser (see `.env.example`). Never put secrets in them.

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000/api/v1` | FastAPI base URL including `/api/v1` |
| `NEXT_PUBLIC_AUTH_MODE` | `dev` | `dev` (email-only `POST /dev/login`, token in localStorage) or `supabase` (magic link) |
| `NEXT_PUBLIC_SUPABASE_URL` | — | Supabase project URL (supabase mode) |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | — | Supabase publishable/anon key (supabase mode) |

In `supabase` mode, add `<origin>/auth/callback` to the Supabase Auth redirect URLs.

## Scripts

| Script | What it does |
|---|---|
| `pnpm dev` / `pnpm build` / `pnpm start` | Next.js dev server / production build / serve the build |
| `pnpm lint` | ESLint (`eslint-config-next`, core-web-vitals + TypeScript; `react/no-danger` is an error) |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm test` | Vitest + Testing Library (jsdom) |
| `pnpm gen:api` | Exports `openapi.json` from the backend, generates `types/api.d.ts`, and writes `lib/api-capabilities.generated.ts`. `SKIP_EXPORT=1` reuses the existing `openapi.json`. |

## How it fits together

- `lib/api.ts` — fetch client: base URL, bearer token, error envelope → `ApiError`, multipart, `Idempotency-Key`, 401 → sign-out.
- `lib/endpoints.ts` — one typed function per endpoint. `types/models.ts` uses the generated OpenAPI types and falls back to
  hand-written types (from `backend/app/schemas/api`) for routes the backend hasn't exposed yet; the generated type wins
  automatically once it exists.
- `lib/capabilities.ts` — `hasEndpoint(method, path)` checks the generated operation list. Actions whose endpoint isn't in the
  OpenAPI document are not rendered (FR-UI-02); whole areas show a "not available on this server yet" notice. Re-run
  `pnpm gen:api` after the backend adds routes.
- `hooks/use-agent-run.ts` + `components/run-progress.tsx` — poll `GET /agent-runs/{id}` every 2 s (5 s after 2 min) until
  terminal; `awaiting_approval` pauses polling and shows approval UI; failed runs offer Retry.
- `components/approval-dialog.tsx` — shows the exact payload and requires an explicit confirm checkbox before approving.
- `components/provenance-badge.tsx`, `components/evidence-popover.tsx` — consistent "how is this known" labelling and evidence.
- All job/web/LLM text is rendered as plain text; links to external URLs are restricted to http(s) (`safeHref`).
- Times are shown in the user's timezone from `/me` (default Asia/Kolkata).

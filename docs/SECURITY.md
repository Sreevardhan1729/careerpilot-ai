# CareerPilot AI — Security, Privacy, and AI Safety

Implements spec §12, plus principles P4–P7. The checklist in §12 is verified at the end of each phase and in full during Phase 6.

---

## 1. Threat model

| Asset | Why it matters |
|---|---|
| Resumes, candidate profile (phone, work authorisation) | Personal data of the owner |
| Google OAuth tokens | Can create drafts and send email as the user |
| Contact records (`people`) | Personal data of third parties |
| Supabase secret key, DB URL, NVIDIA key, search key | Full data access, or quota and cost abuse |
| Approval records | The integrity of "never send or submit without approval" |

| Threat | Primary controls |
|---|---|
| Account takeover / forged JWT | Supabase Auth, JWKS verification, short-lived tokens (§2) |
| Cross-user data access (IDOR) | Ownership-scoped repositories, RLS, 404-on-foreign-ID, isolation tests (§3) |
| Prompt injection in JDs or web pages | Tool-less LLM nodes, delimiting, schema validation, deterministic post-checks, approval gates (§5) |
| SSRF via job or career URLs | SafeFetcher IP and scheme guards, re-checked on redirect (§6) |
| Malicious uploads (zip bomb, macro, parser exploit) | Magic bytes, size and page caps, DOCX structure checks, isolated parsing (§7) |
| Secret leakage (repo, logs, client bundle) | Env-only secrets, secret scanning, log redaction, publishable-key-only frontend (§4) |
| Unintended external action | Approval service with payload hash plus atomic consume; no send tool in agents (§8) |
| Scraping-terms violations | Permitted-source policy, robots, rate limits, blocked hosts (§10) |
| Dependency compromise | Lockfiles, `pip-audit` / `pnpm audit`, Dependabot, minimal images (§11) |

---

## 2. Authentication

- **Supabase Auth.** Email magic link and/or Google sign-in. The browser holds the session through `@supabase/ssr`.
- **Backend verification, every request:**
  - signature via `SUPABASE_JWKS_URL` (asymmetric keys), or `SUPABASE_JWT_SECRET` for legacy HS256 projects;
  - `exp` and `nbf` checked with 30 s leeway;
  - `iss == {SUPABASE_URL}/auth/v1`;
  - `aud == authenticated`.
  - The JWKS is cached for 10 min and refetched when an unknown `kid` appears.
- **Optional allowlist.** `ALLOWED_USER_EMAILS` (comma list), for single-owner deployments. Any other signed-in user gets `403` at the dependency level. Recommended for the personal deployment.
- **Dev auth** (`AUTH_MODE=dev`) accepts a locally signed token for a fixed dev user. **The app refuses to start** if `AUTH_MODE=dev` and `APP_ENV=production`.
- **Scheduler token** (`SCHEDULER_TOKEN`). Accepted only by `POST /scheduler/run`, compared in constant time. Rotate it on suspicion. It isn't needed when the GitHub Actions worker connects to the DB directly (the default).

---

## 3. Authorisation and data isolation

1. **Repositories:** every query on a user-owned table includes `user_id = :current_user`. Lookups by ID use `WHERE id = :id AND user_id = :uid`, and a miss returns `404`.
2. **RLS (defence in depth):** forced on every `public` table. API requests run as `authenticated` with the caller's claims set per transaction (`ARCHITECTURE.md` §4). A repository bug therefore still can't read another user's rows.
3. **Workers:** they set user-scoped sessions per task `user_id` before touching user data.
4. **Storage:**
   - Private bucket.
   - Object keys are `<user_id>/<random-uuid>.<ext>`.
   - Only the backend talks to Storage, using the secret key.
   - Downloads use signed URLs that live 60 s, issued after an ownership check.
5. **Tests (AT-19), run every phase:**
   - two users; every endpoint with a foreign ID returns 404;
   - list endpoints never include foreign rows;
   - direct SQL in a user-scoped session can't select, update, or insert foreign rows.

---

## 4. Secrets and configuration

- Secrets come **only** from environment variables (Render, Vercel, and GitHub Actions secrets). `.env` files are gitignored; `.env.example` holds names only.
- The frontend receives only `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, and `NEXT_PUBLIC_API_BASE_URL`. A CI check fails the build if any other `NEXT_PUBLIC_*` variable, or a known secret prefix (`sb_secret_`, `nvapi-`, etc.), appears in the client bundle.
- Secret scanning runs in CI (gitleaks) and optionally as a pre-commit hook.
- **OAuth tokens:**
  - encrypted at rest with `MultiFernet(TOKEN_ENCRYPTION_KEYS)`; the first key encrypts, all keys decrypt, and `token_key_id` is stored per row;
  - rotation: prepend a new key, run `scripts/rotate_tokens.py`, then remove the old key;
  - tokens are never returned by any API, never logged, and are deleted (and revoked at Google) on disconnect or account deletion.
- Settings validate at startup and the app fails fast on missing secrets. Settings `repr` masks secret fields.

---

## 5. Prompt-injection and LLM safety (spec §12.2)

| Control | Implementation |
|---|---|
| Retrieved content is data | Every external text goes inside `<untrusted_document id=…>` delimiters. Before it, the system prompt states it is data and that embedded instructions must be ignored. Delimiter look-alikes inside the content are escaped. |
| Separate system and external content | System prompts are static files. External content is never interpolated into the system role. |
| No tool escalation | Extraction, classification, explanation, and generation nodes have **no tools**. The model can't call fetch, DB, search, Gmail, or submit. |
| Server-side validation | All LLM output is parsed into strict Pydantic models (`extra="forbid"`, enums, length limits). URLs in LLM output are never fetched. People URLs must match evidence URLs (`AGENT_DESIGN.md` §7.3). |
| Deterministic post-checks | Evidence verification, people validation, and claim checks (`AGENT_DESIGN.md` §3.3, §7.3, §8). An injected "the salary is ₹1 Cr" fails unless that text is in the JD — and then it's honestly in the JD. |
| Privileged actions behind approval | Only approval-consuming executors can send or submit. No graph node can approve. |
| Minimal personal data in prompts | Phone and work authorisation are never included unless an application question needs them. Secrets are never included. |
| Output rendering | The frontend renders LLM and external text as plain text (no `dangerouslySetInnerHTML`). Markdown, where used, goes through a sanitising renderer with links `rel="noopener noreferrer nofollow"`. |
| Testing | `injection` eval suite (`AGENT_DESIGN.md` §11) plus unit tests for delimiter escaping. |

---

## 6. Safe fetching (SSRF and abuse)

`SafeFetcher` is the only client for untrusted URLs:

- **Schemes:** `http` and `https` only. No credentials in the URL. Ports 80 and 443, plus an explicit allowlist.
- **Addresses:** the host is resolved and **every** resolved IP checked. Rejected ranges: RFC 1918, loopback, link-local (incl. `169.254.169.254`), CGNAT `100.64/10`, `0.0.0.0/8`, multicast, IPv6 ULA (`fc00::/7`), link-local `fe80::/10`, and IPv4-mapped forms. The connection is pinned to the checked IP (no TOCTOU rebinding).
- **Redirects:** max 5, each target re-validated.
- **Limits:** 15 s total timeout, 2 MB body cap (streamed), content-type allowlist (`text/html`, `application/json`, `application/xml`, `application/rss+xml`, `application/pdf`, DOCX MIME).
- **Politeness:** robots.txt via `protego`, cached 24 h; disallowed means `source_not_permitted`. Identifying User-Agent. Per-domain token bucket (default 30/min, 1 concurrent).
- **Blocked hosts:** `linkedin.com` and its subdomains, plus `BLOCKED_FETCH_HOSTS`. These return `source_not_permitted` with the suggestion to paste text.
- **No cookies, no auth headers, no JS** by default. Playwright, when enabled for an allowlisted domain, runs with the same IP guard on every request, blocks downloads, and has no persistent profile.

---

## 7. File handling

- **Size:** `MAX_UPLOAD_MB` (default 5). Request bodies over the limit are rejected before buffering.
- **Type:** decided by magic bytes, never by extension or the client's MIME type.
  - PDF: `%PDF-` header.
  - DOCX: a ZIP containing `[Content_Types].xml` and `word/document.xml`.
  - `.docm`, `.doc`, and other formats are rejected (`415`).
- **Zip-bomb guard:** total uncompressed size ≤ 50 MB, ≤ 1,000 entries, compression ratio ≤ 100:1.
- **PDF:** page cap 20 (configurable). PyMuPDF extracts text only; there is no JS execution and embedded files are ignored. Encrypted PDFs are rejected with a clear message.
- **Parsing isolation:** parsing runs in the task runner under a timeout (60 s). A future hardening step is a subprocess with resource limits.
- **Names and keys:** storage keys are random. Original filenames are stored as metadata only, sanitised for display.
- **Downloads:** served by signed URL with `Content-Disposition: attachment`.

---

## 8. Approval controls (spec §12.3)

**Mandatory approval** before:

- sending email (`send_email`);
- submitting applications (`submit_application`);
- making a materially changed resume version active (`activate_resume_version`);
- publishing or sharing personal information (`share_personal_info`);
- any other irreversible external action (`external_action`).

**Mechanism:**

1. **Request.** The service builds the exact payload, computes `payload_hash = sha256(canonical_json(payload))`, stores `payload_preview`, and sets `expires_at` (24 h).
2. **Decide.** An authenticated user call with `approval_id`, `payload_hash`, and `confirm: true` plus an `Idempotency-Key` marks the row `approved`.
3. **Execute.** The executor rebuilds the payload from current state and **atomically consumes** the approval (`UPDATE … WHERE status='approved' AND payload_hash=:h AND expires_at>now() RETURNING`). Any change to the draft, recipient, or resume after approval breaks the hash, so execution is refused.
4. **Record.** `execution_result`, `external_confirmation` (e.g. Gmail message ID), `executed_at`, and an `audit_events` row.

Recorded per spec: user ID, action, target, payload hash (plus preview), approval timestamp, execution result, and external confirmation evidence.

**Not approval-gated, but explicit user actions:**

- creating a Gmail **draft** (writes only to the user's own Drafts folder);
- marking a LinkedIn message as manually sent;
- recording a manual application submission (stored as `user_attestation`).

### 8.1 Audit events

Written for:

- sign-in from a new device (if available from Supabase hooks; otherwise first API use per day);
- OAuth connect and disconnect;
- token decrypt for send;
- approval requested, decided, and executed;
- email sent;
- application submitted or confirmed;
- resume version activated;
- data export;
- account deletion;
- source enabled or disabled;
- scheduler manual run;
- settings changes to LLM, search, or sources.

Metadata never includes message bodies or tokens.

---

## 9. Privacy

- **Minimal collection.** Only the fields in spec §3.1 and §4.3. People data is limited to professional information that is publicly disclosed, with its source. No personal social profiles, home addresses, or personal phone numbers are collected, even if found.
- **Do-not-contact.** `contact_status=do_not_contact` blocks outreach generation for that person.
- **Retention.** Per `DATABASE_SCHEMA.md` §7. No raw HTML is ever stored.
- **Export.** A ZIP of all user data plus original files (`POST /account/export`).
- **Deletion.** `DELETE /account` (requires typed confirmation) removes:
  - all user-owned rows (cascade);
  - storage objects;
  - LangGraph threads;
  - Google tokens (revoked at Google first);
  - the Supabase auth user (via the admin API).

  An audit row is kept without personal fields.
- **Logs.** A redaction processor masks emails, phone numbers, bearer tokens, and API-key patterns. Request bodies are never logged. User IDs are UUIDs only.
- **Regulatory note (not legal advice).** For an India-based owner, India's Digital Personal Data Protection Act 2023 is relevant to storing third-party contact data. GDPR applies to EU-resident contacts. The minimal-collection, purpose-limitation, deletion, and do-not-contact controls above are designed with these in mind. Review before any multi-user or commercial use.

---

## 10. Source governance (spec §4.5)

- Only adapters for documented public APIs or robots-permitted pages. LinkedIn, Wellfound, and YC content comes only through user-provided text or alerts (D9).
- Each `crawl_sources` row records `terms_reviewed_at` and `terms_note`. Adding a new source type requires a terms review noted in the PR.
- Reasonable rate limits; crawler identified by User-Agent; no anti-bot evasion (no proxy rotation, UA spoofing, CAPTCHA solving, or headless stealth).
- A source disable switch, plus auto-disable after 7 consecutive failures, with a notification.
- Errors are logged per source; one failure never stops the run.

---

## 11. Platform and dependency security

- **CORS:** allow only `FRONTEND_ORIGIN`; methods and headers are explicit; no wildcard with credentials. The API uses bearer tokens, not cookies, so CSRF doesn't apply to API calls. The OAuth callback uses `state` (bound to the user session, single use, 10 min TTL) plus PKCE.
- **Security headers:** `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and a CSP on the frontend (`default-src 'self'`, `connect-src` limited to the API and Supabase).
- **Rate limits:** per `API_SPEC.md` §1.7; `429` with `Retry-After`.
- **Dependencies:**
  - `uv.lock` and `pnpm-lock.yaml` committed;
  - `pip-audit` and `pnpm audit --prod` in CI (fail on high or critical);
  - Dependabot weekly.
- **Container:** slim Python base, non-root user, no build tools in the final stage, read-only app directory.
- **TLS** everywhere (all providers terminate TLS). DB connections use `sslmode=require`.

---

## 11b. Controls added after the whole-branch review

| Area | Control |
|---|---|
| Evidence | Extracted values must appear in the source span their evidence matched. Experience and salary numbers are re-derived from that span, never taken from the model's snippet. |
| People | An email is kept only if it is a whole address token in a supporting snippet, on the company domain, and not a generic mailbox. "Former" or "ex-" near the name rejects the person. Name and company must appear in the same evidence item, unless it is on the company site. |
| Company domains | A domain is taken only from a company-owned URL. It must not be a job board, form host, social site or ATS, and its label must match the company name. |
| Outreach claims | Every number must come from verified facts or the job. Skills are checked clause by clause. A reference to a different role or company blocks the draft. |
| Resumes | Model-parsed bullets, achievements, summaries and technologies must match the text as whole items. "Strong" evidence comes only from verified technologies. |
| Sending | The approval is consumed and committed before Gmail is called. A failed or timed-out send marks the approval `failed` (outcome unknown), so it can never be retried with the same approval. |
| Deletion | Storage is deleted by the `<user_id>/` prefix. Checkpoints are purged with their runs. Exports expire after 24 h. A `deleted_users` tombstone blocks re-creation. |
| Logs | Redaction runs after tracebacks are formatted. Standard-library and httpx records pass through the same redaction, including query-string credentials. Google revoke sends its token in the body. |
| SSRF | IPv4 embedded in IPv6 (mapped, NAT64, 6to4, Teredo, IPv4-compatible) is validated as IPv4. |
| Sign-up | Production Supabase mode refuses to start without `ALLOWED_USER_EMAILS`, unless `ALLOW_OPEN_SIGNUP=true`. |
| Prompt injection | Instruction-like lines are excluded from evidence (D19). |

## 12. Security checklist (per phase; full in Phase 6)

- [ ] JWT verification rejects a wrong `iss`, wrong `aud`, expired tokens, and `alg=none`
- [ ] `AUTH_MODE=dev` blocked in production
- [ ] Isolation suite (AT-19) green
- [ ] RLS forced on all `public` tables (query `pg_class.relforcerowsecurity`)
- [ ] No secrets in repo (gitleaks) or client bundle (bundle scan)
- [ ] SafeFetcher tests: private IPs, DNS rebinding, redirect-to-private, oversize body, blocked hosts
- [ ] Upload tests: wrong magic bytes, `.docm`, zip bomb, encrypted PDF, page cap
- [ ] Injection eval suite passes
- [ ] Approval tests: missing, mismatched hash, expired, replay, edited-after-approval
- [ ] Claim-check tests: invented metric, unsupported skill, fake relationship, unverified email
- [ ] Log redaction test
- [ ] Export and delete end-to-end test, including storage and Google revoke
- [ ] `pip-audit` / `pnpm audit` clean (or documented exceptions)

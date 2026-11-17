import { API_BASE_URL } from "./env";

/** The backend's error envelope (docs/API_SPEC.md §1.3). */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
    request_id?: string | null;
  };
}

export interface FieldError {
  field: string;
  message: string;
}

const STATUS_FALLBACK_CODES: Record<number, string> = {
  400: "bad_request",
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  405: "method_not_allowed",
  409: "conflict",
  413: "file_too_large",
  415: "unsupported_file_type",
  422: "validation_error",
  429: "rate_limited",
  500: "internal_error",
  502: "upstream_error",
  503: "unavailable",
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
    requestId?: string | null;
    retryAfter?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? {};
    this.requestId = init.requestId ?? null;
    this.retryAfter = init.retryAfter ?? null;
  }

  /** `validation_error` responses carry `details.fields[]`. */
  get fieldErrors(): FieldError[] {
    const fields = this.details.fields;
    if (!Array.isArray(fields)) return [];
    return fields
      .filter((f): f is { field?: unknown; message?: unknown } => !!f && typeof f === "object")
      .map((f) => ({ field: String(f.field ?? ""), message: String(f.message ?? "Invalid value") }));
  }

  /** Transient failures worth an automatic retry (network, 5xx except 501). */
  get isTransient(): boolean {
    return this.status === 0 || (this.status >= 500 && this.status !== 501);
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== "object") return false;
  const err = (value as { error?: unknown }).error;
  return !!err && typeof err === "object" && typeof (err as { code?: unknown }).code === "string";
}

function parseRetryAfter(header: string | null): number | null {
  if (!header) return null;
  const seconds = Number(header);
  return Number.isFinite(seconds) ? seconds : null;
}

/** Turn any non-2xx response into a typed ApiError, preferring the backend's envelope. */
export async function parseApiError(res: Response): Promise<ApiError> {
  const requestIdHeader = res.headers.get("X-Request-ID");
  const retryAfter = parseRetryAfter(res.headers.get("Retry-After"));
  let body: unknown = null;
  const text = await res.text().catch(() => "");
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (isErrorEnvelope(body)) {
    const e = body.error;
    const details = e.details && typeof e.details === "object" ? e.details : {};
    const detailRetry = typeof details.retry_after === "number" ? details.retry_after : null;
    return new ApiError({
      status: res.status,
      code: e.code,
      message: e.message || res.statusText || "Request failed.",
      details,
      requestId: e.request_id ?? requestIdHeader,
      retryAfter: retryAfter ?? detailRetry,
    });
  }
  // FastAPI's default `{"detail": ...}` shape, or a proxy/HTML error page.
  let message = res.statusText || `Request failed with status ${res.status}.`;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") message = detail;
  }
  return new ApiError({
    status: res.status,
    code: STATUS_FALLBACK_CODES[res.status] ?? `http_${res.status}`,
    message,
    requestId: requestIdHeader,
    retryAfter,
  });
}

// ------------------------------------------------------------------------------------------------ configuration
export interface ApiConfig {
  baseUrl: string;
  getToken: () => Promise<string | null> | string | null;
  onUnauthorized: (error: ApiError) => void;
  /** 403 forbidden on an authenticated call: account deleted or not allowed on this deployment. */
  onForbidden: (error: ApiError) => void;
  fetch: typeof fetch;
}

const config: ApiConfig = {
  baseUrl: API_BASE_URL,
  getToken: () => null,
  onUnauthorized: () => {},
  onForbidden: () => {},
  fetch: (...args) => globalThis.fetch(...args),
};

export function configureApi(partial: Partial<ApiConfig>): void {
  Object.assign(config, partial);
}

// ------------------------------------------------------------------------------------------------ requests
export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue | QueryValue[]>;

/** Arrays become repeated keys (`?work_mode=remote&work_mode=hybrid`), matching FastAPI list query params. */
export function buildUrl(path: string, query?: QueryParams, baseUrl: string = config.baseUrl): string {
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, raw] of Object.entries(query)) {
    const values = Array.isArray(raw) ? raw : [raw];
    for (const v of values) {
      if (v === undefined || v === null || v === "") continue;
      params.append(key, String(v));
    }
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: QueryParams;
  /** JSON body. */
  json?: unknown;
  /** Multipart body; the browser sets the boundary header. */
  form?: FormData;
  /** Sent as `Idempotency-Key`. Use `newIdempotencyKey()` once per user action. */
  idempotencyKey?: string;
  signal?: AbortSignal;
  /** Attach the bearer token (default true). */
  auth?: boolean;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // RFC 4122 v4 fallback for very old browsers.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Low-level request. Resolves with the Response for 2xx, otherwise throws ApiError. */
export async function apiRequest(path: string, opts: RequestOptions = {}): Promise<Response> {
  const headers = new Headers({ Accept: "application/json" });
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  if (opts.idempotencyKey) headers.set("Idempotency-Key", opts.idempotencyKey);
  if (opts.auth !== false) {
    const token = await config.getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  let res: Response;
  try {
    res = await config.fetch(buildUrl(path, opts.query), {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
      credentials: "omit",
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "Can't reach the CareerPilot API. Check that the backend is running, then try again.",
    });
  }

  if (!res.ok) {
    const error = await parseApiError(res);
    if (res.status === 401 && opts.auth !== false) config.onUnauthorized(error);
    if (res.status === 403 && error.code === "forbidden" && opts.auth !== false) config.onForbidden(error);
    throw error;
  }
  return res;
}

async function readJson<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function apiJson<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  return readJson<T>(await apiRequest(path, opts));
}

/** For endpoints whose meaning depends on the status (200 dedup vs 202 accepted). */
export async function apiJsonWithStatus<T>(path: string, opts: RequestOptions = {}): Promise<{ status: number; data: T }> {
  const res = await apiRequest(path, opts);
  return { status: res.status, data: await readJson<T>(res) };
}

// ------------------------------------------------------------------------------------------------ messages
const FRIENDLY: Record<string, string> = {
  network_error: "Can't reach the CareerPilot API. Check that the backend is running, then try again.",
  source_not_permitted: "LinkedIn can't be fetched — paste the post text instead.",
  unsafe_url: "That URL isn't allowed. Use a public http(s) job page.",
  file_too_large: "That file is too large. The limit is 5 MB.",
  unsupported_file_type: "Only PDF and DOCX files are supported.",
  rate_limited: "You're doing that too often. Wait a moment and try again.",
  llm_quota_exhausted: "Today's LLM budget is used up. Work is queued until the next window.",
  idempotency_conflict: "This action was already submitted with different details. Refresh and try again.",
  approval_mismatch: "The content changed after approval was requested. Request approval again to review the latest version.",
  approval_expired: "This approval has expired. Request approval again.",
  integration_not_connected: "Connect Google in Settings → Integrations first.",
  unverified_recipient: "The recipient email isn't a verified public address for this person.",
  forbidden: "This account isn't allowed to use this deployment.",
  account_deleted: "This account was deleted.",
};

/** A human message for any thrown value; prefers the server's message except where a clearer UI message exists. */
export function errorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === "source_not_permitted") {
      const host = typeof error.details.host === "string" ? error.details.host : "";
      if (/linkedin/i.test(host) || /linkedin/i.test(error.message) || error.details.suggestion === "paste_text") {
        return FRIENDLY.source_not_permitted;
      }
      return error.message || "This source can't be fetched. Paste the text instead.";
    }
    if (error.code === "rate_limited" && error.retryAfter) {
      return `You're doing that too often. Try again in ${Math.ceil(error.retryAfter)}s.`;
    }
    if (error.code === "validation_error" && error.fieldErrors.length) {
      return error.fieldErrors.map((f) => (f.field ? `${f.field}: ${f.message}` : f.message)).join("; ");
    }
    if (error.code === "forbidden" && isAccountDeleted(error)) return FRIENDLY.account_deleted;
    return FRIENDLY[error.code] ?? error.message;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** The backend answers 403 forbidden ("This account was deleted.") for tokens of deleted accounts. */
export function isAccountDeleted(error: ApiError): boolean {
  return error.code === "forbidden" && (/deleted/i.test(error.message) || error.details.reason === "account_deleted");
}

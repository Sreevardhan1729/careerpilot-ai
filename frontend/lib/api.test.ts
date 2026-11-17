import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiJson, apiJsonWithStatus, buildUrl, configureApi, errorMessage, isAccountDeleted, isErrorEnvelope, parseApiError } from "./api";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

describe("parseApiError", () => {
  it("parses the backend error envelope into a typed ApiError", async () => {
    const res = jsonResponse(422, {
      error: {
        code: "source_not_permitted",
        message: "LinkedIn pages can't be fetched. Paste the post text instead.",
        details: { host: "www.linkedin.com", suggestion: "paste_text" },
        request_id: "req-123",
      },
    });
    const err = await parseApiError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.code).toBe("source_not_permitted");
    expect(err.message).toMatch(/LinkedIn/);
    expect(err.details).toEqual({ host: "www.linkedin.com", suggestion: "paste_text" });
    expect(err.requestId).toBe("req-123");
  });

  it("exposes validation field errors from details.fields", async () => {
    const err = await parseApiError(
      jsonResponse(422, {
        error: { code: "validation_error", message: "Some fields are invalid.", details: { fields: [{ field: "body.text", message: "too short" }] }, request_id: null },
      }),
    );
    expect(err.fieldErrors).toEqual([{ field: "body.text", message: "too short" }]);
    expect(errorMessage(err)).toBe("body.text: too short");
  });

  it("falls back to the X-Request-ID header and Retry-After for rate limits", async () => {
    const err = await parseApiError(
      jsonResponse(429, { error: { code: "rate_limited", message: "Too many requests.", details: { retry_after: 30 } } }, { "X-Request-ID": "hdr-1", "Retry-After": "12" }),
    );
    expect(err.requestId).toBe("hdr-1");
    expect(err.retryAfter).toBe(12);
    expect(errorMessage(err)).toBe("You're doing that too often. Try again in 12s.");
  });

  it("handles FastAPI's default {detail} body and non-JSON bodies", async () => {
    const a = await parseApiError(jsonResponse(404, { detail: "Not Found" }));
    expect(a.code).toBe("not_found");
    expect(a.message).toBe("Not Found");

    const b = await parseApiError(new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    expect(b.code).toBe("upstream_error");
    expect(b.message).toBe("Bad Gateway");
    expect(b.isTransient).toBe(true);
  });

  it("recognises envelopes structurally", () => {
    expect(isErrorEnvelope({ error: { code: "x", message: "y" } })).toBe(true);
    expect(isErrorEnvelope({ detail: "x" })).toBe(false);
    expect(isErrorEnvelope(null)).toBe(false);
  });
});

describe("friendly messages", () => {
  it("maps LinkedIn source_not_permitted to the paste-text hint", () => {
    const err = new ApiError({ status: 422, code: "source_not_permitted", message: "server text", details: { host: "linkedin.com" } });
    expect(errorMessage(err)).toBe("LinkedIn can't be fetched — paste the post text instead.");
  });

  it("keeps the server message for non-LinkedIn blocked sources", () => {
    const err = new ApiError({ status: 422, code: "source_not_permitted", message: "robots.txt disallows fetching this page.", details: { url: "https://x.test" } });
    expect(errorMessage(err)).toBe("robots.txt disallows fetching this page.");
  });
});

describe("request client", () => {
  const fetchMock = vi.fn();
  const onUnauthorized = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    onUnauthorized.mockReset();
    configureApi({ baseUrl: "http://api.test/api/v1", fetch: fetchMock as unknown as typeof fetch, getToken: () => "tok-1", onUnauthorized });
  });
  afterEach(() => {
    configureApi({ getToken: () => null, onUnauthorized: () => {} });
  });

  it("serialises arrays as repeated query keys and drops empty values", () => {
    expect(buildUrl("/jobs", { work_mode: ["remote", "hybrid"], q: "", saved: false, min_score: 70, x: undefined }, "http://api.test/api/v1")).toBe(
      "http://api.test/api/v1/jobs?work_mode=remote&work_mode=hybrid&saved=false&min_score=70",
    );
  });

  it("attaches the bearer token, JSON body and Idempotency-Key", async () => {
    fetchMock.mockResolvedValue(jsonResponse(202, { workflow_id: "w1", status: "queued", status_url: "/api/v1/agent-runs/w1" }));
    const res = await apiJsonWithStatus("/jobs/analyze", { method: "POST", json: { text: "hi" }, idempotencyKey: "key-1" });
    expect(res.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/jobs/analyze");
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-1");
    expect(headers.get("Idempotency-Key")).toBe("key-1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ text: "hi" }));
  });

  it("lets the browser set the multipart boundary for uploads", async () => {
    fetchMock.mockResolvedValue(jsonResponse(202, { workflow_id: "w1", status: "queued", status_url: "" }));
    const form = new FormData();
    form.append("file", new Blob(["x"]), "cv.pdf");
    await apiJson("/resumes/upload", { method: "POST", form });
    const init = fetchMock.mock.calls[0][1];
    expect((init.headers as Headers).has("Content-Type")).toBe(false);
    expect(init.body).toBe(form);
  });

  it("signs out on 401 and throws the parsed error", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { error: { code: "unauthorized", message: "Authentication required.", request_id: "r" } }));
    await expect(apiJson("/me")).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not sign out on other errors", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { error: { code: "not_found", message: "Resource not found." } }));
    await expect(apiJson("/jobs/x")).rejects.toMatchObject({ code: "not_found" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("turns network failures into a network_error ApiError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiJson("/me")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});

describe("forbidden handling", () => {
  it("calls onForbidden for a deleted account and maps the message", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "forbidden", message: "This account was deleted.", details: {}, request_id: "r" } }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const onForbidden = vi.fn();
    const onUnauthorized = vi.fn();
    configureApi({ baseUrl: "http://api.test/api/v1", fetch: fetchMock as unknown as typeof fetch, getToken: () => "old", onForbidden, onUnauthorized });
    const err = (await apiJson("/me").catch((e: unknown) => e)) as ApiError;
    expect(err).toMatchObject({ status: 403, code: "forbidden" });
    expect(isAccountDeleted(err)).toBe(true);
    expect(errorMessage(err)).toBe("This account was deleted.");
    expect(onForbidden).toHaveBeenCalledTimes(1);
    expect(onUnauthorized).not.toHaveBeenCalled();
    configureApi({ getToken: () => null, onUnauthorized: () => {}, onForbidden: () => {} });
  });
});

import { describe, expect, it } from "vitest";
import { hasEndpoint } from "./capabilities";
import { safeHref } from "./utils";

describe("safeHref", () => {
  it("allows only http(s) links from untrusted text", () => {
    expect(safeHref("https://example.com/jobs/1")).toBe("https://example.com/jobs/1");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
    expect(safeHref(null)).toBeNull();
  });
});

describe("hasEndpoint", () => {
  it("matches generated operations regardless of path-param names", () => {
    expect(hasEndpoint("GET", "/jobs/{job_id}")).toBe(true);
    expect(hasEndpoint("GET", "/jobs/{id}")).toBe(true);
    expect(hasEndpoint("DELETE", "/jobs/{}")).toBe(false);
  });
});

describe("isRuleBased", () => {
  it("treats heuristic model ids as rule-based", async () => {
    const { isRuleBased } = await import("./analysis");
    expect(isRuleBased("heuristic", "heuristic-v1")).toBe(true);
    expect(isRuleBased(null, null)).toBe(true);
    expect(isRuleBased("jd_extraction", "nvidia/nemotron")).toBe(false);
  });
});

describe("loginUrl", () => {
  it("keeps the expired notice and return path, but not for manual sign-out", async () => {
    const { loginUrl } = await import("./auth/auth-context");
    expect(loginUrl("expired", "/jobs/1")).toBe("/login?reason=expired&next=%2Fjobs%2F1");
    expect(loginUrl(null, "/dashboard")).toBe("/login?next=%2Fdashboard");
    expect(loginUrl("manual", "/dashboard")).toBe("/login");
    expect(loginUrl(null, "//evil.example")).toBe("/login");
  });
});

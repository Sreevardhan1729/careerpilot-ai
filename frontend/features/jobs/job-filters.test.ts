import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, activeFilterCount, filtersFromParams, filtersToParams, filtersToQuery } from "./job-filters";

describe("job filters", () => {
  it("round-trips through URL params", () => {
    const f = { ...EMPTY_FILTERS, q: "acme", work_mode: ["remote", "hybrid"], priority: ["excellent"], min_score: "70", saved: "true" as const };
    const back = filtersFromParams(filtersToParams(f));
    expect(back).toEqual(f);
  });

  it("maps to GET /jobs query params", () => {
    const q = filtersToQuery({ ...EMPTY_FILTERS, skills: "Python, FastAPI", source: "greenhouse", experience_max: "2", saved: "false" });
    expect(q.skills).toEqual(["Python", "FastAPI"]);
    expect(q.source).toEqual(["greenhouse"]);
    expect(q.experience_max).toBe(2);
    expect(q.saved).toBe(false);
    expect(q.q).toBeUndefined();
    expect(q.sort).toBe("-job_score");
  });

  it("ignores invalid sort and saved values from the URL", () => {
    const f = filtersFromParams(new URLSearchParams("sort=hack&saved=maybe"));
    expect(f.sort).toBe("-job_score");
    expect(f.saved).toBe("");
    expect(activeFilterCount(f)).toBe(0);
  });
});

import type { JobListParams } from "@/lib/endpoints";

/** Job Search filters <-> URL search params, so filtered views are linkable (e.g. from the dashboard). */
export interface JobFilters {
  q: string;
  role: string;
  location: string;
  work_mode: string[];
  experience_max: string;
  salary_min: string;
  source: string;
  skills: string;
  posted_after: string;
  min_score: string;
  priority: string[];
  saved: "" | "true" | "false";
  status: string;
  sort: string;
}

export const EMPTY_FILTERS: JobFilters = {
  q: "",
  role: "",
  location: "",
  work_mode: [],
  experience_max: "",
  salary_min: "",
  source: "",
  skills: "",
  posted_after: "",
  min_score: "",
  priority: [],
  saved: "",
  status: "",
  sort: "-job_score",
};

export const SORT_OPTIONS = [
  { value: "-job_score", label: "Job Score (high → low)" },
  { value: "-posted_at", label: "Posted (newest)" },
  { value: "-created_at", label: "Added (newest)" },
  { value: "company", label: "Company (A → Z)" },
];

const ARRAY_KEYS = ["work_mode", "priority"] as const;

function list(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function filtersFromParams(params: URLSearchParams): JobFilters {
  const f: JobFilters = { ...EMPTY_FILTERS, work_mode: [], priority: [] };
  for (const key of Object.keys(EMPTY_FILTERS) as (keyof JobFilters)[]) {
    if ((ARRAY_KEYS as readonly string[]).includes(key)) {
      (f[key] as string[]) = params.getAll(key).flatMap(list);
    } else {
      const v = params.get(key);
      if (v !== null) (f[key] as string) = v;
    }
  }
  if (!["", "true", "false"].includes(f.saved)) f.saved = "";
  if (!SORT_OPTIONS.some((o) => o.value === f.sort)) f.sort = EMPTY_FILTERS.sort;
  return f;
}

export function filtersToParams(f: JobFilters): URLSearchParams {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(f)) {
    if (Array.isArray(value)) value.forEach((v) => p.append(key, v));
    else if (value && !(key === "sort" && value === EMPTY_FILTERS.sort)) p.set(key, value);
  }
  return p;
}

function num(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

/** Maps UI filters to GET /jobs query params. */
export function filtersToQuery(f: JobFilters): JobListParams {
  return {
    q: f.q.trim() || undefined,
    role: f.role.trim() || undefined,
    location: f.location.trim() || undefined,
    work_mode: f.work_mode.length ? f.work_mode : undefined,
    experience_max: num(f.experience_max),
    salary_min: num(f.salary_min),
    source: f.source ? list(f.source) : undefined,
    skills: f.skills ? list(f.skills) : undefined,
    posted_after: f.posted_after || undefined,
    min_score: num(f.min_score),
    priority: f.priority.length ? f.priority : undefined,
    saved: f.saved === "" ? undefined : f.saved === "true",
    status: f.status || undefined,
    sort: f.sort || undefined,
  };
}

export function activeFilterCount(f: JobFilters): number {
  return Object.entries(f).filter(([k, v]) => k !== "sort" && (Array.isArray(v) ? v.length > 0 : Boolean(v))).length;
}

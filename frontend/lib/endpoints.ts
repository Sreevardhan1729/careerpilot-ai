/**
 * Typed functions for every backend endpoint the UI uses (paths are relative to NEXT_PUBLIC_API_BASE_URL, i.e. /api/v1).
 * Approve / start-work POSTs take an idempotency key; callers create one per user action with newIdempotencyKey().
 */
import { apiJson, apiJsonWithStatus, apiRequest, type QueryParams } from "./api";
import type { TailoredVersionPayload } from "@/features/resumes/tailored";
import type {
  Accepted,
  ActivationOut,
  AgentRunOut,
  AnalyzeTextIn,
  ApplicationOut,
  ApplicationPatch,
  ApprovalOut,
  ApproveIn,
  ConfirmSubmissionIn,
  DashboardSummary,
  Deduplicated,
  DownloadOut,
  FactCreate,
  FactOut,
  FactUpdate,
  JobDetail,
  JobListItem,
  JobPatch,
  JobPeopleOut,
  MatchesOut,
  MeOut,
  NotificationOut,
  OkOut,
  OutreachDraftIn,
  OutreachGenerateIn,
  OutreachOut,
  OutreachPatch,
  PersonIn,
  PersonOut,
  PersonPatch,
  PrepareIn,
  ProfileOut,
  ProfileUpdate,
  ResumeDetail,
  ResumeOut,
  ResumeParsed,
  ResumePatch,
  SchedulerRunIn,
  SearchConfigIn,
  SearchConfigOut,
  SearchConfigPatch,
  SettingsIn,
  SettingsOut,
  SourceIn,
  SourceOut,
  SourcePatch,
  TailoredVersionOut,
  TokenOut,
} from "@/types/models";

/** GET /scheduler/runs (backend/app/api/v1/discovery.py). */
export interface SchedulerRunsOut {
  runs: { id: string; workflow_name: string; status: string; created_at: string; completed_at: string | null; output: Record<string, unknown> | null }[];
  crawl_runs: {
    id: string;
    source: string;
    status: string;
    found: number | null;
    new: number | null;
    merged: number | null;
    filtered_out: number | null;
    errors: unknown;
    created_at: string;
  }[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export type AnalyzeResult = { kind: "accepted"; run: Accepted } | { kind: "deduplicated"; jobId: string };

function analyzeResult(res: { status: number; data: Accepted | Deduplicated }): AnalyzeResult {
  const data = res.data as Partial<Accepted & Deduplicated>;
  if (res.status === 200 && data.deduplicated && data.job_id) return { kind: "deduplicated", jobId: data.job_id };
  return { kind: "accepted", run: res.data as Accepted };
}

/** A 202 (new work) or a 200 replay of existing results (e.g. re-match with no changes). */
export type MaybeAccepted<T> = { kind: "accepted"; run: Accepted } | { kind: "existing"; data: T };

function maybeAccepted<T>(res: { status: number; data: unknown }): MaybeAccepted<T> {
  if (res.status === 202) return { kind: "accepted", run: res.data as Accepted };
  const d = res.data as Partial<Accepted>;
  if (d && typeof d === "object" && typeof d.workflow_id === "string") return { kind: "accepted", run: d as Accepted };
  return { kind: "existing", data: res.data as T };
}

export interface JobListParams extends QueryParams {
  q?: string;
  role?: string;
  company_id?: string;
  location?: string;
  work_mode?: string[];
  experience_max?: number;
  experience_known?: boolean;
  salary_min?: number;
  salary_disclosed?: boolean;
  source?: string[];
  skills?: string[];
  posted_after?: string;
  min_score?: number;
  priority?: string[];
  status?: string;
  saved?: boolean;
  sort?: string;
  limit?: number;
  cursor?: string;
}

export const api = {
  // ---------------------------------------------------------------------------------------------- auth / me
  devLogin: (email: string) => apiJson<TokenOut>("/dev/login", { method: "POST", json: { email }, auth: false }),
  me: () => apiJson<MeOut>("/me"),

  // ---------------------------------------------------------------------------------------------- profile
  profile: {
    get: () => apiJson<ProfileOut>("/profile"),
    put: (body: ProfileUpdate) => apiJson<ProfileOut>("/profile", { method: "PUT", json: body }),
    facts: (params?: { fact_type?: string; status?: string }) => apiJson<FactOut[]>("/profile/facts", { query: params }),
    addFact: (body: FactCreate) => apiJson<FactOut>("/profile/facts", { method: "POST", json: body }),
    patchFact: (id: string, body: FactUpdate) => apiJson<FactOut>(`/profile/facts/${id}`, { method: "PATCH", json: body }),
    deleteFact: (id: string) => apiJson<OkOut>(`/profile/facts/${id}`, { method: "DELETE" }),
  },

  searchConfigs: {
    list: () => apiJson<SearchConfigOut[]>("/search-configs"),
    create: (body: SearchConfigIn) => apiJson<SearchConfigOut>("/search-configs", { method: "POST", json: body }),
    patch: (id: string, body: SearchConfigPatch) =>
      apiJson<SearchConfigOut>(`/search-configs/${id}`, { method: "PATCH", json: body }),
    delete: (id: string) => apiJson<OkOut>(`/search-configs/${id}`, { method: "DELETE" }),
  },

  settings: {
    get: () => apiJson<SettingsOut>("/settings"),
    put: (body: SettingsIn) => apiJson<SettingsOut>("/settings", { method: "PUT", json: body }),
  },

  dashboard: () => apiJson<DashboardSummary>("/dashboard/summary"),

  // ---------------------------------------------------------------------------------------------- runs / notifications
  runs: {
    get: (id: string, signal?: AbortSignal) => apiJson<AgentRunOut>(`/agent-runs/${id}`, { signal }),
    list: (params?: { status?: string; workflow_name?: string; limit?: number }) =>
      apiJson<AgentRunOut[]>("/agent-runs", { query: params }),
    retry: (id: string, idempotencyKey: string) =>
      apiJson<Accepted>(`/agent-runs/${id}/retry`, { method: "POST", idempotencyKey }),
  },

  notifications: {
    list: (params?: { unread?: boolean }) => apiJson<NotificationOut[]>("/notifications", { query: params }),
    markRead: (id: string) => apiJson<OkOut>(`/notifications/${id}/read`, { method: "POST" }),
  },

  // ---------------------------------------------------------------------------------------------- jobs
  jobs: {
    list: (params: JobListParams) => apiJson<Page<JobListItem>>("/jobs", { query: params }),
    get: (id: string) => apiJson<JobDetail>(`/jobs/${id}`),
    patch: (id: string, body: JobPatch) => apiJson<JobListItem>(`/jobs/${id}`, { method: "PATCH", json: body }),
    matches: (id: string) => apiJson<MatchesOut>(`/jobs/${id}/matches`),
    analyzeText: async (body: AnalyzeTextIn, idempotencyKey: string) =>
      analyzeResult(
        await apiJsonWithStatus<Accepted | Deduplicated>("/jobs/analyze", { method: "POST", json: body, idempotencyKey }),
      ),
    analyzeUrl: async (url: string, idempotencyKey: string) =>
      analyzeResult(
        await apiJsonWithStatus<Accepted | Deduplicated>("/jobs/analyze-url", {
          method: "POST",
          json: { url },
          idempotencyKey,
        }),
      ),
    analyzeFile: async (file: File, sourceUrl: string | undefined, idempotencyKey: string) => {
      const form = new FormData();
      form.append("file", file);
      if (sourceUrl) form.append("source_url", sourceUrl);
      return analyzeResult(
        await apiJsonWithStatus<Accepted | Deduplicated>("/jobs/analyze-file", { method: "POST", form, idempotencyKey }),
      );
    },
    discover: (body: { source_ids?: string[] | null }, idempotencyKey: string) =>
      apiJson<Accepted>("/jobs/discover", { method: "POST", json: body, idempotencyKey }),
  },

  // ---------------------------------------------------------------------------------------------- resumes
  resumes: {
    list: () => apiJson<ResumeOut[]>("/resumes"),
    get: (id: string) => apiJson<ResumeDetail>(`/resumes/${id}`),
    upload: (file: File, label: string | undefined, idempotencyKey: string) => {
      const form = new FormData();
      form.append("file", file);
      if (label) form.append("label", label);
      return apiJson<Accepted>("/resumes/upload", { method: "POST", form, idempotencyKey });
    },
    patch: (id: string, body: ResumePatch) => apiJson<ResumeOut>(`/resumes/${id}`, { method: "PATCH", json: body }),
    putParsed: (id: string, versionId: string, body: ResumeParsed) =>
      apiJson<ResumeDetail>(`/resumes/${id}/versions/${versionId}/parsed-data`, { method: "PUT", json: body }),
    /** Either a signed URL to open, or the file itself. */
    download: async (id: string, versionId: string, fallbackFilename = "resume"): Promise<{ kind: "url"; url: string; filename: string } | { kind: "blob"; blob: Blob; filename: string }> => {
      const res = await apiRequest(`/resumes/${id}/versions/${versionId}/download`);
      const type = res.headers.get("Content-Type") ?? "";
      if (type.includes("application/json")) {
        const data = (await res.json()) as DownloadOut;
        if (data.url) return { kind: "url", url: data.url, filename: data.filename };
        throw new Error("The server did not return a download link.");
      }
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = /filename="?([^";]+)"?/i.exec(disposition);
      // Content-Disposition is only readable cross-origin if the API exposes it, so fall back to the known filename.
      return { kind: "blob", blob: await res.blob(), filename: match?.[1] ?? fallbackFilename };
    },
    delete: (id: string) => apiJson<OkOut>(`/resumes/${id}`, { method: "DELETE" }),
    /** Create a tailored DOCX version (pending approval) from text changes and/or a skill order. */
    createVersion: (id: string, body: TailoredVersionPayload) =>
      apiJson<TailoredVersionOut>(`/resumes/${id}/versions`, { method: "POST", json: body }),
    activateVersion: (id: string, versionId: string, body: ApproveIn, idempotencyKey: string) =>
      apiJson<ActivationOut>(`/resumes/${id}/versions/${versionId}/activate`, { method: "POST", json: body, idempotencyKey }),
    /** Improvement suggestions for this resume against a job (202; result in run.output.improvement). */
    optimize: (id: string, jobId: string, idempotencyKey: string) =>
      apiJson<Accepted>(`/resumes/${id}/optimize`, { method: "POST", query: { job_id: jobId }, idempotencyKey }),
    match: async (jobId: string, idempotencyKey: string, force = false) =>
      maybeAccepted<unknown>(
        await apiJsonWithStatus(`/resumes/match/${jobId}`, {
          method: "POST",
          query: force ? { force: true } : undefined,
          idempotencyKey,
        }),
      ),
  },

  // ---------------------------------------------------------------------------------------------- people
  people: {
    forJob: (jobId: string) => apiJson<JobPeopleOut>(`/jobs/${jobId}/people`),
    discover: (jobId: string, idempotencyKey: string) =>
      apiJson<Accepted>(`/jobs/${jobId}/people/discover`, { method: "POST", idempotencyKey }),
    list: (params?: { company_id?: string; contact_status?: string; limit?: number; cursor?: string }) =>
      apiJson<PersonOut[] | Page<PersonOut>>("/people", { query: params }),
    create: (body: PersonIn) => apiJson<PersonOut>("/people", { method: "POST", json: body }),
    patch: (id: string, body: PersonPatch) => apiJson<PersonOut>(`/people/${id}`, { method: "PATCH", json: body }),
  },

  // ---------------------------------------------------------------------------------------------- outreach
  outreach: {
    createDraft: (body: OutreachDraftIn) => apiJson<OutreachOut>("/outreach/drafts", { method: "POST", json: body }),
    generate: (body: OutreachGenerateIn, idempotencyKey: string) =>
      apiJson<Accepted>("/outreach/generate", { method: "POST", json: body, idempotencyKey }),
    list: (params?: { job_id?: string; status?: string; limit?: number; cursor?: string }) =>
      apiJson<OutreachOut[] | Page<OutreachOut>>("/outreach", { query: params }),
    patch: (id: string, body: OutreachPatch) => apiJson<OutreachOut>(`/outreach/${id}`, { method: "PATCH", json: body }),
    gmailDraft: (id: string, idempotencyKey: string) =>
      apiJson<OutreachOut | Record<string, unknown>>(`/outreach/${id}/gmail-draft`, { method: "POST", idempotencyKey }),
    requestApproval: (id: string, idempotencyKey: string) =>
      apiJson<ApprovalOut>(`/outreach/${id}/request-approval`, { method: "POST", idempotencyKey }),
    approve: (id: string, body: ApproveIn, idempotencyKey: string) =>
      apiJson<{ status: string; gmail_message_id?: string; sent_at?: string }>(`/outreach/${id}/approve`, {
        method: "POST",
        json: body,
        idempotencyKey,
      }),
    markSent: (id: string, idempotencyKey: string) =>
      apiJson<OutreachOut>(`/outreach/${id}/mark-sent`, { method: "POST", idempotencyKey }),
  },

  approvals: {
    list: (params?: { status?: string }) => apiJson<ApprovalOut[] | Page<ApprovalOut>>("/approvals", { query: params }),
    reject: (id: string) => apiJson<OkOut>(`/approvals/${id}/reject`, { method: "POST" }),
  },

  // ---------------------------------------------------------------------------------------------- applications
  applications: {
    list: (params?: { status?: string; limit?: number; cursor?: string }) =>
      apiJson<ApplicationOut[] | Page<ApplicationOut>>("/applications", { query: params }),
    prepare: (body: PrepareIn, idempotencyKey: string) =>
      apiJson<Accepted>("/applications/prepare", { method: "POST", json: body, idempotencyKey }),
    patch: (id: string, body: ApplicationPatch) =>
      apiJson<ApplicationOut>(`/applications/${id}`, { method: "PATCH", json: body }),
    approve: (id: string, body: ApproveIn, idempotencyKey: string) =>
      apiJson<ApplicationOut | Record<string, unknown>>(`/applications/${id}/approve`, {
        method: "POST",
        json: body,
        idempotencyKey,
      }),
    confirmSubmission: (id: string, body: ConfirmSubmissionIn, idempotencyKey: string) =>
      apiJson<ApplicationOut>(`/applications/${id}/confirm-submission`, { method: "POST", json: body, idempotencyKey }),
  },

  // ---------------------------------------------------------------------------------------------- sources / scheduler
  sources: {
    list: () => apiJson<SourceOut[] | Page<SourceOut>>("/sources"),
    create: (body: SourceIn) => apiJson<SourceOut>("/sources", { method: "POST", json: body }),
    patch: (id: string, body: SourcePatch) => apiJson<SourceOut>(`/sources/${id}`, { method: "PATCH", json: body }),
    delete: (id: string) => apiJson<OkOut>(`/sources/${id}`, { method: "DELETE" }),
    healthCheck: (id: string, idempotencyKey: string) =>
      apiJson<Record<string, unknown>>(`/sources/${id}/health-check`, { method: "POST", idempotencyKey }),
  },

  scheduler: {
    /** 202 = a new daily run was queued; 200 = the run for that date already exists (same envelope). */
    run: async (body: SchedulerRunIn, idempotencyKey: string) => {
      const res = await apiJsonWithStatus<Accepted>("/scheduler/run", { method: "POST", json: body, idempotencyKey });
      return { run: res.data, existing: res.status === 200 };
    },
    runs: () => apiJson<SchedulerRunsOut>("/scheduler/runs"),
  },

  // ---------------------------------------------------------------------------------------------- integrations / account
  integrations: {
    list: () => apiJson<Record<string, unknown>>("/integrations"),
    googleAuthorize: () => apiJson<{ url: string }>("/integrations/google/authorize"),
    googleDisconnect: () => apiJson<OkOut | Record<string, unknown>>("/integrations/google", { method: "DELETE" }),
  },

  account: {
    export: (idempotencyKey: string) => apiJson<Accepted>("/account/export", { method: "POST", idempotencyKey }),
    /** The ZIP needs the bearer token, so it is fetched as a blob rather than linked. */
    downloadExport: async (runId: string) => {
      const res = await apiRequest(`/account/exports/${runId}`);
      return { blob: await res.blob(), filename: `careerpilot-export-${runId}.zip` };
    },
    delete: () => apiJson<OkOut | Record<string, unknown>>("/account", { method: "DELETE", json: { confirm: "DELETE" } }),
  },
};

/** List endpoints for Phase 2+ may return a bare array or a cursor page; accept both. */
export function itemsOf<T>(value: T[] | Page<T> | null | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value) ? value : (value.items ?? []);
}

export function nextCursorOf<T>(value: T[] | Page<T> | null | undefined): string | null {
  return value && !Array.isArray(value) ? (value.next_cursor ?? null) : null;
}

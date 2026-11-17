/**
 * Domain types for the UI.
 *
 * Generated types (types/api.d.ts, from the backend's OpenAPI via `pnpm gen:api`) are authoritative.
 * Models whose routes are not in the OpenAPI document yet are hand-written from
 * backend/app/schemas/api/__init__.py and used as a fallback through `Gen<>`: as soon as the backend
 * exposes the schema, the generated type takes over automatically and any drift shows up as a type error.
 */
import type { components } from "./api";

type Schemas = components["schemas"];
type Gen<K extends string, Fallback> = K extends keyof Schemas ? Schemas[K] : Fallback;

// ------------------------------------------------------------------------------------------------ generated today
export type Accepted = Schemas["Accepted"];
export type Deduplicated = Schemas["Deduplicated"];
export type OkOut = Schemas["OkOut"];
export type TokenOut = Schemas["TokenOut"];
export type MeOut = Schemas["MeOut"];
export type ProfileOut = Schemas["ProfileOut"];
export type ProfileUpdate = Schemas["ProfileUpdate"];
export type SalaryPreference = Schemas["SalaryPreference"];
export type FactOut = Schemas["FactOut"];
export type FactCreate = Schemas["FactCreate"];
export type FactUpdate = Schemas["FactUpdate"];
export type SearchConfigOut = Schemas["SearchConfigOut"];
export type SearchConfigIn = Schemas["SearchConfigIn"];
export type SearchConfigPatch = Schemas["SearchConfigPatch"];
export type SettingsOut = Schemas["SettingsOut"];
export type SettingsIn = Schemas["SettingsIn"];
export type AnalyzeTextIn = Schemas["AnalyzeTextIn"];
export type ManualFields = Schemas["ManualFields"];
export type JobListItem = Schemas["JobListItem"];
export type JobDetail = Schemas["JobDetail"];
export type JobSkillOut = Schemas["JobSkillOut"];
export type JobEvidenceOut = Schemas["JobEvidenceOut"];
export type JobPatch = Schemas["JobPatch"];
export type SalaryOut = Schemas["SalaryOut"];
export type ExperienceOut = Schemas["ExperienceOut"];
export type CompanyOut = Schemas["CompanyOut"];
export type MatchesOut = Schemas["MatchesOut"];
export type MatchItem = Schemas["MatchItem"];
export type ComponentOut = Schemas["ComponentOut"];
export type ResumeOut = Schemas["ResumeOut"];
export type ResumeDetail = Schemas["ResumeDetail"];
export type ResumeVersionOut = Schemas["ResumeVersionOut"];
export type ResumePatch = Schemas["ResumePatch"];
export type ResumeParsed = Schemas["ResumeParsed"];
export type ResumeSkill = Schemas["ResumeSkill"];
export type ResumeExperience = Schemas["ResumeExperience"];
export type ResumeProject = Schemas["ResumeProject"];
export type ResumeEducation = Schemas["ResumeEducation"];
export type AgentRunOut = Schemas["AgentRunOut"];
export type RunRef = Schemas["RunRef"];
export type NotificationOut = Schemas["NotificationOut"];

export interface TailoredVersionOutManual {
  version: ResumeVersionOut;
  approval: ApprovalOut;
}
export type TailoredVersionOut = Gen<"TailoredVersionOut", TailoredVersionOutManual>;
export type ActivationOut = Gen<"ActivationOut", { status: string; current_version_id: string }>;

export interface OutreachDraftInManual {
  job_id?: string | null;
  person_id?: string | null;
  message_type: MessageType;
  subject?: string | null;
  body: string;
}
export type OutreachDraftIn = Gen<"OutreachDraftIn", OutreachDraftInManual>;

/** Download either returns `{url, filename}` (signed URL storage) or the file bytes. */
export type DownloadOut = Gen<"DownloadOut", { url: string | null; filename: string }>;

// ------------------------------------------------------------------------------------------------ people (Phase 2)
export interface EvidenceItemOutManual {
  id: string;
  source_type: string;
  source_url: string;
  source_title: string | null;
  snippet: string;
  retrieved_at: string;
}
export type EvidenceItemOut = Gen<"EvidenceItemOut", EvidenceItemOutManual>;

export interface JobPersonOutManual {
  rank: number;
  person_id: string;
  name: string;
  designation: string | null;
  department: string | null;
  role_category: string;
  linkedin_url: string | null;
  public_email: string | null;
  association_status: string;
  relevance_score: number;
  components: Record<string, unknown>;
  relevance_reason: string;
  confidence: number | null;
  evidence: EvidenceItemOut[];
  contact_status: string;
  outreach_count: number;
}
export type JobPersonOut = Gen<"JobPersonOut", JobPersonOutManual>;

export interface JobPeopleOutManual {
  job_id: string;
  company: CompanyOut | null;
  verified_count: number;
  unavailable_count: number;
  target?: number;
  coverage_note: string | null;
  items: JobPersonOut[];
  latest_run: RunRef | null;
}
export type JobPeopleOut = Gen<"JobPeopleOut", JobPeopleOutManual>;

export interface PersonOutManual {
  id: string;
  name: string;
  designation: string | null;
  department: string | null;
  company?: CompanyOut | null;
  linkedin_url: string | null;
  public_email: string | null;
  association_status: string;
  contact_status: string;
  added_by: string;
  notes: string | null;
  first_discovered_at: string;
  last_verified_at: string | null;
}
export type PersonOut = Gen<"PersonOut", PersonOutManual>;

export interface PersonInManual {
  name: string;
  linkedin_url?: string | null;
  designation?: string | null;
  company?: string | null;
  job_id?: string | null;
  notes?: string | null;
}
export type PersonIn = Gen<"PersonIn", PersonInManual>;

export type ContactStatus = "new" | "contacted" | "responded" | "do_not_contact";
export interface PersonPatchManual {
  contact_status?: ContactStatus | null;
  notes?: string | null;
  designation?: string | null;
}
export type PersonPatch = Gen<"PersonPatch", PersonPatchManual>;

// ------------------------------------------------------------------------------------------------ outreach / approvals (Phase 3)
export type MessageType =
  | "linkedin_connection"
  | "linkedin_follow_up"
  | "referral_request"
  | "hiring_manager_message"
  | "recruiter_email"
  | "recruiter_follow_up"
  | "thank_you";

export interface OutreachGenerateInManual {
  job_id: string;
  person_ids?: string[] | null;
  message_types?: MessageType[];
  resume_id?: string | null;
}
export type OutreachGenerateIn = Gen<"OutreachGenerateIn", OutreachGenerateInManual>;

export interface OutreachPatchManual {
  subject?: string | null;
  body?: string | null;
  discard?: boolean | null;
}
export type OutreachPatch = Gen<"OutreachPatch", OutreachPatchManual>;

export interface OutreachOutManual {
  id: string;
  job_id: string | null;
  person_id: string | null;
  message_type: string;
  channel: string;
  recipient_name: string | null;
  recipient_email: string | null;
  subject: string | null;
  body: string;
  recommended_resume_id: string | null;
  personalization_evidence: unknown[];
  claim_check: Record<string, unknown>;
  requires_review: boolean;
  status: string;
  gmail_draft_id: string | null;
  sent_at: string | null;
  model_id: string | null;
  prompt_version: string | null;
  created_at: string;
  updated_at: string;
}
export type OutreachOut = Gen<"OutreachOut", OutreachOutManual>;

export interface ApprovalOutManual {
  approval_id: string;
  action_type: string;
  status: string;
  expires_at: string;
  payload_hash: string;
  payload_preview: Record<string, unknown>;
  reference_type: string;
  reference_id: string;
}
export type ApprovalOut = Gen<"ApprovalOut", ApprovalOutManual>;

export interface ApproveInManual {
  approval_id: string;
  payload_hash: string;
  confirm: true;
}
export type ApproveIn = Gen<"ApproveIn", ApproveInManual>;

// ------------------------------------------------------------------------------------------------ applications (Phase 5)
export interface PrepareInManual {
  job_id: string;
  resume_version_id?: string | null;
  questions?: string[] | null;
}
export type PrepareIn = Gen<"PrepareIn", PrepareInManual>;

export interface ApplicationPatchManual {
  status?: string | null;
  notes?: string | null;
  follow_up_date?: string | null;
}
export type ApplicationPatch = Gen<"ApplicationPatch", ApplicationPatchManual>;

export interface ConfirmSubmissionInManual {
  evidence_type: "external_receipt" | "user_attestation";
  detail: string;
}
export type ConfirmSubmissionIn = Gen<"ConfirmSubmissionIn", ConfirmSubmissionInManual>;

export interface ApplicationOutManual {
  id: string;
  job_id: string;
  job_title?: string | null;
  company_name?: string | null;
  resume_id: string | null;
  resume_version_id: string | null;
  application_url: string | null;
  status: string;
  submission_method: string | null;
  submitted_at: string | null;
  confirmation_evidence: Record<string, unknown> | null;
  answers: unknown[];
  preview: Record<string, unknown> | null;
  follow_up_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}
export type ApplicationOut = Gen<"ApplicationOut", ApplicationOutManual>;

// ------------------------------------------------------------------------------------------------ sources / scheduler (Phase 2)
export type SourceType = "greenhouse" | "lever" | "ashby" | "rss" | "career_page";
export interface SourceInManual {
  source_type: SourceType;
  identifier: string;
  name?: string | null;
  company_name?: string | null;
  enabled?: boolean;
  config?: Record<string, unknown>;
  terms_note?: string | null;
}
export type SourceIn = Gen<"SourceIn", SourceInManual>;

export interface SourcePatchManual {
  enabled?: boolean | null;
  name?: string | null;
  config?: Record<string, unknown> | null;
  rate_limit_per_minute?: number | null;
  terms_note?: string | null;
}
export type SourcePatch = Gen<"SourcePatch", SourcePatchManual>;

export interface SourceOutManual {
  id: string;
  source_type: string;
  name: string;
  identifier: string;
  enabled: boolean;
  config: Record<string, unknown>;
  rate_limit_per_minute: number;
  last_crawled_at: string | null;
  last_status: string | null;
  last_error: string | null;
  consecutive_failures: number;
  terms_reviewed_at: string | null;
  terms_note: string | null;
}
export type SourceOut = Gen<"SourceOut", SourceOutManual>;

export interface DiscoverInManual {
  source_ids?: string[] | null;
}
export type DiscoverIn = Gen<"DiscoverIn", DiscoverInManual>;

export interface SchedulerRunInManual {
  date?: string | null;
}
export type SchedulerRunIn = Gen<"SchedulerRunIn", SchedulerRunInManual>;

// ------------------------------------------------------------------------------------------------ untyped (dict) responses
/** GET /dashboard/summary returns a plain dict; shape from backend/app/services/dashboard.py. */
export interface DashboardSummary {
  jobs_total: number;
  jobs_new_today: number;
  matches: { excellent?: number; strong?: number; moderate?: number; low?: number };
  people_discovered: number;
  jobs_with_people?: number;
  outreach_awaiting_review: number;
  applications_submitted: number;
  follow_ups_due: { application_id: string; date: string; job_title?: string | null }[];
  scheduler: {
    last_run_at: string | null;
    last_status: string | null;
    next_run_at?: string | null;
    failed_sources?: number;
    stale?: boolean;
    last_run_id?: string | null;
  };
  latest_jobs: {
    id: string;
    title: string | null;
    company: string | null;
    job_score: number;
    priority: string | null;
    posted_at: string | null;
  }[];
  recent_failures: {
    workflow_id: string;
    workflow_name: string;
    error_code: string | null;
    message?: string | null;
    at: string;
  }[];
  llm_budget: { used_today: number; limit: number; provider?: string; model?: string };
}

/** Shapes inside `dict[str, Any]` fields, normalised by lib/shapes.ts. */
export interface ClaimViolation {
  code: string;
  severity: "blocking" | "warning" | string;
  detail: string;
}

export interface PersonalizationEvidence {
  fact: string;
  source: string | null;
  ref_id: string | null;
}

export interface RunProgressNode {
  node: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  detail: Record<string, unknown> | null;
  error: string | null;
}

export interface RunApproval {
  approval_id: string;
  action_type: string;
  payload_hash: string;
  payload_preview: Record<string, unknown>;
  expires_at: string | null;
}

/**
 * Normalisers for backend fields typed as `dict[str, Any]` / `list[Any]`. They never throw: unknown shapes degrade to
 * empty values so a backend change can't crash a page.
 */
import type { ClaimViolation, PersonalizationEvidence, RunApproval, RunProgressNode } from "@/types/models";
import { asArray, asNumber, asRecord, asString } from "./utils";

export function progressNodes(progress: unknown): RunProgressNode[] {
  return asArray(progress).map((raw) => {
    const p = asRecord(raw);
    const error = p.error;
    return {
      node: asString(p.node) ?? "step",
      status: asString(p.status) ?? "pending",
      started_at: asString(p.started_at),
      finished_at: asString(p.finished_at),
      detail: p.detail && typeof p.detail === "object" ? asRecord(p.detail) : null,
      error: typeof error === "string" ? error : error ? (asString(asRecord(error).message) ?? JSON.stringify(error)) : null,
    };
  });
}

/**
 * The backend appends a node entry when it starts and may not update it when it finishes. Derive what the user should
 * see: a node is done once a later node has started; the last node takes the run's outcome once the run is over.
 */
export function effectiveNodes(nodes: RunProgressNode[], runStatus: string | null | undefined): RunProgressNode[] {
  const terminal = ["completed", "partially_completed", "failed", "cancelled"].includes(runStatus ?? "");
  return nodes.map((n, i) => {
    if (n.status !== "running") return n;
    const isLast = i === nodes.length - 1;
    if (!isLast) return { ...n, status: "completed" };
    if (runStatus === "awaiting_approval") return { ...n, status: "awaiting_approval" };
    if (!terminal) return n;
    if (runStatus === "failed") return { ...n, status: "failed" };
    if (runStatus === "cancelled") return { ...n, status: "skipped" };
    return { ...n, status: "completed" };
  });
}

export function runApproval(value: unknown): RunApproval | null {
  const a = asRecord(value);
  const id = asString(a.approval_id);
  const hash = asString(a.payload_hash);
  if (!id || !hash) return null;
  return {
    approval_id: id,
    action_type: asString(a.action_type) ?? "external_action",
    payload_hash: hash,
    payload_preview: asRecord(a.payload_preview),
    expires_at: asString(a.expires_at),
  };
}

export function runError(value: unknown): { code: string | null; message: string | null; node: string | null } | null {
  if (!value) return null;
  const e = asRecord(value);
  return { code: asString(e.code), message: asString(e.message) ?? asString(e.detail), node: asString(e.node) };
}

export interface ScoreComponent {
  key: string;
  score: number | null;
  weight: number | null;
  explanation: string;
  detail: Record<string, unknown>;
  evidenceRefs: string[];
}

export function scoreComponents(components: unknown, order: string[]): ScoreComponent[] {
  const rec = asRecord(components);
  const keys = [...order.filter((k) => k in rec), ...Object.keys(rec).filter((k) => !order.includes(k))];
  return keys.map((key) => {
    const c = asRecord(rec[key]);
    return {
      key,
      score: asNumber(c.score),
      weight: asNumber(c.weight),
      explanation: asString(c.explanation) ?? "",
      detail: asRecord(c.detail),
      evidenceRefs: asArray(c.evidence_refs).map(String),
    };
  });
}

export interface JobScoreBreakdown {
  score: number | null;
  priority: string | null;
  components: ScoreComponent[];
  disqualifiers: string[];
  limitations: string[];
  salaryKnown: boolean | null;
  recent: boolean | null;
  experienceEligible: boolean | null;
  disclaimer: string;
}

export const JOB_SCORE_ORDER = ["M", "F", "E_elig", "L", "S"];
export const JOB_SCORE_LABELS: Record<string, string> = {
  M: "Resume match (M)",
  F: "Freshness (F)",
  E_elig: "Experience eligibility (E_elig)",
  L: "Location fit (L)",
  S: "Salary fit (S)",
};

export const MATCH_ORDER = ["K", "P", "E_rel", "R", "D"];
export const MATCH_LABELS: Record<string, string> = {
  K: "Skill coverage (K)",
  P: "Project relevance (P)",
  E_rel: "Relevant experience (E_rel)",
  R: "Responsibility fit (R)",
  D: "Domain fit (D)",
};

export const PEOPLE_LABELS: Record<string, string> = {
  T: "Role priority (T)",
  D: "Department fit (D)",
  C: "Confidence (C)",
  S: "Source strength (S)",
};

function bool(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

export function jobScoreBreakdown(value: unknown): JobScoreBreakdown | null {
  if (!value || typeof value !== "object") return null;
  const b = asRecord(value);
  if (!Object.keys(asRecord(b.components)).length && asNumber(b.score) === null) return null;
  return {
    score: asNumber(b.score),
    priority: asString(b.priority),
    components: scoreComponents(b.components, JOB_SCORE_ORDER),
    disqualifiers: asArray(b.disqualifiers).map((d) => asString(d) ?? JSON.stringify(d)),
    limitations: asArray(b.limitations).map((d) => asString(d) ?? JSON.stringify(d)),
    salaryKnown: bool(b.salary_known),
    recent: bool(b.recent),
    experienceEligible: bool(b.experience_eligible),
    disclaimer:
      asString(b.disclaimer) ?? "Job Score is a prioritisation heuristic, not a probability of being shortlisted.",
  };
}

export type SkillStatus = "strong" | "listed_only" | "related" | "profile_only" | "no_evidence" | "confirmed_missing";

export interface SkillBreakdownItem {
  skill: string;
  importance: string;
  status: SkillStatus | string;
  evidenceRefs: string[];
}

export function skillBreakdown(value: unknown): SkillBreakdownItem[] {
  return asArray(value).map((raw) => {
    const b = asRecord(raw);
    return {
      skill: asString(b.skill) ?? asString(b.name) ?? "?",
      importance: asString(b.importance) ?? "mentioned",
      status: asString(b.status) ?? "no_evidence",
      evidenceRefs: asArray(b.evidence_refs).map(String),
    };
  });
}

export interface RelevantItem {
  ref: string | null;
  title: string;
  score: number | null;
  matchedSkills: string[];
}

export function relevantItems(value: unknown): RelevantItem[] {
  return asArray(value).map((raw) => {
    const r = asRecord(raw);
    return {
      ref: asString(r.ref),
      title: asString(r.title) ?? asString(r.company) ?? asString(r.ref) ?? "Untitled",
      score: asNumber(r.score),
      matchedSkills: asArray(r.matched_skills).map(String),
    };
  });
}

export interface Suggestions {
  summary: string | null;
  bulletRewrites: { before: string; after: string; evidenceRefs: string[] }[];
  missingEvidence: string[];
  skillOrder: string[];
  keywords: string[];
  other: string[];
}

export function suggestions(value: unknown): Suggestions | null {
  if (!value || typeof value !== "object") return null;
  const s = asRecord(value);
  const rewrites = asArray(s.bullet_rewrites).map((raw) => {
    const r = asRecord(raw);
    return { before: asString(r.before) ?? "", after: asString(r.after) ?? "", evidenceRefs: asArray(r.evidence_refs).map(String) };
  });
  const textList = (v: unknown) =>
    asArray(v)
      .map((x) => asString(x) ?? asString(asRecord(x).skill) ?? asString(asRecord(x).text))
      .filter((x): x is string => !!x);
  return {
    summary: asString(s.summary),
    bulletRewrites: rewrites.filter((r) => r.after),
    missingEvidence: textList(s.missing_evidence),
    skillOrder: textList(s.skill_order),
    keywords: textList(s.keywords_to_highlight),
    other: textList(s.items ?? s.tips),
  };
}

export function claimCheck(value: unknown): { passed: boolean | null; blocking: ClaimViolation[]; warnings: ClaimViolation[] } {
  const c = asRecord(value);
  const violations = asArray(c.violations).map((raw) => {
    const v = asRecord(raw);
    return { code: asString(v.code) ?? "check", severity: asString(v.severity) ?? "warning", detail: asString(v.detail) ?? "" };
  });
  return {
    passed: bool(c.passed),
    blocking: violations.filter((v) => v.severity === "blocking"),
    warnings: violations.filter((v) => v.severity !== "blocking"),
  };
}

export function personalizationEvidence(value: unknown): PersonalizationEvidence[] {
  return asArray(value).map((raw) => {
    if (typeof raw === "string") return { fact: raw, source: null, ref_id: null };
    const e = asRecord(raw);
    // Documented as {fact, source, ref_id}; the backend currently sends {id, kind, text}. Accept both.
    return {
      fact: asString(e.fact) ?? asString(e.text) ?? asString(e.snippet) ?? JSON.stringify(e),
      source: asString(e.source) ?? asString(e.kind),
      ref_id: asString(e.ref_id) ?? asString(e.id),
    };
  });
}

export function locationLabels(locations: unknown): string[] {
  return asArray(locations)
    .map((raw) => {
      if (typeof raw === "string") return raw;
      const l = asRecord(raw);
      const raw_ = asString(l.raw);
      if (raw_) return raw_;
      return [asString(l.city), asString(l.region), asString(l.country)].filter(Boolean).join(", ") || (l.remote ? "Remote" : "");
    })
    .filter(Boolean);
}

export interface ApplicationAnswer {
  question: string;
  answer: string | null;
  sourceFactIds: string[];
  needsUserInput: boolean;
}

export interface ApplicationPreview {
  resumeVersion: Record<string, unknown>;
  answers: ApplicationAnswer[];
  submissionMethod: string | null;
  manualSteps: string[];
  applicationUrl: string | null;
}

export function applicationAnswers(value: unknown): ApplicationAnswer[] {
  return asArray(value).map((raw) => {
    const a = asRecord(raw);
    return {
      question: asString(a.question) ?? "Question",
      answer: asString(a.answer),
      sourceFactIds: asArray(a.source_fact_ids).map(String),
      needsUserInput: a.needs_user_input === true || !asString(a.answer),
    };
  });
}

export function applicationPreview(value: unknown): ApplicationPreview | null {
  if (!value || typeof value !== "object") return null;
  const p = asRecord(value);
  return {
    resumeVersion: asRecord(p.resume_version),
    answers: applicationAnswers(p.answers),
    submissionMethod: asString(p.submission_method),
    manualSteps: asArray(p.manual_steps).map((s) => asString(s) ?? JSON.stringify(s)),
    applicationUrl: asString(p.application_url),
  };
}

export function parseWarnings(value: unknown): string[] {
  return asArray(value).map((w) => asString(w) ?? asString(asRecord(w).message) ?? JSON.stringify(w));
}

export interface ImprovementChange {
  section: string;
  before: string | null;
  after: string;
  evidenceRefs: string[];
  reason: string | null;
  rejected: { code: string; detail: string }[];
}

export interface Improvement {
  updatedSummary: string | null;
  suggestedChanges: ImprovementChange[];
  droppedChanges: ImprovementChange[];
  keywords: string[];
  missingEvidence: string[];
  skillOrder: string[];
  method: string | null;
}

function improvementChanges(value: unknown): ImprovementChange[] {
  return asArray(value)
    .map((raw) => {
      const c = asRecord(raw);
      return {
        section: asString(c.section) ?? "experience",
        before: asString(c.before),
        after: asString(c.after) ?? "",
        evidenceRefs: asArray(c.evidence_refs).map(String),
        reason: asString(c.reason),
        rejected: asArray(c.rejected).map((v) => ({ code: asString(asRecord(v).code) ?? "violation", detail: asString(asRecord(v).detail) ?? "" })),
      };
    })
    .filter((c) => c.after);
}

/** `output.improvement` from POST /resumes/{id}/optimize (also persisted at matches.items[].suggestions.improvement). */
export function improvement(value: unknown): Improvement | null {
  if (!value || typeof value !== "object") return null;
  const i = asRecord(value);
  const list = (v: unknown) => asArray(v).map((x) => asString(x)).filter((x): x is string => !!x);
  return {
    updatedSummary: asString(i.updated_summary),
    suggestedChanges: improvementChanges(i.suggested_changes),
    droppedChanges: improvementChanges(i.dropped_changes),
    keywords: list(i.keywords_to_highlight),
    missingEvidence: list(i.missing_evidence),
    skillOrder: list(i.skill_order),
    method: asString(i.method),
  };
}

/**
 * Tailored resume versions (POST /resumes/{id}/versions): pure helpers for the form, so payload building and
 * server-error parsing are unit-testable.
 */
import { isApiError } from "@/lib/api";
import { asArray, asRecord, asString } from "@/lib/utils";
import type { EditableParsed } from "./parsed";

export interface VersionChange {
  section: string;
  before: string;
  after: string;
  evidence_refs?: string[];
}

export interface TailoredVersionPayload {
  job_id: string | null;
  base_version_id: string | null;
  changes: VersionChange[];
  skill_order: string[] | null;
  change_summary: string | null;
}

/** An existing piece of resume text that a change may replace (the server matches `before` exactly). */
export interface EditableText {
  key: string;
  section: string;
  label: string;
  text: string;
}

const clip = (s: string, n = 70) => (s.length > n ? `${s.slice(0, n).trimEnd()}…` : s);

/** Every text the backend accepts as `before`: summary, experience/project bullets, project descriptions, achievements. */
export function editableTexts(parsed: EditableParsed): EditableText[] {
  const out: EditableText[] = [];
  if (parsed.summary?.trim()) out.push({ key: "summary", section: "summary", label: `Summary: ${clip(parsed.summary)}`, text: parsed.summary });
  parsed.experience.forEach((e, i) => {
    const owner = e.title || e.company || `Experience ${i + 1}`;
    (e.bullets ?? []).forEach((b, j) => {
      if (b.trim()) out.push({ key: `experience[${i}]#${j}`, section: "experience", label: `${owner}: ${clip(b)}`, text: b });
    });
  });
  parsed.projects.forEach((p, i) => {
    const owner = p.title || `Project ${i + 1}`;
    if (p.description?.trim()) out.push({ key: `projects[${i}].description`, section: "project", label: `${owner} (description): ${clip(p.description)}`, text: p.description });
    (p.bullets ?? []).forEach((b, j) => {
      if (b.trim()) out.push({ key: `projects[${i}]#${j}`, section: "project", label: `${owner}: ${clip(b)}`, text: b });
    });
  });
  parsed.achievements.forEach((a, i) => {
    if (a.text.trim()) out.push({ key: `achievements[${i}]`, section: "achievement", label: `Achievement: ${clip(a.text)}`, text: a.text });
  });
  return out;
}

/** The resume's skills, in resume order, without duplicates (the only names `skill_order` may contain). */
export function resumeSkills(parsed: EditableParsed): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of parsed.skills) {
    const name = s.name.trim();
    if (name && !seen.has(name.toLowerCase())) {
      seen.add(name.toLowerCase());
      out.push(name);
    }
  }
  return out;
}

/**
 * Initial skill order: suggested skills first (only those already on the resume, using the resume's spelling),
 * then the rest in their current order. Suggestions for skills the resume lacks are dropped.
 */
export function initialSkillOrder(skills: string[], suggested: string[] | null | undefined): string[] {
  const byLower = new Map(skills.map((s) => [s.toLowerCase(), s]));
  const first: string[] = [];
  for (const s of suggested ?? []) {
    const match = byLower.get(s.trim().toLowerCase());
    if (match && !first.includes(match)) first.push(match);
  }
  return [...first, ...skills.filter((s) => !first.includes(s))];
}

export function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export interface TailoredFormState {
  jobId: string | null;
  baseVersionId: string | null;
  originalSkills: string[];
  skillOrder: string[];
  /** Rewrites the user ticked (from match suggestions or "Suggest improvements"). */
  selectedRewrites: VersionChange[];
  /** Manual edits: an existing text and its replacement. */
  edits: { before: string; after: string; section: string }[];
  changeSummary: string;
  jobTitle?: string | null;
}

/** Builds the request body, or returns the problems that would make the server reject it. */
export function buildTailoredPayload(f: TailoredFormState): { payload: TailoredVersionPayload | null; errors: string[] } {
  const errors: string[] = [];
  const allowed = new Set(f.originalSkills.map((s) => s.toLowerCase()));
  const unknown = f.skillOrder.filter((s) => !allowed.has(s.toLowerCase()));
  if (unknown.length) errors.push(`These skills aren't in this resume: ${unknown.join(", ")}.`);
  const orderChanged = f.skillOrder.length > 0 && f.skillOrder.join("\u0000") !== f.originalSkills.join("\u0000");

  const changes: VersionChange[] = [];
  const seenBefore = new Set<string>();
  const add = (c: VersionChange) => {
    const before = c.before.trim();
    const after = c.after.trim();
    if (!before || !after || before === after) return;
    if (seenBefore.has(before)) {
      errors.push(`Two changes edit the same text: "${before.slice(0, 60)}".`);
      return;
    }
    seenBefore.add(before);
    changes.push({ section: c.section || "experience", before, after, evidence_refs: c.evidence_refs ?? [] });
  };
  f.selectedRewrites.forEach(add);
  f.edits.forEach((e) => add({ section: e.section, before: e.before, after: e.after }));

  if (!changes.length && !orderChanged) errors.push("Nothing to change: reorder skills or pick at least one text change.");
  if (changes.length > 30) errors.push("At most 30 text changes per version.");
  if (errors.length) return { payload: null, errors };

  const parts = [changes.length ? `${changes.length} text change${changes.length === 1 ? "" : "s"}` : null, orderChanged ? "skill order updated" : null].filter(Boolean);
  const auto = `${f.jobTitle ? `Tailored for ${f.jobTitle}` : "Tailored version"}: ${parts.join(", ")}`;
  return {
    payload: {
      job_id: f.jobId,
      base_version_id: f.baseVersionId,
      changes,
      skill_order: orderChanged ? f.skillOrder : null,
      change_summary: (f.changeSummary.trim() || auto).slice(0, 500),
    },
    errors: [],
  };
}

export interface TailoredServerProblems {
  message: string;
  violations: { code: string; severity: string; detail: string }[];
  unknownSkills: string[];
  unknownBefore: string | null;
  fieldErrors: string[];
}

/** Reads a 422 from POST /resumes/{id}/versions: claim-check violations, unknown skills, or unknown `before` text. */
export function tailoredProblems(error: unknown): TailoredServerProblems | null {
  if (!isApiError(error) || error.status !== 422) return null;
  const d = asRecord(error.details);
  return {
    message: error.message,
    violations: asArray(d.violations).map((v) => {
      const r = asRecord(v);
      return { code: asString(r.code) ?? "violation", severity: asString(r.severity) ?? "blocking", detail: asString(r.detail) ?? "" };
    }),
    unknownSkills: asArray(d.unknown).map((x) => asString(x)).filter((x): x is string => !!x),
    unknownBefore: asString(d.before),
    fieldErrors: error.fieldErrors.map((f) => (f.field ? `${f.field}: ${f.message}` : f.message)),
  };
}

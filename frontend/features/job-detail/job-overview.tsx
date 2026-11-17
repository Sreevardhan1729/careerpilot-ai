"use client";

import { AlertTriangleIcon, InfoIcon } from "lucide-react";
import type { ReactNode } from "react";
import { EvidencePopover } from "@/components/evidence-popover";
import { ExternalLink } from "@/components/external-link";
import { LongText } from "@/components/long-text";
import { Section } from "@/components/page-header";
import { ProvenanceBadge, SalaryBadge } from "@/components/provenance-badge";
import { PriorityBadge, ScoreBar } from "@/components/score";
import { Time } from "@/components/time";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { isRuleBased } from "@/lib/analysis";
import { evidenceKind, formatSalaryRange, salarySourceMeta } from "@/lib/provenance";
import { JOB_SCORE_LABELS, jobScoreBreakdown, locationLabels } from "@/lib/shapes";
import { asRecord, asString, formatPercent, formatScore, titleCase } from "@/lib/utils";
import type { JobDetail, JobEvidenceOut, JobSkillOut } from "@/types/models";
import { experienceLabel } from "@/features/jobs/job-format";

/** Short, readable rendering of an extracted value (objects show their scalar fields, never raw JSON). */
function valueText(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(valueText).join(", ") || "—";
  const parts = Object.entries(value as Record<string, unknown>)
    .filter(([k, v]) => v != null && v !== "" && typeof v !== "object" && !["evidence", "evidence_text", "confidence"].includes(k))
    .map(([k, v]) => `${titleCase(k)}: ${typeof v === "number" ? v.toLocaleString("en-IN") : String(v)}`);
  return parts.join(" · ") || "—";
}

function evidenceFor(evidence: JobEvidenceOut[], ...fields: string[]): JobEvidenceOut[] {
  return evidence.filter((e) => fields.some((f) => e.field === f || e.field.startsWith(`${f}.`) || e.field.startsWith(`${f}_`)));
}

function FactEvidence({ label, items, extraText }: { label: string; items: JobEvidenceOut[]; extraText?: string | null }) {
  if (!items.length && !extraText) return null;
  const verified = items.length ? items.every((e) => e.verified) : undefined;
  const confidence = items.find((e) => e.confidence != null)?.confidence ?? null;
  return (
    <EvidencePopover
      label={label}
      verified={verified}
      confidence={confidence}
      evidence={[...(extraText ? [{ text: extraText }] : []), ...items.map((e) => ({ text: e.evidence_text }))]}
    />
  );
}

function Fact({ label, children, evidence }: { label: string; children: ReactNode; evidence?: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="flex flex-wrap items-center gap-1.5 text-sm">
        {children}
        {evidence}
      </dd>
    </div>
  );
}

function KindFor({ items }: { items: JobEvidenceOut[] }) {
  if (!items.length) return null;
  return <ProvenanceBadge kind={evidenceKind({ explicit: items.every((e) => e.explicit), verified: items.every((e) => e.verified) })} />;
}

function SkillChip({ skill }: { skill: JobSkillOut }) {
  return (
    <li className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-sm">
      <span>{skill.name}</span>
      {!skill.evidence_verified && <ProvenanceBadge kind="unverified" label="Unverified" />}
      <EvidencePopover
        label={`${skill.name} (${skill.importance})`}
        verified={skill.evidence_verified}
        confidence={skill.confidence}
        evidence={[{ text: skill.evidence_text, meta: skill.category ? <span>Category: {titleCase(skill.category)}</span> : null }]}
        triggerLabel={<span className="sr-only">Evidence</span>}
      />
    </li>
  );
}

function SkillGroup({ title, description, skills }: { title: string; description: string; skills: JobSkillOut[] }) {
  return (
    <div className="space-y-2">
      <div>
        <h3 className="font-medium">
          {title} <span className="text-sm font-normal text-muted-foreground">({skills.length})</span>
        </h3>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      {skills.length ? (
        <ul className="flex flex-wrap gap-2">
          {skills.map((s) => (
            <SkillChip key={`${s.importance}-${s.name}`} skill={s} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">None stated.</p>
      )}
    </div>
  );
}

function BulletList({ items, empty = "Not stated." }: { items: string[]; empty?: string }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      {items.map((x, i) => (
        <li key={i}>
          <LongText text={x} />
        </li>
      ))}
    </ul>
  );
}

export function JobScoreCard({ job }: { job: JobDetail }) {
  const b = jobScoreBreakdown(job.job_score_breakdown);
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="flex flex-wrap items-center gap-2">
            Job Score <span className="tabular-nums">{formatScore(job.job_score ?? b?.score, 1)}</span>
            <PriorityBadge priority={job.priority ?? b?.priority} />
            <ProvenanceBadge kind="heuristic" />
          </h2>
        </CardTitle>
        <CardDescription>0.50·M + 0.20·F + 0.15·E_elig + 0.10·L + 0.05·S, each 0–100.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!b ? (
          <p className="text-sm text-muted-foreground">Not ranked yet. The score appears after analysis and resume matching.</p>
        ) : (
          <>
            <div className="space-y-3">
              {b.components.map((c) => (
                <div key={c.key}>
                  <ScoreBar label={JOB_SCORE_LABELS[c.key] ?? c.key} score={c.score} weight={c.weight} />
                  {c.explanation && <p className="mt-1 text-xs text-muted-foreground">{c.explanation}</p>}
                </div>
              ))}
            </div>
            {b.disqualifiers.length > 0 && (
              <Alert variant="warning">
                <AlertTriangleIcon aria-hidden="true" />
                <AlertTitle>Potential disqualifiers</AlertTitle>
                <AlertDescription>
                  <p className="mb-1 text-xs">Flagged for your judgement — the job is not filtered out.</p>
                  <BulletList items={b.disqualifiers} />
                </AlertDescription>
              </Alert>
            )}
            {b.limitations.length > 0 && (
              <div>
                <h3 className="text-sm font-medium">Limitations</h3>
                <BulletList items={b.limitations} />
              </div>
            )}
            <div className="flex flex-wrap gap-2 text-xs">
              {b.salaryKnown !== null && <Badge variant="outline">Salary {b.salaryKnown ? "known" : "unknown"}</Badge>}
              {b.recent !== null && <Badge variant="outline">{b.recent ? "Recent posting" : "Older posting"}</Badge>}
              {b.experienceEligible !== null && (
                <Badge variant="outline">{b.experienceEligible ? "Experience eligible" : "Experience gap"}</Badge>
              )}
            </div>
          </>
        )}
        <p className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
          {b?.disclaimer ?? "Job Score is a prioritisation heuristic."} Scores are not shortlist probabilities.
        </p>
      </CardContent>
    </Card>
  );
}

export function JobOverview({ job }: { job: JobDetail }) {
  const ev = job.evidence;
  const locations = locationLabels(job.locations);
  const salaryRange = formatSalaryRange(job.salary);
  const salaryMeta = salarySourceMeta(job.salary.source_type);
  const postedBy = asRecord(job.posted_by);
  const postedByName = asString(postedBy.name);
  const mandatory = job.skills.filter((s) => s.importance === "mandatory");
  const preferred = job.skills.filter((s) => s.importance === "preferred");
  const mentioned = job.skills.filter((s) => s.importance !== "mandatory" && s.importance !== "preferred");

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Role details</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-4 sm:grid-cols-2">
              <Fact label="Company" evidence={<FactEvidence label="Company" items={evidenceFor(ev, "company")} />}>
                {job.company?.name ?? "Unknown"}
                {job.company?.domain && <span className="text-muted-foreground">({job.company.domain})</span>}
              </Fact>
              <Fact label="Location" evidence={<FactEvidence label="Location" items={evidenceFor(ev, "location", "locations")} />}>
                {locations.length ? locations.join(" · ") : "Not stated"}
                <KindFor items={evidenceFor(ev, "location", "locations")} />
              </Fact>
              <Fact label="Work mode" evidence={<FactEvidence label="Work mode" items={evidenceFor(ev, "work_mode")} />}>
                {job.work_mode === "unknown" ? "Not stated" : titleCase(job.work_mode)}
                <KindFor items={evidenceFor(ev, "work_mode")} />
              </Fact>
              <Fact label="Employment type" evidence={<FactEvidence label="Employment type" items={evidenceFor(ev, "employment_type")} />}>
                {job.employment_type === "unknown" ? "Not stated" : titleCase(job.employment_type)}
              </Fact>
              <Fact label="Seniority" evidence={<FactEvidence label="Seniority" items={evidenceFor(ev, "seniority")} />}>
                {job.seniority === "unknown" ? "Not stated" : titleCase(job.seniority)}
                <KindFor items={evidenceFor(ev, "seniority")} />
              </Fact>
              <Fact
                label="Experience"
                evidence={<FactEvidence label="Experience" items={evidenceFor(ev, "experience")} extraText={job.experience.evidence} />}
              >
                {experienceLabel(job.experience)}
                {(job.experience.min_years != null || job.experience.max_years != null) && (
                  <ProvenanceBadge kind={job.experience.explicit ? "explicit" : "inferred"} />
                )}
              </Fact>
              <Fact label="Salary" evidence={<FactEvidence label="Salary" items={evidenceFor(ev, "salary")} />}>
                {salaryRange && <span className="tabular-nums">{salaryRange}</span>}
                <SalaryBadge sourceType={job.salary.source_type} />
                {job.salary.is_base === false && <Badge variant="outline">Total comp</Badge>}
                {job.salary.is_base === true && <Badge variant="outline">Base</Badge>}
                {job.salary.source_url && <ExternalLink href={job.salary.source_url}>salary source</ExternalLink>}
              </Fact>
              {job.department && <Fact label="Department">{job.department}</Fact>}
              {job.business_domain && <Fact label="Business domain">{job.business_domain}</Fact>}
              <Fact label="Posted">
                <Time value={job.posted_at} dateOnly />
              </Fact>
              {job.application_deadline && (
                <Fact label="Application deadline">
                  <Time value={job.application_deadline} dateOnly />
                </Fact>
              )}
              {job.posted_by && (
                <Fact label="Posted by">
                  {postedByName ?? valueText(job.posted_by)}
                  {asString(postedBy.title) && <span className="text-muted-foreground">· {asString(postedBy.title)}</span>}
                  {asString(postedBy.profile_url) && <ExternalLink href={asString(postedBy.profile_url)}>profile</ExternalLink>}
                </Fact>
              )}
            </dl>
            <p className="mt-3 text-xs text-muted-foreground">{salaryMeta.description}</p>
            {job.hiring_expectations && (
              <div className="mt-4">
                <h3 className="text-sm font-medium">Hiring expectations</h3>
                <p className="whitespace-pre-wrap text-sm">{job.hiring_expectations}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Skills</h2>
            </CardTitle>
            <CardDescription>Each skill links to the sentence it was extracted from. Unverified quotes couldn&apos;t be found in the source text.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <SkillGroup title="Mandatory" description="Stated as required." skills={mandatory} />
            <SkillGroup title="Preferred" description="Nice to have / preferred." skills={preferred} />
            <SkillGroup title="Mentioned" description="Mentioned without a requirement level." skills={mentioned} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Responsibilities and requirements</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <div>
              <h3 className="mb-1 font-medium">Responsibilities</h3>
              <BulletList items={job.responsibilities} />
            </div>
            <div>
              <h3 className="mb-1 font-medium">Technical requirements</h3>
              <BulletList items={job.technical_requirements} />
            </div>
            <div>
              <h3 className="mb-1 font-medium">Education</h3>
              <BulletList items={job.education} />
            </div>
            <div>
              <h3 className="mb-1 font-medium">Soft skills</h3>
              <BulletList items={job.soft_skills} />
            </div>
          </CardContent>
        </Card>

        {job.missing_information.length > 0 && (
          <Alert variant="info">
            <InfoIcon aria-hidden="true" />
            <AlertTitle>Not stated in the job post</AlertTitle>
            <AlertDescription>
              <BulletList items={job.missing_information} />
            </AlertDescription>
          </Alert>
        )}

        <Section id="evidence" title="Evidence" description="Every extracted field with the quote that supports it.">
          {ev.length ? (
            <Card>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Field</TableHead>
                    <TableHead>Value</TableHead>
                    <TableHead>Evidence</TableHead>
                    <TableHead>How known</TableHead>
                    <TableHead>Confidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ev.map((e, i) => (
                    <TableRow key={`${e.field}-${i}`}>
                      <TableCell className="font-medium">{titleCase(e.field)}</TableCell>
                      <TableCell className="max-w-48 break-words">{valueText(e.value)}</TableCell>
                      <TableCell className="max-w-md">
                        {e.evidence_text ? (
                          <span className="italic">
                            <LongText text={e.evidence_text} quote />
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <ProvenanceBadge kind={evidenceKind(e)} />
                      </TableCell>
                      <TableCell className="tabular-nums">{formatPercent(e.confidence)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          ) : (
            <p className="text-sm text-muted-foreground">No field-level evidence recorded.</p>
          )}
        </Section>
      </div>

      <div className="space-y-6">
        <JobScoreCard job={job} />

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Source and application</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Apply</p>
              {job.application_url ? <ExternalLink href={job.application_url}>Application page</ExternalLink> : <p className="text-muted-foreground">No application link found.</p>}
            </div>
            {job.source_url && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Original post</p>
                <ExternalLink href={job.source_url} />
              </div>
            )}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Source records</p>
              {job.source_records.length ? (
                <ul className="mt-1 space-y-2">
                  {job.source_records.map((r, i) => (
                    <li key={i}>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline">{r.source_name}</Badge>
                        {r.source_url && <ExternalLink href={r.source_url} />}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Collected <Time value={r.collected_at} /> · {r.dedup_signal === "new" ? "first seen" : `merged by ${titleCase(r.dedup_signal)}`}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">Added by you ({titleCase(job.input_type)}).</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Provenance</h2>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-sm">
            <p>
              <span className="text-muted-foreground">Input: </span>
              {titleCase(job.input_type)}
            </p>
            <p className="flex flex-wrap items-center gap-1.5">
              <span className="text-muted-foreground">Analysis method: </span>
              {job.analysis_method ?? "—"}
              {isRuleBased(job.analysis_method, job.model_id) ? (
                <ProvenanceBadge kind="heuristic" label="Rule-based" />
              ) : (
                <ProvenanceBadge kind="inferred" label="LLM-extracted" />
              )}
            </p>
            <p>
              <span className="text-muted-foreground">Model: </span>
              {job.model_id ?? "—"}
            </p>
            <p>
              <span className="text-muted-foreground">Added: </span>
              <Time value={job.created_at} />
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

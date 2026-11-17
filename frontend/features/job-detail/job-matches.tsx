"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, Loader2Icon, RefreshCwIcon, StarIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { EvidencePopover } from "@/components/evidence-popover";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { EmptyState, QueryView } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { ScoreBar } from "@/components/score";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { MATCH_LABELS, MATCH_ORDER, relevantItems, scoreComponents, skillBreakdown, suggestions as parseSuggestions } from "@/lib/shapes";
import { SKILL_STATUS_META } from "@/lib/skill-status";
import { asRecord, asString, formatPercent, formatScore, titleCase } from "@/lib/utils";
import type { MatchItem, MatchesOut } from "@/types/models";
import { SkillStatusBadge } from "./skill-status-badge";
import { TailorPanel } from "./tailor-panel";

export const matchesKey = (jobId: string) => ["jobs", jobId, "matches"] as const;

function refsToEvidence(refs: string[], evidence: Record<string, string>) {
  return refs.map((r) => ({ text: evidence[r] ?? null, meta: evidence[r] ? null : <span>Reference {r}</span> }));
}

function MatchCard({ item, evidence, jobId, jobTitle }: { item: MatchItem; evidence: Record<string, string>; jobId: string; jobTitle: string | null }) {
  const components = scoreComponents(item.components, MATCH_ORDER);
  const skills = skillBreakdown(item.skill_breakdown);
  const projects = relevantItems(item.relevant_projects);
  const experience = relevantItems(item.relevant_experience);
  const sugg = parseSuggestions(item.suggestions);
  const resumeId = asString(item.resume.id);
  const label = asString(item.resume.label) ?? "Resume";
  const version = asString(item.resume.version_number);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h3 className="flex flex-wrap items-center gap-2 text-base">
            <span className="text-muted-foreground">#{item.rank}</span>
            {resumeId ? (
              <Link href={`/resumes/${resumeId}`} className="text-primary hover:underline">
                {label}
              </Link>
            ) : (
              label
            )}
            {version && <span className="text-sm font-normal text-muted-foreground">v{version}</span>}
            {item.is_best && (
              <Badge variant="success">
                <StarIcon aria-hidden="true" />
                Best match
              </Badge>
            )}
            <span className="ml-auto text-xl tabular-nums">{formatScore(item.score, 1)}</span>
          </h3>
        </CardTitle>
        <CardDescription>
          Mandatory coverage {formatPercent(item.mandatory_coverage)} · Preferred coverage {formatPercent(item.preferred_coverage)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {item.explanation && <p className="whitespace-pre-wrap text-sm">{item.explanation}</p>}

        <div className="grid gap-4 md:grid-cols-2">
          {components.map((c) => (
            <div key={c.key} className="space-y-1">
              <ScoreBar label={MATCH_LABELS[c.key] ?? c.key} score={c.score} weight={c.weight} />
              {c.explanation && <p className="text-xs text-muted-foreground">{c.explanation}</p>}
              {c.evidenceRefs.length > 0 && (
                <EvidencePopover
                  label={MATCH_LABELS[c.key] ?? c.key}
                  kind="heuristic"
                  evidence={refsToEvidence(c.evidenceRefs, evidence)}
                  triggerLabel={`${c.evidenceRefs.length} resume excerpt${c.evidenceRefs.length === 1 ? "" : "s"}`}
                />
              )}
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <h4 className="font-medium">Skill breakdown</h4>
          <ul className="flex flex-wrap gap-2 text-xs" aria-label="Skill status legend">
            {Object.keys(SKILL_STATUS_META).map((s) => (
              <li key={s}>
                <SkillStatusBadge status={s} />
              </li>
            ))}
          </ul>
          {skills.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Skill</TableHead>
                  <TableHead>Job importance</TableHead>
                  <TableHead>Resume evidence</TableHead>
                  <TableHead>
                    <span className="sr-only">Excerpts</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.map((s) => (
                  <TableRow key={`${s.importance}-${s.skill}`}>
                    <TableCell className="font-medium">{s.skill}</TableCell>
                    <TableCell>{titleCase(s.importance)}</TableCell>
                    <TableCell>
                      <SkillStatusBadge status={s.status} />
                    </TableCell>
                    <TableCell>
                      {s.evidenceRefs.length > 0 && (
                        <EvidencePopover label={`${s.skill} on ${label}`} evidence={refsToEvidence(s.evidenceRefs, evidence)} />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">The job lists no skills to compare.</p>
          )}
        </div>

        {(projects.length > 0 || experience.length > 0) && (
          <div className="grid gap-4 md:grid-cols-2">
            {projects.length > 0 && (
              <div>
                <h4 className="mb-1 font-medium">Relevant projects</h4>
                <ul className="space-y-1.5 text-sm">
                  {projects.map((p, i) => (
                    <li key={i}>
                      <span className="font-medium">{p.title}</span>
                      {p.score != null && <span className="ml-2 tabular-nums text-muted-foreground">{formatScore(p.score)}</span>}
                      {p.matchedSkills.length > 0 && <p className="text-xs text-muted-foreground">Matches: {p.matchedSkills.join(", ")}</p>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {experience.length > 0 && (
              <div>
                <h4 className="mb-1 font-medium">Relevant experience</h4>
                <ul className="space-y-1.5 text-sm">
                  {experience.map((p, i) => (
                    <li key={i}>
                      <span className="font-medium">{p.title}</span>
                      {p.score != null && <span className="ml-2 tabular-nums text-muted-foreground">{formatScore(p.score)}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {sugg && (sugg.summary || sugg.bulletRewrites.length > 0 || sugg.missingEvidence.length > 0 || sugg.keywords.length > 0) && (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3">
            <h4 className="flex items-center gap-2 font-medium">
              Suggestions <ProvenanceBadge kind="inferred" label="Suggested" />
            </h4>
            {sugg.summary && <p className="whitespace-pre-wrap text-sm">{sugg.summary}</p>}
            {sugg.missingEvidence.length > 0 && (
              <div className="text-sm">
                <p className="font-medium">Add evidence for (only if true):</p>
                <p className="text-muted-foreground">{sugg.missingEvidence.join(", ")}</p>
              </div>
            )}
            {sugg.skillOrder.length > 0 && (
              <p className="text-sm">
                <span className="font-medium">Suggested skill order: </span>
                {sugg.skillOrder.join(", ")}
              </p>
            )}
            {sugg.keywords.length > 0 && (
              <p className="text-sm">
                <span className="font-medium">Keywords to highlight (where true): </span>
                {sugg.keywords.join(", ")}
              </p>
            )}
            {sugg.bulletRewrites.length > 0 && (
              <ul className="space-y-2 text-sm">
                {sugg.bulletRewrites.map((r, i) => (
                  <li key={i} className="grid gap-1 rounded border bg-background p-2 md:grid-cols-[1fr_auto_1fr] md:items-start md:gap-2">
                    <p className="text-muted-foreground">
                      <span className="sr-only">Before: </span>
                      {r.before || "—"}
                    </p>
                    <ArrowRightIcon className="hidden size-4 md:block" aria-hidden="true" />
                    <p>
                      <span className="sr-only">After: </span>
                      {r.after}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-muted-foreground">Suggestions never invent experience — keep only what is true.</p>
          </div>
        )}

        {resumeId && (
          <TailorPanel
            resumeId={resumeId}
            jobId={jobId}
            jobTitle={jobTitle}
            suggestedSkillOrder={sugg?.skillOrder ?? []}
            bulletRewrites={(sugg?.bulletRewrites ?? []).filter((r) => r.before).map((r) => ({ section: "experience", before: r.before, after: r.after, evidence_refs: r.evidenceRefs }))}
            persistedImprovement={asRecord(item.suggestions).improvement}
          />
        )}

        {item.limitations.length > 0 && (
          <div>
            <h4 className="font-medium">Limitations</h4>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {item.limitations.map((l, i) => (
                <li key={i}>{typeof l === "string" ? l : JSON.stringify(l)}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MatchesList({ data, jobId, jobTitle }: { data: MatchesOut; jobId: string; jobTitle: string | null }) {
  if (!data.items.length) {
    return (
      <EmptyState
        title="No resume matches yet"
        description="Upload a resume, then re-match. Matching runs automatically after analysis when resumes exist."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href="/resumes">Go to Resume Library</Link>
          </Button>
        }
      />
    );
  }
  return (
    <div className="space-y-4">
      {data.items.map((item) => (
        <MatchCard key={`${item.rank}-${asString(item.resume.id)}`} item={item} evidence={data.evidence ?? {}} jobId={jobId} jobTitle={jobTitle} />
      ))}
      <p className="text-xs text-muted-foreground">Scoring config {data.scoring_config_version}</p>
    </div>
  );
}

export function JobMatches({ jobId, jobTitle = null }: { jobId: string; jobTitle?: string | null }) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: matchesKey(jobId), queryFn: () => api.jobs.matches(jobId) });
  const [runId, setRunId] = useState<string | null>(null);
  const [upToDate, setUpToDate] = useState(false);
  const rematch = useMutation({
    mutationFn: (force: boolean) => api.resumes.match(jobId, newIdempotencyKey(), force),
    onSuccess: (res) => {
      if (res.kind === "accepted") {
        setUpToDate(false);
        setRunId(res.run.workflow_id);
      } else {
        setUpToDate(true);
        toast.info("Matches are already up to date for the current resumes.");
        void qc.invalidateQueries({ queryKey: matchesKey(jobId) });
      }
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canMatch = hasEndpoint("POST", "/resumes/match/{}");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          {query.data?.disclaimer ?? "Match scores rank your resumes for this job. They are not a probability of being shortlisted."}
        </p>
        {canMatch && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => rematch.mutate(false)} disabled={rematch.isPending || Boolean(runId)}>
              {rematch.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <RefreshCwIcon aria-hidden="true" />}
              Re-match resumes
            </Button>
            {upToDate && (
              <Button variant="ghost" onClick={() => rematch.mutate(true)} disabled={rematch.isPending}>
                Force re-match
              </Button>
            )}
          </div>
        )}
      </div>
      {runId && (
        <RunProgress
          runId={runId}
          title="Matching resumes"
          onSettled={() => {
            void qc.invalidateQueries({ queryKey: matchesKey(jobId) });
            void qc.invalidateQueries({ queryKey: ["jobs", jobId] });
          }}
          actions={(run) =>
            run.status !== "running" && run.status !== "queued" ? (
              <Button size="sm" variant="ghost" onClick={() => setRunId(null)}>
                Dismiss
              </Button>
            ) : null
          }
        />
      )}
      <QueryView query={query} loadingLabel="Loading resume matches…" errorTitle="Couldn't load resume matches">
        {(data) => <MatchesList data={data} jobId={jobId} jobTitle={jobTitle} />}
      </QueryView>
    </div>
  );
}

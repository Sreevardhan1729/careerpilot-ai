"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, LightbulbIcon, Loader2Icon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { RunProgress } from "@/components/run-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TailoredVersionButton } from "@/features/resumes/tailored-version-dialog";
import type { VersionChange } from "@/features/resumes/tailored";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isSuccessStatus, isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { improvement as parseImprovement, type Improvement, type ImprovementChange } from "@/lib/shapes";
import { asRecord, titleCase } from "@/lib/utils";

function ChangeList({ changes, dropped = false }: { changes: ImprovementChange[]; dropped?: boolean }) {
  return (
    <ul className="space-y-2">
      {changes.map((c, i) => (
        <li key={i} className={dropped ? "rounded border border-red-200 bg-red-50 p-2 text-sm" : "rounded border bg-background p-2 text-sm"}>
          <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">{titleCase(c.section)}</p>
          <div className="grid gap-1 md:grid-cols-[1fr_auto_1fr] md:items-start md:gap-2">
            <p className="text-muted-foreground">
              <span className="sr-only">Before: </span>
              {c.before ?? "General advice (no existing text to replace)"}
            </p>
            <ArrowRightIcon className="hidden size-4 md:block" aria-hidden="true" />
            <p>
              <span className="sr-only">After: </span>
              {c.after}
            </p>
          </div>
          {c.reason && <p className="mt-1 text-xs text-muted-foreground">Why: {c.reason}</p>}
          {dropped && c.rejected.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs text-red-800">
              {c.rejected.map((v, j) => (
                <li key={j}>
                  {titleCase(v.code)}: {v.detail}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ImprovementView({ value }: { value: Improvement }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="flex flex-wrap items-center gap-2 font-medium">
        <LightbulbIcon className="size-4" aria-hidden="true" />
        Improvement suggestions
        {value.method === "heuristic" ? <ProvenanceBadge kind="heuristic" label="Rule-based" /> : <ProvenanceBadge kind="inferred" label="Suggested" />}
      </p>
      {value.updatedSummary && (
        <div>
          <p className="font-medium">Suggested summary</p>
          <p className="whitespace-pre-wrap text-muted-foreground">{value.updatedSummary}</p>
        </div>
      )}
      {value.keywords.length > 0 && (
        <div>
          <p className="font-medium">Keywords to highlight</p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {value.keywords.map((k) => (
              <li key={k}>
                <Badge variant="info">{k}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {value.missingEvidence.length > 0 && (
        <div>
          <p className="font-medium">No evidence in this resume — add only if true</p>
          <ul className="mt-1 flex flex-wrap gap-1">
            {value.missingEvidence.map((k) => (
              <li key={k}>
                <Badge variant="outline" className="border-dashed border-slate-400 text-slate-700">
                  {k}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {value.suggestedChanges.length > 0 && (
        <div className="space-y-1">
          <p className="font-medium">Suggested changes (passed the claim check)</p>
          <ChangeList changes={value.suggestedChanges} />
        </div>
      )}
      {value.droppedChanges.length > 0 && (
        <div className="space-y-1">
          <p className="font-medium">Dropped changes (would claim things your resume doesn&apos;t support)</p>
          <ChangeList changes={value.droppedChanges} dropped />
        </div>
      )}
      {!value.keywords.length && !value.missingEvidence.length && !value.suggestedChanges.length && !value.skillOrder.length && (
        <p className="text-muted-foreground">No improvements suggested for this job.</p>
      )}
    </div>
  );
}

/** Per-resume tailoring actions on the Resume match tab. */
export function TailorPanel({
  resumeId,
  jobId,
  jobTitle,
  suggestedSkillOrder,
  bulletRewrites,
  persistedImprovement,
}: {
  resumeId: string;
  jobId: string;
  jobTitle: string | null;
  suggestedSkillOrder: string[];
  bulletRewrites: VersionChange[];
  persistedImprovement: unknown;
}) {
  const qc = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Improvement | null>(null);
  const optimize = useMutation({
    mutationFn: () => api.resumes.optimize(resumeId, jobId, newIdempotencyKey()),
    onSuccess: (res) => {
      setFresh(null);
      setRunId(res.workflow_id);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canOptimize = hasEndpoint("POST", "/resumes/{}/optimize");
  const canTailor = hasEndpoint("POST", "/resumes/{}/versions");
  if (!canOptimize && !canTailor) return null;

  const imp = fresh ?? parseImprovement(persistedImprovement);
  const improvementRewrites: VersionChange[] = (imp?.suggestedChanges ?? [])
    .filter((c) => c.before)
    .map((c) => ({ section: c.section, before: c.before as string, after: c.after, evidence_refs: c.evidenceRefs }));
  const allRewrites = [...bulletRewrites, ...improvementRewrites.filter((r) => !bulletRewrites.some((b) => b.before === r.before && b.after === r.after))];

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="mr-auto font-medium">Tailor this resume</h4>
        {canOptimize && (
          <Button size="sm" variant="outline" onClick={() => optimize.mutate()} disabled={optimize.isPending || (Boolean(runId) && !fresh)}>
            {optimize.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <LightbulbIcon aria-hidden="true" />}
            Suggest improvements
          </Button>
        )}
        <TailoredVersionButton
          resumeId={resumeId}
          jobId={jobId}
          jobTitle={jobTitle}
          suggestedSkillOrder={suggestedSkillOrder}
          rewrites={allRewrites}
          label="Create tailored version for this job"
        />
      </div>
      {runId && (
        <RunProgress
          runId={runId}
          title="Suggesting improvements"
          onSettled={(run) => {
            if (isSuccessStatus(run.status)) setFresh(parseImprovement(asRecord(run.output).improvement));
            void qc.invalidateQueries({ queryKey: ["jobs", jobId, "matches"] });
          }}
          actions={(run) =>
            isTerminalStatus(run.status) ? (
              <Button size="sm" variant="ghost" onClick={() => setRunId(null)}>
                Dismiss
              </Button>
            ) : null
          }
        />
      )}
      {imp && (
        <>
          <ImprovementView value={imp} />
          {imp.skillOrder.length > 0 && (
            <TailoredVersionButton
              resumeId={resumeId}
              jobId={jobId}
              jobTitle={jobTitle}
              suggestedSkillOrder={imp.skillOrder}
              rewrites={allRewrites}
              label="Use this skill order in a tailored version"
              variant="default"
            />
          )}
        </>
      )}
    </div>
  );
}

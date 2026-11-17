"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, ArrowLeftIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { ErrorState, LoadingState } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage, isApiError } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { parseWarnings } from "@/lib/shapes";
import { titleCase } from "@/lib/utils";
import type { ResumeDetail } from "@/types/models";
import { ParsedDataEditor } from "./parsed-data-editor";
import { TailoredVersionButton } from "./tailored-version-dialog";
import { VersionHistory } from "./version-history";
import { DeleteResumeButton, DownloadButton, SetDefaultButton } from "./resume-actions";
import { ResumeStatusBadge } from "./resumes-view";

export const resumeKey = (id: string) => ["resumes", id] as const;

function MetadataForm({ resume }: { resume: ResumeDetail }) {
  const qc = useQueryClient();
  const [label, setLabel] = useState(resume.label);
  const [category, setCategory] = useState(resume.category ?? "");
  const patch = useMutation({
    mutationFn: () => api.resumes.patch(resume.id, { label: label.trim(), category: category.trim() || null }),
    onSuccess: () => {
      toast.success("Resume updated");
      void qc.invalidateQueries({ queryKey: ["resumes"] });
    },
  });
  if (!hasEndpoint("PATCH", "/resumes/{}")) return null;
  const dirty = label.trim() !== resume.label || (category.trim() || null) !== (resume.category ?? null);
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    patch.mutate();
  }
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
      <Field id="resume-label-edit" label="Label" required hint={resume.label_suggested ? `Suggested: ${resume.label_suggested}` : undefined}>
        <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
      </Field>
      <Field id="resume-category-edit" label="Category" hint="e.g. AI/ML, Backend">
        <Input value={category} onChange={(e) => setCategory(e.target.value)} maxLength={80} />
      </Field>
      <Button type="submit" disabled={!dirty || !label.trim() || patch.isPending}>
        {patch.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
        Save
      </Button>
      {patch.error && (
        <Alert variant="destructive" className="sm:col-span-3">
          <AlertDescription>{errorMessage(patch.error)}</AlertDescription>
        </Alert>
      )}
    </form>
  );
}

function Detail({ resume }: { resume: ResumeDetail }) {
  const qc = useQueryClient();
  const router = useRouter();
  const current = resume.current_version;
  const warnings = parseWarnings(current?.parse_warnings);
  const latest = resume.latest_run;
  const running = latest && !isTerminalStatus(latest.status);

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Link href="/resumes" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeftIcon className="size-4" aria-hidden="true" />
          Back to Resume Library
        </Link>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{resume.label}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <ResumeStatusBadge status={resume.status} />
              {resume.is_default && <Badge variant="success">Default</Badge>}
              {resume.category && <Badge variant="outline">{resume.category}</Badge>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <SetDefaultButton resumeId={resume.id} isDefault={resume.is_default} label={resume.label} />
            {current && resume.parsed_data && <TailoredVersionButton resumeId={resume.id} />}
            {current && <DownloadButton resumeId={resume.id} versionId={current.id} filename={current.original_filename} label="Download current" />}
            <DeleteResumeButton resumeId={resume.id} label={resume.label} onDeleted={() => router.push("/resumes")} />
          </div>
        </div>
      </div>

      {(running || latest?.status === "failed") && latest && (
        <RunProgress runId={latest.workflow_id} title="Parsing resume" onSettled={() => void qc.invalidateQueries({ queryKey: resumeKey(resume.id) })} />
      )}

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Details</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <MetadataForm key={`${resume.label}-${resume.category}`} resume={resume} />
          {current && (
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Current version</dt>
                <dd>
                  v{current.version_number} · {titleCase(current.approval_status)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">File</dt>
                <dd className="break-all">
                  {current.original_filename}
                  {current.page_count != null && ` · ${current.page_count} page${current.page_count === 1 ? "" : "s"}`}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Parsed with</dt>
                <dd className="flex flex-wrap items-center gap-1.5">
                  {current.parse_method ?? "—"}
                  {current.parse_method === "user_corrected" ? (
                    <ProvenanceBadge kind="explicit" label="Your corrections" />
                  ) : current.parse_method?.includes("llm") ? (
                    <ProvenanceBadge kind="inferred" label="LLM-parsed" />
                  ) : current.parse_method ? (
                    <ProvenanceBadge kind="heuristic" label="Rule-based" />
                  ) : null}
                </dd>
              </div>
            </dl>
          )}
        </CardContent>
      </Card>

      {warnings.length > 0 && (
        <Alert variant="warning">
          <AlertTriangleIcon aria-hidden="true" />
          <AlertTitle>Parsing warnings</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {current && resume.parsed_data ? (
        <ParsedDataEditor key={`${current.id}-${resume.updated_at}`} resumeId={resume.id} versionId={current.id} parsed={resume.parsed_data} />
      ) : (
        <Alert variant="info">
          <AlertDescription>
            {resume.status === "failed" ? "Parsing failed — retry above, or upload the file again." : "Parsed data appears here once parsing finishes."}
          </AlertDescription>
        </Alert>
      )}

      <VersionHistory resume={resume} />
    </div>
  );
}

export function ResumeDetailView({ id }: { id: string }) {
  const query = useQuery({
    queryKey: resumeKey(id),
    queryFn: () => api.resumes.get(id),
    refetchInterval: (q) => (q.state.data && ["uploaded", "parsing"].includes(q.state.data.status) ? 4000 : false),
  });
  if (query.isPending) return <LoadingState label="Loading resume…" rows={6} />;
  if (query.isError) {
    const notFound = isApiError(query.error) && query.error.status === 404;
    return <ErrorState title={notFound ? "Resume not found" : "Couldn't load this resume"} error={query.error} onRetry={notFound ? undefined : () => void query.refetch()} />;
  }
  return <Detail resume={query.data} />;
}

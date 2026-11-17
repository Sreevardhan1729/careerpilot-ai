"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KanbanSquareIcon, Loader2Icon, NotebookPenIcon, TableIcon } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ExternalLink } from "@/components/external-link";
import { PageHeader } from "@/components/page-header";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { Time } from "@/components/time";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api, itemsOf } from "@/lib/endpoints";
import { groupByColumn, KANBAN_COLUMNS, MANUAL_STATUS_OPTIONS, statusLabel } from "@/lib/kanban";
import { applicationPreview } from "@/lib/shapes";
import type { ApplicationOut, ApprovalOut } from "@/types/models";
import { ApproveApplicationButton, ConfirmSubmissionButton, evidenceLabel } from "./application-preview";
import { PrepareApplicationButton } from "./prepare-application";

type View = "kanban" | "table";

function StatusSelect({ app }: { app: ApplicationOut }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: (status: (typeof MANUAL_STATUS_OPTIONS)[number]) => api.applications.patch(app.id, { status }),
    onSuccess: (_d, status) => {
      toast.success(`Moved to ${statusLabel(status)}`);
      void qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasEndpoint("PATCH", "/applications/{}")) return null;
  const options: string[] = [...MANUAL_STATUS_OPTIONS];
  const current = options.includes(app.status) ? app.status : "";
  return (
    <NativeSelect
      aria-label={`Move ${app.job_title ?? "application"} to status`}
      className="h-8 text-xs"
      value={current}
      disabled={patch.isPending}
      onChange={(e) => e.target.value && patch.mutate(e.target.value as (typeof MANUAL_STATUS_OPTIONS)[number])}
    >
      {!current && <option value="">{statusLabel(app.status)} — move to…</option>}
      {options.map((s) => (
        <option key={s} value={s}>
          {statusLabel(s)}
        </option>
      ))}
    </NativeSelect>
  );
}

function NotesDialog({ app }: { app: ApplicationOut }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState(app.notes ?? "");
  const [followUp, setFollowUp] = useState(app.follow_up_date ?? "");
  const patch = useMutation({
    mutationFn: () => api.applications.patch(app.id, { notes: notes.trim() || null, follow_up_date: followUp || null }),
    onSuccess: () => {
      toast.success("Saved");
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  if (!hasEndpoint("PATCH", "/applications/{}")) return null;
  function submit(e: FormEvent) {
    e.preventDefault();
    patch.mutate();
  }
  return (
    <>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)} aria-label={`Notes and follow-up for ${app.job_title ?? "application"}`}>
        <NotebookPenIcon aria-hidden="true" />
        Notes
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Notes and follow-up</DialogTitle>
            <DialogDescription>{app.job_title ?? "Application"}</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-4">
            <Field id={`fu-${app.id}`} label="Follow-up date">
              <Input type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
            </Field>
            <Field id={`notes-${app.id}`} label="Notes">
              <Textarea rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={5000} />
            </Field>
            {patch.error && (
              <Alert variant="destructive">
                <AlertDescription>{errorMessage(patch.error)}</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={patch.isPending}>
                {patch.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StageActions({ app, approval }: { app: ApplicationOut; approval: ApprovalOut | undefined }) {
  const preview = applicationPreview(approval?.payload_preview ?? app.preview);
  if (app.status === "awaiting_approval") {
    return approval ? (
      <ApproveApplicationButton
        applicationId={app.id}
        approvalId={approval.approval_id}
        payloadHash={approval.payload_hash}
        expiresAt={approval.expires_at}
        preview={preview}
      />
    ) : (
      <p className="text-xs text-muted-foreground">Waiting for an approval request.</p>
    );
  }
  if (app.status === "ready_to_submit") {
    return (
      <div className="space-y-2">
        {preview && preview.manualSteps.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer font-medium">Manual steps</summary>
            <ol className="mt-1 list-decimal pl-4">
              {preview.manualSteps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </details>
        )}
        <ConfirmSubmissionButton applicationId={app.id} jobTitle={app.job_title} />
      </div>
    );
  }
  return null;
}

function AppCard({ app, approval }: { app: ApplicationOut; approval: ApprovalOut | undefined }) {
  const evidence = evidenceLabel(app.confirmation_evidence);
  return (
    <li>
      <Card>
        <CardContent className="space-y-2 p-3 text-sm">
          <div>
            <Link href={`/jobs/${app.job_id}`} className="font-medium text-primary hover:underline">
              {app.job_title || "Job"}
            </Link>
            <p className="text-xs text-muted-foreground">{app.company_name ?? "—"}</p>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge variant="outline">{statusLabel(app.status)}</Badge>
            {app.submitted_at && (
              <Badge variant="success">
                Applied <Time value={app.submitted_at} dateOnly />
              </Badge>
            )}
            {evidence && <Badge variant={evidence === "User Attestation" ? "warning" : "info"}>{evidence}</Badge>}
          </div>
          {app.follow_up_date && (
            <p className="text-xs">
              Follow up <Time value={app.follow_up_date} dateOnly />
            </p>
          )}
          {app.notes && <p className="line-clamp-3 whitespace-pre-wrap text-xs text-muted-foreground">{app.notes}</p>}
          <StageActions app={app} approval={approval} />
          <div className="flex items-center gap-1 border-t pt-2">
            <div className="flex-1">
              <StatusSelect app={app} />
            </div>
            <NotesDialog app={app} />
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

function Board({ apps, approvals }: { apps: ApplicationOut[]; approvals: Map<string, ApprovalOut> }) {
  const [showArchived, setShowArchived] = useState(false);
  const grouped = groupByColumn(apps);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 overflow-x-auto pb-3" role="list" aria-label="Application stages">
        {KANBAN_COLUMNS.map((col) => {
          const items = grouped.columns[col.id];
          const headingId = `col-${col.id}`;
          return (
            <section key={col.id} role="listitem" aria-labelledby={headingId} className="w-72 shrink-0 rounded-lg bg-muted/60 p-2">
              <h2 id={headingId} className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
                {col.title}
                <span className="rounded-full bg-background px-2 text-xs tabular-nums text-muted-foreground">{items.length}</span>
              </h2>
              {items.length ? (
                <ul className="space-y-2">
                  {items.map((a) => (
                    <AppCard key={a.id} app={a} approval={approvals.get(a.id)} />
                  ))}
                </ul>
              ) : (
                <p className="px-1 py-4 text-center text-xs text-muted-foreground">Empty</p>
              )}
            </section>
          );
        })}
      </div>
      {grouped.archived.length > 0 && (
        <div>
          <Button variant="ghost" size="sm" onClick={() => setShowArchived((s) => !s)} aria-expanded={showArchived}>
            {showArchived ? "Hide" : "Show"} archived ({grouped.archived.length})
          </Button>
          {showArchived && (
            <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {grouped.archived.map((a) => (
                <AppCard key={a.id} app={a} approval={undefined} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function AppTable({ apps, approvals }: { apps: ApplicationOut[]; approvals: Map<string, ApprovalOut> }) {
  return (
    <Card>
      <Table aria-label="Applications">
        <TableHeader>
          <TableRow>
            <TableHead>Job</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Submitted</TableHead>
            <TableHead>Follow-up</TableHead>
            <TableHead>Next step</TableHead>
            <TableHead>Move / notes</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {apps.map((a) => (
            <TableRow key={a.id}>
              <TableCell className="min-w-48">
                <Link href={`/jobs/${a.job_id}`} className="font-medium text-primary hover:underline">
                  {a.job_title || "Job"}
                </Link>
                <div className="text-muted-foreground">{a.company_name ?? "—"}</div>
                {a.application_url && <ExternalLink href={a.application_url} className="text-xs">Apply page</ExternalLink>}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{statusLabel(a.status)}</Badge>
              </TableCell>
              <TableCell>
                <Time value={a.submitted_at} dateOnly />
                {evidenceLabel(a.confirmation_evidence) && <div className="text-xs text-muted-foreground">{evidenceLabel(a.confirmation_evidence)}</div>}
              </TableCell>
              <TableCell>
                <Time value={a.follow_up_date} dateOnly />
              </TableCell>
              <TableCell>
                <StageActions app={a} approval={approvals.get(a.id)} />
              </TableCell>
              <TableCell className="min-w-56">
                <div className="flex items-center gap-1">
                  <StatusSelect app={a} />
                  <NotesDialog app={a} />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function PrepareFromJob() {
  const [jobId, setJobId] = useState("");
  const jobs = useQuery({ queryKey: ["jobs", "picker", "no-app"], queryFn: () => api.jobs.list({ limit: 100, sort: "-job_score" }) });
  if (!hasEndpoint("POST", "/applications/prepare")) return null;
  const candidates = jobs.data?.items.filter((j) => !j.has_application && j.status === "analyzed") ?? [];
  return (
    <Card className="mb-4">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
        <Field id="prep-job" label="Prepare an application for" className="flex-1" hint={jobs.isError ? errorMessage(jobs.error) : undefined}>
          <NativeSelect value={jobId} onChange={(e) => setJobId(e.target.value)} disabled={jobs.isPending}>
            <option value="">{jobs.isPending ? "Loading jobs…" : candidates.length ? "Choose a job" : "No analysed jobs without an application"}</option>
            {candidates.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title || "Untitled"} — {j.company?.name ?? "Unknown company"}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {jobId && <PrepareApplicationButton key={jobId} jobId={jobId} />}
      </CardContent>
    </Card>
  );
}

export function ApplicationsView() {
  const [view, setView] = useState<View>("kanban");
  const enabled = hasEndpoint("GET", "/applications");
  const query = useQuery({ queryKey: ["applications", "list"], queryFn: () => api.applications.list({ limit: 100 }), enabled });
  const approvalsEnabled = enabled && hasEndpoint("GET", "/approvals");
  const approvals = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals.list({ status: "pending" }),
    enabled: approvalsEnabled,
  });
  const approvalByApp = new Map<string, ApprovalOut>();
  for (const a of itemsOf(approvals.data)) {
    if (a.reference_type === "application" && a.status === "pending") approvalByApp.set(a.reference_id, a);
  }

  return (
    <>
      <PageHeader
        title="Application Tracker"
        description="Discovered and analysed jobs live in Job Search; the tracker starts once you prepare an application."
        actions={
          enabled ? (
            <div role="group" aria-label="View" className="inline-flex rounded-md border p-0.5">
              <Button size="sm" variant={view === "kanban" ? "secondary" : "ghost"} aria-pressed={view === "kanban"} onClick={() => setView("kanban")}>
                <KanbanSquareIcon aria-hidden="true" />
                Board
              </Button>
              <Button size="sm" variant={view === "table" ? "secondary" : "ghost"} aria-pressed={view === "table"} onClick={() => setView("table")}>
                <TableIcon aria-hidden="true" />
                Table
              </Button>
            </div>
          ) : null
        }
      />
      {!enabled ? (
        <NotAvailable feature="Applications" endpoint="GET /applications" />
      ) : (
        <>
          <PrepareFromJob />
          {approvals.isError && (
            <Alert variant="warning" className="mb-4">
              <AlertDescription>
                Couldn&apos;t load pending approvals: {errorMessage(approvals.error)}{" "}
                <Button size="sm" variant="link" onClick={() => void approvals.refetch()}>
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          )}
          <QueryView query={query} loadingLabel="Loading applications…" errorTitle="Couldn't load applications">
            {(data) => {
              const apps = itemsOf(data);
              if (!apps.length) return <EmptyState title="No applications yet" description="Prepare an application from a job to start tracking it." />;
              return view === "kanban" ? <Board apps={apps} approvals={approvalByApp} /> : <AppTable apps={apps} approvals={approvalByApp} />;
            }}
          </QueryView>
          {view === "kanban" && query.data && <PreviewLegend />}
        </>
      )}
    </>
  );
}

function PreviewLegend() {
  return (
    <p className="mt-2 text-xs text-muted-foreground">
      Tip: use each card&apos;s status menu to move it between stages. &quot;Applied&quot; is set by recording submission evidence.
    </p>
  );
}


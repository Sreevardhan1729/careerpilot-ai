"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, WandSparklesIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api, itemsOf } from "@/lib/endpoints";
import type { MessageType } from "@/types/models";
import { PendingApprovals } from "@/features/approvals/pending-approvals";
import { MESSAGE_TYPE_LABELS, OutreachCard } from "./outreach-card";
import { WriteDraftDialog } from "./write-draft-dialog";

const MESSAGE_TYPES = Object.keys(MESSAGE_TYPE_LABELS) as MessageType[];
const STATUSES = ["", "draft", "edited", "approved", "gmail_draft_created", "sent", "manually_sent", "discarded"];

export const outreachKey = (jobId: string | null, status: string) => ["outreach", "list", jobId ?? "all", status] as const;

function JobPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const jobs = useQuery({ queryKey: ["jobs", "picker"], queryFn: () => api.jobs.list({ limit: 100, sort: "-job_score" }) });
  return (
    <Field id="gen-job" label="Job" required hint={jobs.isError ? errorMessage(jobs.error) : undefined}>
      <NativeSelect value={value} onChange={(e) => onChange(e.target.value)} disabled={jobs.isPending}>
        <option value="">{jobs.isPending ? "Loading jobs…" : "Choose a job"}</option>
        {jobs.data?.items.map((j) => (
          <option key={j.id} value={j.id}>
            {j.title || "Untitled"} — {j.company?.name ?? "Unknown company"}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}

function PeoplePicker({ jobId, selected, onChange }: { jobId: string; selected: string[]; onChange: (ids: string[]) => void }) {
  const enabled = hasEndpoint("GET", "/jobs/{}/people") && Boolean(jobId);
  const people = useQuery({ queryKey: ["people", "job", jobId], queryFn: () => api.people.forJob(jobId), enabled });
  if (!enabled) return null;
  if (people.isPending) return <p className="text-sm text-muted-foreground">Loading people…</p>;
  if (people.isError) return <p className="text-sm text-red-700">{errorMessage(people.error)}</p>;
  const items = people.data.items.filter((p) => p.contact_status !== "do_not_contact");
  if (!items.length) return <p className="text-sm text-muted-foreground">No contactable people for this job yet. Drafts will be generic.</p>;
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">Recipients</legend>
      <p className="text-xs text-muted-foreground">Leave all unchecked to use the top 3 ranked people.</p>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {items.map((p) => {
          const id = `gen-person-${p.person_id}`;
          return (
            <div key={p.person_id} className="flex items-center gap-2">
              <Checkbox
                id={id}
                checked={selected.includes(p.person_id)}
                onCheckedChange={(c) => onChange(c === true ? [...selected, p.person_id] : selected.filter((x) => x !== p.person_id))}
              />
              <Label htmlFor={id} className="font-normal">
                {p.name}
                {p.designation ? <span className="text-muted-foreground"> · {p.designation}</span> : null}
              </Label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

export function GenerateOutreach({ fixedJobId, initialPersonId }: { fixedJobId?: string; initialPersonId?: string | null }) {
  const qc = useQueryClient();
  const [jobId, setJobId] = useState(fixedJobId ?? "");
  const [personIds, setPersonIds] = useState<string[]>(initialPersonId ? [initialPersonId] : []);
  const [types, setTypes] = useState<MessageType[]>(["linkedin_connection", "recruiter_email"]);
  const [runId, setRunId] = useState<string | null>(null);
  const generate = useMutation({
    mutationFn: () =>
      api.outreach.generate({ job_id: jobId, person_ids: personIds.length ? personIds : null, message_types: types }, newIdempotencyKey()),
    onSuccess: (res) => setRunId(res.workflow_id),
  });
  if (!hasEndpoint("POST", "/outreach/generate")) return null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!jobId || !types.length) return;
    generate.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Generate drafts</h2>
        </CardTitle>
        <CardDescription>Drafts use only verified facts and are never sent automatically.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={submit} className="space-y-4">
          {!fixedJobId && (
            <JobPicker
              value={jobId}
              onChange={(v) => {
                setJobId(v);
                setPersonIds([]);
              }}
            />
          )}
          {jobId && <PeoplePicker jobId={jobId} selected={personIds} onChange={setPersonIds} />}
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Message types</legend>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {MESSAGE_TYPES.map((t) => {
                const id = `gen-type-${t}`;
                return (
                  <div key={t} className="flex items-center gap-2">
                    <Checkbox
                      id={id}
                      checked={types.includes(t)}
                      onCheckedChange={(c) => setTypes(c === true ? [...types, t] : types.filter((x) => x !== t))}
                    />
                    <Label htmlFor={id} className="font-normal">
                      {MESSAGE_TYPE_LABELS[t]}
                    </Label>
                  </div>
                );
              })}
            </div>
          </fieldset>
          {generate.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(generate.error)}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" disabled={!jobId || !types.length || generate.isPending || Boolean(runId)}>
            {generate.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <WandSparklesIcon aria-hidden="true" />}
            Generate drafts
          </Button>
        </form>
        {runId && (
          <RunProgress
            runId={runId}
            title="Generating outreach drafts"
            onSettled={() => void qc.invalidateQueries({ queryKey: ["outreach"] })}
            actions={(run) =>
              isTerminalStatus(run.status) ? (
                <Button size="sm" variant="ghost" onClick={() => setRunId(null)}>
                  Dismiss
                </Button>
              ) : null
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

export function OutreachList({ jobId, status }: { jobId: string | null; status: string }) {
  const query = useQuery({
    queryKey: outreachKey(jobId, status),
    queryFn: () => api.outreach.list({ job_id: jobId ?? undefined, status: status || undefined, limit: 100 }),
  });
  return (
    <QueryView query={query} loadingLabel="Loading drafts…" errorTitle="Couldn't load outreach">
      {(data) => {
        const items = itemsOf(data);
        if (!items.length)
          return <EmptyState title="No outreach drafts" description="Generate drafts for a job to see them here." />;
        return (
          <div className="space-y-4">
            {items.map((o) => (
              <OutreachCard key={`${o.id}-${o.updated_at}`} item={o} />
            ))}
          </div>
        );
      }}
    </QueryView>
  );
}

/** Outreach for a single job (Job Intelligence → Outreach tab). */
export function JobOutreachPanel({ jobId }: { jobId: string }) {
  if (!hasEndpoint("GET", "/outreach")) return <NotAvailable feature="Outreach" endpoint="GET /outreach" />;
  return (
    <div className="space-y-6">
      <GenerateOutreach fixedJobId={jobId} />
      <div className="max-w-xs">
        <WriteDraftDialog defaultJobId={jobId} />
      </div>
      <OutreachList jobId={jobId} status="" />
    </div>
  );
}

export function OutreachView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const jobId = params.get("job_id");
  const personId = params.get("person_id");
  const status = params.get("status") ?? "";

  function setParam(key: string, value: string) {
    const p = new URLSearchParams(params.toString());
    if (value) p.set(key, value);
    else p.delete(key);
    if (key === "job_id" && !value) p.delete("person_id");
    router.replace(p.toString() ? `${pathname}?${p}` : pathname);
  }

  if (!hasEndpoint("GET", "/outreach")) {
    return (
      <>
        <PageHeader title="Outreach Center" />
        <NotAvailable feature="Outreach" endpoint="GET /outreach" />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Outreach Center" description="Review, edit, copy and approve drafts. Nothing is sent without your explicit approval." />
      <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
        <div className="space-y-4">
          <GenerateOutreach key={`${jobId ?? ""}-${personId ?? ""}`} fixedJobId={jobId ?? undefined} initialPersonId={personId} />
          <WriteDraftDialog defaultJobId={jobId} />
          <PendingApprovals actionTypes={["send_email"]} title="Emails awaiting approval" />
          <Card>
            <CardContent className="space-y-3 p-4">
              <Field id="o-status" label="Status">
                <NativeSelect value={status} onChange={(e) => setParam("status", e.target.value)}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s ? s.replace(/_/g, " ") : "All statuses"}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              {jobId && (
                <Button variant="outline" size="sm" onClick={() => setParam("job_id", "")}>
                  Show drafts for all jobs
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
        <OutreachList jobId={jobId} status={status} />
      </div>
    </>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { InfoIcon, Loader2Icon, MailIcon, SearchIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { EvidencePopover } from "@/components/evidence-popover";
import { ExternalLink } from "@/components/external-link";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { Time } from "@/components/time";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { PEOPLE_LABELS, scoreComponents } from "@/lib/shapes";
import { formatPercent, formatScore, titleCase } from "@/lib/utils";
import type { JobPeopleOut, JobPersonOut } from "@/types/models";
import { AddPersonDialog, AssociationBadge, ContactStatusSelect } from "./people-common";

export const jobPeopleKey = (jobId: string) => ["people", "job", jobId] as const;

function PersonCard({ person, jobId }: { person: JobPersonOut; jobId: string }) {
  const components = scoreComponents(person.components, ["T", "D", "C", "S"]);
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium">
              <span className="mr-1 text-muted-foreground">#{person.rank}</span>
              {person.name}
            </p>
            <p className="text-sm text-muted-foreground">
              {[person.designation, person.department].filter(Boolean).join(" · ") || "Designation not found"}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Badge variant="outline">{titleCase(person.role_category)}</Badge>
              <AssociationBadge status={person.association_status} />
            </div>
          </div>
          <div className="text-right">
            <p className="text-xl font-semibold tabular-nums">{formatScore(person.relevance_score, 1)}</p>
            <p className="text-xs text-muted-foreground">Relevance</p>
            <ProvenanceBadge kind="heuristic" className="mt-1" />
          </div>
        </div>

        <p className="whitespace-pre-wrap text-sm">{person.relevance_reason}</p>
        {components.length > 0 && (
          <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {components.map((c) => (
              <div key={c.key} className="flex gap-1">
                <dt>{PEOPLE_LABELS[c.key] ?? c.key}:</dt>
                <dd className="tabular-nums text-foreground">{formatScore(c.score ?? (typeof person.components[c.key] === "number" ? (person.components[c.key] as number) : null))}</dd>
              </div>
            ))}
            {person.confidence != null && (
              <div className="flex gap-1">
                <dt>Confidence:</dt>
                <dd className="text-foreground">{formatPercent(person.confidence)}</dd>
              </div>
            )}
          </dl>
        )}

        <div className="flex flex-wrap items-center gap-3 text-sm">
          {person.linkedin_url && <ExternalLink href={person.linkedin_url}>Public profile</ExternalLink>}
          {person.public_email && (
            <span className="inline-flex items-center gap-1">
              <MailIcon className="size-3.5" aria-hidden="true" />
              {person.public_email}
              <ProvenanceBadge kind="explicit" label="Found in public source" />
            </span>
          )}
          <EvidencePopover
            label={`${person.name} — evidence`}
            triggerLabel={`${person.evidence.length} source${person.evidence.length === 1 ? "" : "s"}`}
            evidence={person.evidence.map((e) => ({
              text: e.snippet,
              sourceUrl: e.source_url,
              sourceTitle: e.source_title,
              meta: (
                <span>
                  {titleCase(e.source_type)} · retrieved <Time value={e.retrieved_at} dateOnly />
                </span>
              ),
            }))}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <ContactStatusSelect personId={person.person_id} value={person.contact_status} name={person.name} />
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{person.outreach_count} outreach</span>
            {person.contact_status !== "do_not_contact" && hasEndpoint("POST", "/outreach/generate") && (
              <Button asChild size="sm" variant="outline">
                <Link href={`/outreach?job_id=${jobId}&person_id=${person.person_id}`}>Draft outreach</Link>
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function PeopleList({ data, jobId }: { data: JobPeopleOut; jobId: string }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 text-sm">
        <Badge variant="success">{data.verified_count} with evidence</Badge>
        <Badge variant="muted">{data.unavailable_count} of the {data.target ?? 15}-person target unavailable</Badge>
      </div>
      {data.coverage_note && (
        <Alert variant="info">
          <InfoIcon aria-hidden="true" />
          <AlertDescription>{data.coverage_note}</AlertDescription>
        </Alert>
      )}
      {data.items.length === 0 ? (
        <EmptyState
          title="No people found yet"
          description="Run discovery, or add someone you know. Only people with public evidence of a company association are listed."
        />
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.items.map((p) => (
            <PersonCard key={p.person_id} person={p} jobId={jobId} />
          ))}
        </div>
      )}
    </div>
  );
}

export function JobPeoplePanel({ jobId, companyName }: { jobId: string; companyName?: string | null }) {
  const qc = useQueryClient();
  const enabled = hasEndpoint("GET", "/jobs/{}/people");
  const query = useQuery({ queryKey: jobPeopleKey(jobId), queryFn: () => api.people.forJob(jobId), enabled });
  const [runId, setRunId] = useState<string | null>(null);
  const discover = useMutation({
    mutationFn: () => api.people.discover(jobId, newIdempotencyKey()),
    onSuccess: (res) => setRunId(res.workflow_id),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (!enabled) return <NotAvailable feature="People discovery" endpoint="GET /jobs/{id}/people" />;

  const latest = query.data?.latest_run;
  const activeRunId = runId ?? (latest && !isTerminalStatus(latest.status) ? latest.workflow_id : null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-sm text-muted-foreground">
          People are listed only when public evidence names them at this company. Emails appear only when that exact address was
          found in a public source.
        </p>
        <div className="flex gap-2">
          {hasEndpoint("POST", "/jobs/{}/people/discover") && (
            <Button onClick={() => discover.mutate()} disabled={discover.isPending || Boolean(activeRunId)}>
              {discover.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <SearchIcon aria-hidden="true" />}
              Find people
            </Button>
          )}
          <AddPersonDialog jobId={jobId} companyName={companyName} />
        </div>
      </div>
      {activeRunId && (
        <RunProgress
          runId={activeRunId}
          title="Finding people"
          onSettled={() => void qc.invalidateQueries({ queryKey: jobPeopleKey(jobId) })}
          actions={(run) =>
            isTerminalStatus(run.status) ? (
              <Button size="sm" variant="ghost" onClick={() => setRunId(null)}>
                Dismiss
              </Button>
            ) : null
          }
        />
      )}
      <QueryView query={query} loadingLabel="Loading people…" errorTitle="Couldn't load people">
        {(data) => <PeopleList data={data} jobId={jobId} />}
      </QueryView>
    </div>
  );
}

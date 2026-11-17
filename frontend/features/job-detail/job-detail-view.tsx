"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArchiveIcon, ArchiveRestoreIcon, ArrowLeftIcon, BookmarkCheckIcon, BookmarkIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ExternalLink } from "@/components/external-link";
import { ErrorState, LoadingState } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { PriorityBadge } from "@/components/score";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage, isApiError } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { formatScore, titleCase } from "@/lib/utils";
import type { JobDetail } from "@/types/models";
import { PrepareApplicationButton } from "@/features/applications/prepare-application";
import { JobOutreachPanel } from "@/features/outreach/outreach-view";
import { JobPeoplePanel } from "@/features/people/job-people-panel";
import { JobMatches, matchesKey } from "./job-matches";
import { JobOverview } from "./job-overview";

const TABS = ["overview", "matches", "people", "outreach", "description"] as const;
type Tab = (typeof TABS)[number];

export const jobKey = (id: string) => ["jobs", id] as const;

function Header({ job }: { job: JobDetail }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: (body: { saved?: boolean; archived?: boolean }) => api.jobs.patch(job.id, body),
    onSuccess: (_d, body) => {
      if (body.saved !== undefined) toast.success(body.saved ? "Job saved" : "Removed from saved");
      if (body.archived !== undefined) toast.success(body.archived ? "Job archived" : "Job restored");
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const archived = job.status === "archived";
  return (
    <div className="mb-6 space-y-3">
      <Link href="/jobs" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-4" aria-hidden="true" />
        Back to Job Search
      </Link>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{job.title || "Untitled job"}</h1>
          <p className="text-muted-foreground">{job.company?.name ?? "Unknown company"}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <PriorityBadge priority={job.priority} />
            <span className="text-sm tabular-nums">
              Job Score <strong>{formatScore(job.job_score, 1)}</strong>
            </span>
            {job.match_score != null && (
              <span className="text-sm tabular-nums text-muted-foreground">· Best match {formatScore(job.match_score, 1)}</span>
            )}
            {job.status !== "analyzed" && <Badge variant={job.status === "failed" ? "destructive" : "muted"}>{titleCase(job.status)}</Badge>}
            {job.has_application && <Badge variant="violet">Application started</Badge>}
            {job.application_url && <ExternalLink href={job.application_url}>Apply on employer site</ExternalLink>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {hasEndpoint("PATCH", "/jobs/{}") && (
            <>
              <Button variant="outline" onClick={() => patch.mutate({ saved: !job.saved })} disabled={patch.isPending} aria-pressed={job.saved}>
                {job.saved ? <BookmarkCheckIcon aria-hidden="true" /> : <BookmarkIcon aria-hidden="true" />}
                {job.saved ? "Saved" : "Save"}
              </Button>
              <Button variant="outline" onClick={() => patch.mutate({ archived: !archived })} disabled={patch.isPending}>
                {archived ? <ArchiveRestoreIcon aria-hidden="true" /> : <ArchiveIcon aria-hidden="true" />}
                {archived ? "Restore" : "Archive"}
              </Button>
            </>
          )}
          {!job.has_application && job.status === "analyzed" && <PrepareApplicationButton jobId={job.id} />}
          {job.has_application && hasEndpoint("GET", "/applications") && (
            <Button asChild variant="outline">
              <Link href="/applications">View application</Link>
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function JobDetailView({ id }: { id: string }) {
  const qc = useQueryClient();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tabParam = params.get("tab") as Tab | null;
  const tab: Tab = tabParam && TABS.includes(tabParam) ? tabParam : "overview";
  const query = useQuery({ queryKey: jobKey(id), queryFn: () => api.jobs.get(id) });

  if (query.isPending) return <LoadingState label="Loading job…" rows={6} />;
  if (query.isError) {
    if (isApiError(query.error) && query.error.status === 404) {
      return <ErrorState title="Job not found" error={query.error} />;
    }
    return <ErrorState title="Couldn't load this job" error={query.error} onRetry={() => void query.refetch()} />;
  }
  const job = query.data;
  const latest = job.latest_run;
  const running = latest && !isTerminalStatus(latest.status) && latest.status !== "awaiting_approval";

  return (
    <>
      <Header job={job} />
      {(running || job.status === "failed") && latest && (
        <RunProgress
          className="mb-6"
          runId={latest.workflow_id}
          title={titleCase(latest.workflow_name)}
          onSettled={() => {
            void qc.invalidateQueries({ queryKey: jobKey(id) });
            void qc.invalidateQueries({ queryKey: matchesKey(id) });
          }}
        />
      )}
      <Tabs
        value={tab}
        onValueChange={(v) => {
          const p = new URLSearchParams(params.toString());
          if (v === "overview") p.delete("tab");
          else p.set("tab", v);
          router.replace(p.toString() ? `${pathname}?${p}` : pathname, { scroll: false });
        }}
      >
        <TabsList aria-label="Job sections">
          <TabsTrigger value="overview">Intelligence</TabsTrigger>
          <TabsTrigger value="matches">Resume match</TabsTrigger>
          <TabsTrigger value="people">People</TabsTrigger>
          <TabsTrigger value="outreach">Outreach</TabsTrigger>
          <TabsTrigger value="description">Full description</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <JobOverview job={job} />
        </TabsContent>
        <TabsContent value="matches">
          <JobMatches jobId={id} jobTitle={job.title} />
        </TabsContent>
        <TabsContent value="people">
          <JobPeoplePanel jobId={id} companyName={job.company?.name} />
        </TabsContent>
        <TabsContent value="outreach">
          <JobOutreachPanel jobId={id} />
        </TabsContent>
        <TabsContent value="description">
          <Card>
            <CardContent className="p-5">
              <h2 className="sr-only">Full job description</h2>
              {job.description_text ? (
                <div className="max-w-3xl whitespace-pre-wrap text-sm leading-relaxed">{job.description_text}</div>
              ) : (
                <p className="text-sm text-muted-foreground">No description text stored.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}

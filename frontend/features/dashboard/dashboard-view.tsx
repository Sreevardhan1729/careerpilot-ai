"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, CalendarClockIcon, CpuIcon, RotateCwIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { PendingApprovals } from "@/features/approvals/pending-approvals";
import { EmptyState, QueryView } from "@/components/query-state";
import { RunStatusBadge } from "@/components/run-progress";
import { PriorityBadge } from "@/components/score";
import { Time } from "@/components/time";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { formatScore, titleCase } from "@/lib/utils";
import type { DashboardSummary } from "@/types/models";

function Stat({ label, value, href, hint }: { label: string; value: number | string; href?: string; hint?: string }) {
  const body = (
    <Card className="h-full transition-colors hover:border-primary/40">
      <CardContent className="p-4">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
  return href ? (
    <Link href={href} className="block rounded-xl focus-visible:outline-2 focus-visible:outline-ring">
      {body}
    </Link>
  ) : (
    body
  );
}

export function RuleBasedBanner() {
  return (
    <Alert variant="info">
      <CpuIcon aria-hidden="true" />
      <AlertTitle>Rule-based mode</AlertTitle>
      <AlertDescription>No LLM configured; extraction and drafts use deterministic rules.</AlertDescription>
    </Alert>
  );
}

function Summary({ data }: { data: DashboardSummary }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: (id: string) => api.runs.retry(id, newIdempotencyKey()),
    onSuccess: () => {
      toast.success("Run re-queued");
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canRetry = hasEndpoint("POST", "/agent-runs/{}/retry");
  const m = data.matches ?? {};
  const budget = data.llm_budget;
  const pct = budget?.limit ? Math.min(100, Math.round((budget.used_today / budget.limit) * 100)) : 0;
  const scheduler = data.scheduler ?? { last_run_at: null, last_status: null };

  return (
    <div className="space-y-6">
      {budget?.provider === "none" && <RuleBasedBanner />}
      {scheduler.stale && (
        <Alert variant="warning">
          <AlertTriangleIcon aria-hidden="true" />
          <AlertTitle>Scheduler looks stale</AlertTitle>
          <AlertDescription>
            {scheduler.last_run_at ? (
              <>
                The daily pipeline last ran <Time value={scheduler.last_run_at} />. Check the GitHub Actions cron, or run it now from
                Settings → Scheduler.
              </>
            ) : (
              <>The daily pipeline hasn&apos;t run yet. Run it from Settings → Scheduler, or wait for the scheduled trigger.</>
            )}
          </AlertDescription>
        </Alert>
      )}

      <section aria-labelledby="totals-heading">
        <h2 id="totals-heading" className="sr-only">
          Totals
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Total jobs" value={data.jobs_total} href="/jobs" />
          <Stat label="New today" value={data.jobs_new_today} href="/jobs?sort=-created_at" />
          <Stat label="Excellent matches" value={m.excellent ?? 0} href="/jobs?priority=excellent" />
          <Stat label="Strong matches" value={m.strong ?? 0} href="/jobs?priority=strong" />
          <Stat label="Moderate / low" value={`${m.moderate ?? 0} / ${m.low ?? 0}`} href="/jobs?priority=moderate" />
          <Stat
            label="People discovered"
            value={data.people_discovered}
            href="/people"
            hint={data.jobs_with_people != null ? `across ${data.jobs_with_people} jobs` : undefined}
          />
          <Stat label="Outreach awaiting review" value={data.outreach_awaiting_review} href="/outreach" />
          <Stat label="Applications submitted" value={data.applications_submitted} href="/applications" />
          <Stat label="Follow-ups due (7 days)" value={data.follow_ups_due?.length ?? 0} href="/applications" />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Scheduler</h2>
            </CardTitle>
            <CardDescription>Daily discovery pipeline</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">Last status</span>
              {scheduler.last_status ? <RunStatusBadge status={scheduler.last_status} /> : <span>Never run</span>}
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground">Last run</span>
              <Time value={scheduler.last_run_at} />
            </div>
            {scheduler.next_run_at && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Next run</span>
                <Time value={scheduler.next_run_at} />
              </div>
            )}
            {scheduler.failed_sources != null && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Failed sources</span>
                <span>{scheduler.failed_sources}</span>
              </div>
            )}
            <Link href="/settings?tab=scheduler" className="inline-block pt-1 text-primary underline-offset-2 hover:underline">
              Scheduler settings
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2>LLM budget</h2>
            </CardTitle>
            <CardDescription>
              {budget?.provider === "none" ? "Rule-based mode (no LLM)" : `${titleCase(budget?.provider ?? "")} · ${budget?.model ?? ""}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="tabular-nums">
              <span className="text-2xl font-semibold">{budget?.used_today ?? 0}</span>
              <span className="text-muted-foreground"> / {budget?.limit ?? 0} calls in the last 24 h</span>
            </p>
            <div
              role="meter"
              aria-label="LLM calls used today"
              aria-valuemin={0}
              aria-valuemax={budget?.limit ?? 0}
              aria-valuenow={budget?.used_today ?? 0}
              className="h-2 overflow-hidden rounded-full bg-muted"
            >
              <div className={pct >= 90 ? "h-full bg-red-600" : "h-full bg-primary"} style={{ width: `${pct}%` }} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="flex items-center gap-2">
                <CalendarClockIcon className="size-4" aria-hidden="true" />
                Upcoming follow-ups
              </h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.follow_ups_due?.length ? (
              <ul className="space-y-2 text-sm">
                {data.follow_ups_due.map((f) => (
                  <li key={f.application_id} className="flex items-center justify-between gap-2">
                    <Link href="/applications" className="truncate hover:underline">
                      {f.job_title || "Application"}
                    </Link>
                    <Time value={f.date} dateOnly className="shrink-0 text-muted-foreground" />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No follow-ups due in the next 7 days.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <PendingApprovals />

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Latest opportunities</h2>
          </CardTitle>
          <CardDescription>Top analysed jobs from the last 7 days, by Job Score (a prioritisation heuristic).</CardDescription>
        </CardHeader>
        <CardContent>
          {data.latest_jobs?.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Posted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.latest_jobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell>
                      <Link href={`/jobs/${j.id}`} className="font-medium text-primary hover:underline">
                        {j.title || "Untitled job"}
                      </Link>
                    </TableCell>
                    <TableCell>{j.company || "—"}</TableCell>
                    <TableCell className="tabular-nums">{formatScore(j.job_score, 1)}</TableCell>
                    <TableCell>
                      <PriorityBadge priority={j.priority} />
                    </TableCell>
                    <TableCell>
                      <Time value={j.posted_at} dateOnly />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <EmptyState
              title="No new analysed jobs this week"
              description="Analyse a job post, or configure sources so the daily run can discover jobs."
              action={
                <Button asChild variant="outline" size="sm">
                  <Link href="/jobs?analyze=1">Analyze a job</Link>
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Recent workflow failures</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data.recent_failures?.length ? (
            <ul className="divide-y">
              {data.recent_failures.map((f) => (
                <li key={f.workflow_id} className="flex flex-wrap items-start justify-between gap-2 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="font-medium">{titleCase(f.workflow_name)}</p>
                    <p className="text-muted-foreground">
                      {f.error_code ? <code className="mr-1 rounded bg-muted px-1">{f.error_code}</code> : null}
                      {f.message}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <Time value={f.at} />
                    </p>
                  </div>
                  {canRetry && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => retry.mutate(f.workflow_id)}
                      disabled={retry.isPending && retry.variables === f.workflow_id}
                      aria-label={`Retry ${titleCase(f.workflow_name)}`}
                    >
                      <RotateCwIcon aria-hidden="true" />
                      Retry
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No failed workflows. Nice.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function DashboardView() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 60_000 });
  return (
    <>
      <PageHeader title="Dashboard" description="Your job search at a glance." />
      <QueryView query={query} loadingLabel="Loading dashboard…" errorTitle="Couldn't load the dashboard">
        {(data) => <Summary data={data} />}
      </QueryView>
    </>
  );
}

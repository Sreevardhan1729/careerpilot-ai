"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, PlayIcon, RadarIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { RunProgress, RunStatusBadge } from "@/components/run-progress";
import { Time } from "@/components/time";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTimezone } from "@/hooks/use-me";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asArray, asRecord, asString, titleCase } from "@/lib/utils";

function errorsText(errors: unknown): string | null {
  if (!errors) return null;
  if (typeof errors === "string") return errors;
  const list = asArray(errors);
  if (list.length) return list.map((e) => asString(e) ?? asString(asRecord(e).message) ?? JSON.stringify(e)).join("; ");
  const rec = asRecord(errors);
  return Object.keys(rec).length ? JSON.stringify(rec) : null;
}

function RunsHistory() {
  const query = useQuery({ queryKey: ["scheduler", "runs"], queryFn: api.scheduler.runs });
  return (
    <QueryView query={query} loadingLabel="Loading runs…" errorTitle="Couldn't load run history">
      {(data) => (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Pipeline runs</h2>
              </CardTitle>
              <CardDescription>Daily pipeline and manual discovery runs.</CardDescription>
            </CardHeader>
            <CardContent>
              {data.runs?.length ? (
                <Table aria-label="Pipeline runs">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Run</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead>Finished</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.runs.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-medium">{titleCase(r.workflow_name)}</TableCell>
                        <TableCell>
                          <RunStatusBadge status={r.status} />
                        </TableCell>
                        <TableCell>
                          <Time value={r.created_at} />
                        </TableCell>
                        <TableCell>
                          <Time value={r.completed_at} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState title="No pipeline runs yet" description="Run discovery or the daily pipeline to see history here." />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Source crawls</h2>
              </CardTitle>
              <CardDescription>Each source runs in isolation; one failure doesn&apos;t stop the others.</CardDescription>
            </CardHeader>
            <CardContent>
              {data.crawl_runs?.length ? (
                <Table aria-label="Source crawls">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Source</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Found / new / merged / filtered</TableHead>
                      <TableHead>When</TableHead>
                      <TableHead>Errors</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.crawl_runs.map((c) => (
                      <TableRow key={c.id}>
                        <TableCell className="font-medium">{c.source}</TableCell>
                        <TableCell>
                          <RunStatusBadge status={c.status} />
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {[c.found, c.new, c.merged, c.filtered_out].map((n) => n ?? "—").join(" / ")}
                        </TableCell>
                        <TableCell>
                          <Time value={c.created_at} />
                        </TableCell>
                        <TableCell className="max-w-xs whitespace-pre-wrap text-xs text-red-700">{errorsText(c.errors)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">No crawls yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </QueryView>
  );
}

export function SchedulerTab() {
  const qc = useQueryClient();
  const tz = useTimezone();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings.get });
  const [runId, setRunId] = useState<{ id: string; title: string } | null>(null);
  const [date, setDate] = useState("");
  const settled = () => {
    void qc.invalidateQueries({ queryKey: ["scheduler"] });
    void qc.invalidateQueries({ queryKey: ["jobs"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const discover = useMutation({
    mutationFn: () => api.jobs.discover({}, newIdempotencyKey()),
    onSuccess: (res) => setRunId({ id: res.workflow_id, title: "Job discovery" }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const pipeline = useMutation({
    mutationFn: () => api.scheduler.run(date ? { date } : {}, newIdempotencyKey()),
    onSuccess: (res) => {
      if (res.existing) toast.info("The pipeline already ran for that date — showing that run.");
      setRunId({ id: res.run.workflow_id, title: res.existing ? "Daily pipeline (existing run)" : "Daily pipeline" });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const canDiscover = hasEndpoint("POST", "/jobs/discover");
  const canRun = hasEndpoint("POST", "/scheduler/run");
  const canHistory = hasEndpoint("GET", "/scheduler/runs");
  const sched = asRecord(settings.data?.scheduler);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Schedule</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {settings.isPending ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : settings.isError ? (
            <p className="text-red-700">{errorMessage(settings.error)}</p>
          ) : (
            <>
              <p>
                <span className="text-muted-foreground">Preferred local time: </span>
                {settings.data.scheduler_local_time} ({tz})
              </p>
              {asString(sched.trigger) && (
                <p>
                  <span className="text-muted-foreground">Trigger: </span>
                  {asString(sched.trigger)}
                </p>
              )}
              {asString(sched.note) && <p className="text-muted-foreground">{asString(sched.note)}</p>}
            </>
          )}
        </CardContent>
      </Card>

      {!canDiscover && !canRun ? (
        <NotAvailable feature="Manual discovery and pipeline runs" endpoint="POST /jobs/discover, POST /scheduler/run" />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Run now</h2>
            </CardTitle>
            <CardDescription>Limited to a few runs per hour. Runs continue in the background if you leave this page.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-4 md:flex-row md:items-end">
              {canDiscover && (
                <div className="space-y-1">
                  <Button onClick={() => discover.mutate()} disabled={discover.isPending || Boolean(runId)}>
                    {discover.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <RadarIcon aria-hidden="true" />}
                    Discover jobs now
                  </Button>
                  <p className="text-xs text-muted-foreground">Discovery, analysis, matching and ranking for enabled sources.</p>
                </div>
              )}
              {canRun && (
                <div className="flex items-end gap-2">
                  <Field id="pipeline-date" label="Pipeline date (optional)">
                    <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
                  </Field>
                  <Button variant="outline" onClick={() => pipeline.mutate()} disabled={pipeline.isPending || Boolean(runId)}>
                    {pipeline.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <PlayIcon aria-hidden="true" />}
                    Run daily pipeline
                  </Button>
                </div>
              )}
            </div>
            {(discover.error || pipeline.error) && (
              <Alert variant="destructive">
                <AlertDescription>{errorMessage(discover.error ?? pipeline.error)}</AlertDescription>
              </Alert>
            )}
            {runId && (
              <RunProgress
                runId={runId.id}
                title={runId.title}
                onSettled={settled}
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
      )}

      {canHistory ? <RunsHistory /> : <NotAvailable feature="Run history" endpoint="GET /scheduler/runs" />}
    </div>
  );
}

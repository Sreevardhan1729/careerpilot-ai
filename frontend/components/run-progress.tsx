"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2Icon, CircleDashedIcon, CircleIcon, Loader2Icon, PauseCircleIcon, RotateCwIcon, XCircleIcon } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/query-state";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAgentRun } from "@/hooks/use-agent-run";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { runStatusLabel } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { effectiveNodes, progressNodes, runError } from "@/lib/shapes";
import { cn, titleCase } from "@/lib/utils";
import type { AgentRunOut } from "@/types/models";

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  queued: "muted",
  running: "info",
  awaiting_approval: "warning",
  completed: "success",
  partially_completed: "warning",
  failed: "destructive",
  cancelled: "muted",
};

export function RunStatusBadge({ status }: { status: string | null | undefined }) {
  return <Badge variant={STATUS_VARIANT[status ?? ""] ?? "secondary"}>{runStatusLabel(status)}</Badge>;
}

function NodeIcon({ status }: { status: string }) {
  const cls = "size-4 shrink-0";
  switch (status) {
    case "completed":
      return <CheckCircle2Icon className={cn(cls, "text-emerald-600")} aria-hidden="true" />;
    case "running":
      return <Loader2Icon className={cn(cls, "animate-spin text-sky-600")} aria-hidden="true" />;
    case "failed":
      return <XCircleIcon className={cn(cls, "text-red-600")} aria-hidden="true" />;
    case "awaiting_approval":
      return <PauseCircleIcon className={cn(cls, "text-amber-600")} aria-hidden="true" />;
    case "skipped":
      return <CircleDashedIcon className={cn(cls, "text-muted-foreground")} aria-hidden="true" />;
    default:
      return <CircleIcon className={cn(cls, "text-muted-foreground")} aria-hidden="true" />;
  }
}

/**
 * Live view of an async workflow (FR-UI-03): every node in `progress[]` with its status, errors with Retry,
 * and a hook for the approval UI when the run pauses at `awaiting_approval`.
 */
export function RunProgress({
  runId,
  title,
  onSettled,
  renderPaused,
  actions,
  className,
}: {
  runId: string;
  title?: string;
  onSettled?: (run: AgentRunOut) => void;
  renderPaused?: (run: AgentRunOut) => ReactNode;
  actions?: (run: AgentRunOut) => ReactNode;
  className?: string;
}) {
  const runQuery = useAgentRun(runId, { onSettled });
  const retry = useMutation({
    mutationFn: () => api.runs.retry(runId, newIdempotencyKey()),
    onSuccess: () => {
      toast.success("Run re-queued");
      runQuery.restartPolling();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (runQuery.isPending) {
    return (
      <div role="status" className={cn("flex items-center gap-2 rounded-lg border p-4 text-sm", className)}>
        <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
        Starting workflow…
      </div>
    );
  }
  if (runQuery.isError || !runQuery.run) {
    return <ErrorState className={className} title="Couldn't load workflow status" error={runQuery.error} onRetry={() => runQuery.restartPolling()} />;
  }

  const run = runQuery.run;
  const nodes = effectiveNodes(progressNodes(run.progress), run.status);
  const err = runError(run.error);
  const canRetry = run.status === "failed" && hasEndpoint("POST", "/agent-runs/{}/retry");

  return (
    <div className={cn("space-y-3 rounded-lg border bg-card p-4", className)} aria-busy={!runQuery.isTerminal && !runQuery.isPaused}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{title ?? titleCase(run.workflow_name)}</p>
          {run.current_node && !runQuery.isTerminal && (
            <p className="text-xs text-muted-foreground">Current step: {titleCase(run.current_node)}</p>
          )}
        </div>
        <div aria-live="polite">
          <RunStatusBadge status={run.status} />
        </div>
      </div>

      {nodes.length > 0 && (
        <ol className="space-y-1.5" aria-label="Workflow steps">
          {nodes.map((n, i) => (
            <li key={`${n.node}-${i}`} className="flex items-start gap-2 text-sm">
              <NodeIcon status={n.status} />
              <div className="min-w-0">
                <span>{titleCase(n.node)}</span>
                <span className="sr-only"> — {runStatusLabel(n.status)}</span>
                {n.error && <p className="text-xs text-red-700">{n.error}</p>}
                {n.detail && typeof n.detail.model_id === "string" && (
                  <p className="text-xs text-muted-foreground">Model: {n.detail.model_id}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}

      {run.children && run.children.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Follow-up workflows</p>
          <ul className="space-y-1">
            {run.children.map((c) => (
              <li key={c.workflow_id} className="flex items-center gap-2 text-sm">
                <NodeIcon status={c.status} />
                {titleCase(c.workflow_name)}
                <RunStatusBadge status={c.status} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {err && (run.status === "failed" || run.status === "partially_completed") && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">
          <p className="font-medium">{err.code ? titleCase(err.code) : "Error"}</p>
          {err.message && <p>{err.message}</p>}
        </div>
      )}

      {runQuery.isPaused && renderPaused?.(run)}

      <div className="flex flex-wrap gap-2">
        {canRetry && (
          <Button size="sm" variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending}>
            {retry.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <RotateCwIcon aria-hidden="true" />}
            Retry
          </Button>
        )}
        {actions?.(run)}
      </div>
    </div>
  );
}

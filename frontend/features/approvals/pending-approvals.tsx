"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, XIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/query-state";
import { Time } from "@/components/time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asArray, asRecord, asString, titleCase } from "@/lib/utils";
import type { ApprovalOut } from "@/types/models";

export const pendingApprovalsKey = ["approvals", "pending"] as const;

export const ACTION_LABELS: Record<string, string> = {
  send_email: "Send email",
  submit_application: "Submit application",
  activate_resume_version: "Activate tailored resume",
  share_personal_info: "Share personal info",
  external_action: "External action",
};

/** One-line plain-text summary of what an approval would do. */
export function approvalSummary(a: ApprovalOut): string {
  const p = asRecord(a.payload_preview);
  if (a.action_type === "send_email") return [asString(p.to) && `To ${asString(p.to)}`, asString(p.subject)].filter(Boolean).join(" · ");
  if (a.action_type === "submit_application") return asString(asRecord(p.job).title) ?? "Application package";
  if (a.action_type === "activate_resume_version") {
    const changes = asArray(p.changes).length;
    return [asString(p.resume), asString(p.version_number) && `v${asString(p.version_number)}`, `${changes} change${changes === 1 ? "" : "s"}`]
      .filter(Boolean)
      .join(" · ");
  }
  return titleCase(a.reference_type);
}

function reviewHref(a: ApprovalOut): string | null {
  if (a.reference_type === "outreach") return "/outreach";
  if (a.reference_type === "application") return "/applications";
  if (a.reference_type === "resume_version") return "/resumes";
  return null;
}

export function useRejectApproval(onDone?: () => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.approvals.reject(id),
    onSuccess: () => {
      toast.success("Approval rejected — nothing was executed.");
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["outreach"] });
      void qc.invalidateQueries({ queryKey: ["resumes"] });
      onDone?.();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

/** Pending approvals with a Reject button each (GET /approvals?status=pending). */
export function PendingApprovals({ actionTypes, title = "Pending approvals" }: { actionTypes?: string[]; title?: string }) {
  const enabled = hasEndpoint("GET", "/approvals");
  const query = useQuery({ queryKey: pendingApprovalsKey, queryFn: () => api.approvals.list({ status: "pending" }), enabled });
  const reject = useRejectApproval();
  if (!enabled) return null;
  const canReject = hasEndpoint("POST", "/approvals/{}/reject");
  const items = (Array.isArray(query.data) ? query.data : (query.data?.items ?? [])).filter(
    (a) => a.status === "pending" && (!actionTypes || actionTypes.includes(a.action_type)),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>
            {title}
            {items.length > 0 && <span className="text-sm font-normal text-muted-foreground"> ({items.length})</span>}
          </h2>
        </CardTitle>
        <CardDescription>Nothing here runs until you approve it. Rejecting discards the request.</CardDescription>
      </CardHeader>
      <CardContent>
        {query.isPending ? (
          <LoadingState rows={1} label="Loading approvals…" />
        ) : query.isError ? (
          <ErrorState error={query.error} title="Couldn't load approvals" onRetry={() => void query.refetch()} />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending approvals.</p>
        ) : (
          <ul className="divide-y">
            {items.map((a) => {
              const href = reviewHref(a);
              return (
                <li key={a.approval_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-1.5 font-medium">
                      <Badge variant="warning">{ACTION_LABELS[a.action_type] ?? titleCase(a.action_type)}</Badge>
                      <span className="truncate">{approvalSummary(a)}</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Expires <Time value={a.expires_at} />
                    </p>
                  </div>
                  <div className="flex gap-1">
                    {href && (
                      <Button asChild size="sm" variant="outline">
                        <Link href={href}>Review</Link>
                      </Button>
                    )}
                    {canReject && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-red-700 hover:text-red-800"
                        onClick={() => reject.mutate(a.approval_id)}
                        disabled={reject.isPending && reject.variables === a.approval_id}
                        aria-label={`Reject: ${ACTION_LABELS[a.action_type] ?? a.action_type} — ${approvalSummary(a)}`}
                      >
                        {reject.isPending && reject.variables === a.approval_id ? (
                          <Loader2Icon className="animate-spin" aria-hidden="true" />
                        ) : (
                          <XIcon aria-hidden="true" />
                        )}
                        Reject
                      </Button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

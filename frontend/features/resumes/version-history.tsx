"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardCheckIcon, Loader2Icon, XIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Time } from "@/components/time";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { pendingApprovalsKey, useRejectApproval } from "@/features/approvals/pending-approvals";
import { hasEndpoint } from "@/lib/capabilities";
import { api, itemsOf } from "@/lib/endpoints";
import { titleCase } from "@/lib/utils";
import type { ApprovalOut, ResumeDetail } from "@/types/models";
import { DownloadButton } from "./resume-actions";
import { VersionApprovalDialog } from "./tailored-version-dialog";

export const VERSION_STATUS: Record<string, { label: string; variant: BadgeVariant }> = {
  original: { label: "Original", variant: "outline" },
  pending_approval: { label: "Pending approval", variant: "warning" },
  approved: { label: "Approved", variant: "success" },
  rejected: { label: "Rejected", variant: "destructive" },
  draft: { label: "Draft", variant: "muted" },
};

export function VersionStatusBadge({ status }: { status: string }) {
  const meta = VERSION_STATUS[status] ?? { label: titleCase(status), variant: "secondary" as BadgeVariant };
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}

export function VersionHistory({ resume }: { resume: ResumeDetail }) {
  const hasPending = resume.versions.some((v) => v.approval_status === "pending_approval");
  const approvalsEnabled = hasPending && hasEndpoint("GET", "/approvals");
  const approvals = useQuery({ queryKey: pendingApprovalsKey, queryFn: () => api.approvals.list({ status: "pending" }), enabled: approvalsEnabled });
  const byVersion = new Map<string, ApprovalOut>();
  for (const a of itemsOf(approvals.data)) {
    if (a.reference_type === "resume_version" && a.status === "pending") byVersion.set(a.reference_id, a);
  }
  const [reviewing, setReviewing] = useState<{ versionId: string; approval: ApprovalOut } | null>(null);
  const reject = useRejectApproval();
  const canActivate = hasEndpoint("POST", "/resumes/{}/versions/{}/activate");
  const canReject = hasEndpoint("POST", "/approvals/{}/reject");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Version history</h2>
        </CardTitle>
        <CardDescription>The original upload is never modified. Tailored versions are DOCX files and need your approval to become current.</CardDescription>
      </CardHeader>
      <CardContent>
        <Table aria-label="Versions">
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Change</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {resume.versions.map((v) => {
              const approval = byVersion.get(v.id);
              return (
                <TableRow key={v.id}>
                  <TableCell className="font-medium">
                    v{v.version_number}
                    {v.id === resume.current_version_id && (
                      <Badge variant="info" className="ml-2">
                        Current
                      </Badge>
                    )}
                    <div className="text-xs font-normal text-muted-foreground">{v.original_filename}</div>
                  </TableCell>
                  <TableCell>
                    <Time value={v.created_at} />
                  </TableCell>
                  <TableCell>
                    {v.approval_status === "pending_approval" && approvals.isSuccess && !approval ? (
                      <Badge variant="muted" title="Its approval was rejected or expired, so it was never activated.">
                        Not activated — approval closed
                      </Badge>
                    ) : (
                      <VersionStatusBadge status={v.approval_status} />
                    )}
                  </TableCell>
                  <TableCell className="max-w-sm">
                    {v.change_summary ?? (v.parent_version_id ? "Derived version" : "Original upload")}
                    {v.job_id && (
                      <Link href={`/jobs/${v.job_id}?tab=matches`} className="ml-1 text-primary hover:underline">
                        (tailored for a job)
                      </Link>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap justify-end gap-1">
                      {v.approval_status === "pending_approval" && approvals.isPending && approvalsEnabled && (
                        <Loader2Icon className="size-4 animate-spin" aria-label="Loading approval" />
                      )}
                      {approval && canActivate && (
                        <Button size="sm" onClick={() => setReviewing({ versionId: v.id, approval })}>
                          <ClipboardCheckIcon aria-hidden="true" />
                          Review and activate
                        </Button>
                      )}
                      {approval && canReject && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-red-700 hover:text-red-800"
                          onClick={() => reject.mutate(approval.approval_id)}
                          disabled={reject.isPending}
                          aria-label={`Reject version ${v.version_number}`}
                        >
                          <XIcon aria-hidden="true" />
                          Reject
                        </Button>
                      )}
                      <DownloadButton resumeId={resume.id} versionId={v.id} filename={v.original_filename} label={`Download v${v.version_number}`} />
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
      {reviewing && (
        <VersionApprovalDialog
          resumeId={resume.id}
          versionId={reviewing.versionId}
          approval={reviewing.approval}
          open
          onOpenChange={(o) => {
            if (!o) setReviewing(null);
          }}
        />
      )}
    </Card>
  );
}

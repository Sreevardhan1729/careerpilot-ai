"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ClipboardListIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { errorMessage, isApiError, newIdempotencyKey } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { applicationPreview, runApproval } from "@/lib/shapes";
import { asRecord, asString } from "@/lib/utils";
import type { AgentRunOut } from "@/types/models";
import { ApplicationPreviewView, ApproveApplicationButton, ConfirmSubmissionButton } from "./application-preview";

/** The application id for a prepare run: subject (type application) or output.application_id. */
export function applicationIdFromRun(run: AgentRunOut): string | null {
  if (run.subject?.type === "application") return run.subject.id;
  return asString(asRecord(run.output).application_id);
}

function PausedApproval({ run, onApproved }: { run: AgentRunOut; onApproved: () => void }) {
  const approval = runApproval(run.approval);
  const applicationId = applicationIdFromRun(run);
  if (!approval) return <p className="text-sm text-muted-foreground">Waiting for the approval details…</p>;
  const preview = applicationPreview(approval.payload_preview);
  return (
    <div className="space-y-3 rounded-md border border-amber-300 bg-amber-50/60 p-3">
      <p className="text-sm font-medium">Review the prepared application. Nothing is submitted until you approve.</p>
      {preview && <ApplicationPreviewView preview={preview} />}
      {applicationId ? (
        <ApproveApplicationButton
          applicationId={applicationId}
          approvalId={approval.approval_id}
          payloadHash={approval.payload_hash}
          expiresAt={approval.expires_at}
          preview={preview}
          onApproved={onApproved}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Open the Applications page to approve.</p>
      )}
    </div>
  );
}

export function PrepareApplicationButton({ jobId, label = "Prepare application" }: { jobId: string; label?: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const [approvedAppId, setApprovedAppId] = useState<string | null>(null);
  const prepare = useMutation({
    mutationFn: () => api.applications.prepare({ job_id: jobId }, newIdempotencyKey()),
    onSuccess: (res) => setRunId(res.workflow_id),
  });
  if (!hasEndpoint("POST", "/applications/prepare")) return null;
  const duplicate = isApiError(prepare.error) && prepare.error.code === "duplicate";

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          setRunId(null);
          setApprovedAppId(null);
          prepare.reset();
        }
      }}
    >
      <Button
        variant="outline"
        onClick={() => {
          setOpen(true);
          if (!runId) prepare.mutate();
        }}
      >
        <ClipboardListIcon aria-hidden="true" />
        {label}
      </Button>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Prepare application</DialogTitle>
          <DialogDescription>
            Picks the best resume version and drafts answers from your confirmed profile facts. You review and approve before anything else
            happens.
          </DialogDescription>
        </DialogHeader>
        {prepare.isPending && (
          <p role="status" className="flex items-center gap-2 text-sm">
            <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
            Starting…
          </p>
        )}
        {prepare.error && (
          <Alert variant={duplicate ? "info" : "destructive"}>
            <AlertDescription>
              {duplicate ? "You already have an application for this job." : errorMessage(prepare.error)}{" "}
              <Link href="/applications" className="underline">
                Open Applications
              </Link>
            </AlertDescription>
          </Alert>
        )}
        {runId && (
          <RunProgress
            runId={runId}
            title="Preparing application"
            onSettled={() => void qc.invalidateQueries({ queryKey: ["applications"] })}
            renderPaused={(run) =>
              approvedAppId ? null : (
                <PausedApproval
                  run={run}
                  onApproved={() => {
                    setApprovedAppId(applicationIdFromRun(run));
                  }}
                />
              )
            }
          />
        )}
        {approvedAppId && (
          <Alert variant="success">
            <AlertDescription className="space-y-2">
              <p>Approved and ready to submit. Complete the manual steps on the employer&apos;s site, then record your submission.</p>
              <ConfirmSubmissionButton applicationId={approvedAppId} />
            </AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  );
}

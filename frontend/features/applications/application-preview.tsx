"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, ClipboardCheckIcon, Loader2Icon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApprovalDialog } from "@/components/approval-dialog";
import { ExternalLink } from "@/components/external-link";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { useRejectApproval } from "@/features/approvals/pending-approvals";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import type { ApplicationPreview } from "@/lib/shapes";
import { asString, cn, titleCase } from "@/lib/utils";
import type { ConfirmSubmissionIn } from "@/types/models";

/** The exact application package being approved: resume version, answers (gaps highlighted), and manual steps. */
export function ApplicationPreviewView({ preview }: { preview: ApplicationPreview }) {
  const rv = preview.resumeVersion;
  const rvLabel = asString(rv.label) ?? asString(rv.resume_label) ?? asString(rv.original_filename) ?? asString(rv.filename);
  const rvNumber = asString(rv.version_number);
  const needsInput = preview.answers.filter((a) => a.needsUserInput).length;
  return (
    <div className="space-y-4 text-sm">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Resume version</h3>
        <p>
          {rvLabel ?? "Selected resume"}
          {rvNumber && <span className="text-muted-foreground"> · v{rvNumber}</span>}
          {asString(rv.id) && <span className="ml-1 text-xs text-muted-foreground">({asString(rv.id)})</span>}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Submission</h3>
        <Badge variant="outline">{preview.submissionMethod === "supported_integration" ? "Supported integration" : "Manual (you submit)"}</Badge>
        {preview.applicationUrl && <ExternalLink href={preview.applicationUrl}>Application page</ExternalLink>}
      </div>
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Answers {needsInput > 0 && <span className="normal-case text-amber-800">· {needsInput} need your input</span>}
        </h3>
        {preview.answers.length ? (
          <ul className="space-y-2">
            {preview.answers.map((a, i) => (
              <li key={i} className={cn("rounded-md border p-2", a.needsUserInput && "border-amber-400 bg-amber-50")}>
                <p className="font-medium">{a.question}</p>
                {a.needsUserInput && (
                  <Badge variant="warning" className="my-1">
                    <AlertTriangleIcon aria-hidden="true" />
                    Needs your input
                  </Badge>
                )}
                <p className="whitespace-pre-wrap">{a.answer || <span className="text-muted-foreground">No answer — fill this in yourself.</span>}</p>
                {a.sourceFactIds.length > 0 && <p className="text-xs text-muted-foreground">From {a.sourceFactIds.length} confirmed profile fact(s)</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No application questions.</p>
        )}
      </div>
      {preview.manualSteps.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Manual steps</h3>
          <ol className="list-decimal space-y-1 pl-5">
            {preview.manualSteps.map((s, i) => (
              <li key={i} className="whitespace-pre-wrap">
                {s}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/** Approve an application package (POST /applications/{id}/approve) with an explicit confirm step. */
export function ApproveApplicationButton({
  applicationId,
  approvalId,
  payloadHash,
  expiresAt,
  preview,
  onApproved,
}: {
  applicationId: string;
  approvalId: string;
  payloadHash: string;
  expiresAt?: string | null;
  preview: ApplicationPreview | null;
  onApproved?: () => void;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState<string | null>(null);
  const reject = useRejectApproval(() => setOpen(false));
  const approve = useMutation({
    mutationFn: () => api.applications.approve(applicationId, { approval_id: approvalId, payload_hash: payloadHash, confirm: true }, key as string),
    onSuccess: () => {
      toast.success("Approved. Complete the manual steps, then confirm your submission.");
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      onApproved?.();
    },
  });
  if (!hasEndpoint("POST", "/applications/{}/approve")) return null;
  const canReject = hasEndpoint("POST", "/approvals/{}/reject");
  return (
    <>
      <Button
        size="sm"
        onClick={() => {
          setKey(newIdempotencyKey());
          approve.reset();
          setOpen(true);
        }}
      >
        <ClipboardCheckIcon aria-hidden="true" />
        Review and approve…
      </Button>
      <ApprovalDialog
        open={open}
        onOpenChange={setOpen}
        title="Approve this application"
        description="Approving records this exact package. In the MVP every platform is manual: nothing is submitted for you."
        expiresAt={expiresAt}
        confirmLabel="Approve application"
        acknowledgement="I have reviewed the resume version, every answer, and the steps above, and I approve this application package."
        onConfirm={() => approve.mutate()}
        pending={approve.isPending}
        error={approve.error}
        onReject={canReject ? () => reject.mutate(approvalId) : undefined}
        rejecting={reject.isPending}
      >
        {preview ? <ApplicationPreviewView preview={preview} /> : <p className="text-sm text-muted-foreground">No preview was returned.</p>}
      </ApprovalDialog>
    </>
  );
}

/** Record manual submission evidence (POST /applications/{id}/confirm-submission) → status becomes "applied". */
export function ConfirmSubmissionButton({ applicationId, jobTitle }: { applicationId: string; jobTitle?: string | null }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [evidenceType, setEvidenceType] = useState<ConfirmSubmissionIn["evidence_type"]>("external_receipt");
  const [detail, setDetail] = useState("");
  const [key, setKey] = useState<string | null>(null);
  const confirm = useMutation({
    mutationFn: () => api.applications.confirmSubmission(applicationId, { evidence_type: evidenceType, detail: detail.trim() }, key as string),
    onSuccess: () => {
      toast.success("Submission recorded — marked as applied.");
      setOpen(false);
      setDetail("");
      void qc.invalidateQueries({ queryKey: ["applications"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  if (!hasEndpoint("POST", "/applications/{}/confirm-submission")) return null;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (detail.trim().length < 3) return;
    confirm.mutate();
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          setKey(newIdempotencyKey());
          confirm.reset();
          setOpen(true);
        }}
      >
        Confirm submission…
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm you submitted{jobTitle ? ` “${jobTitle}”` : ""}</DialogTitle>
            <DialogDescription>&quot;Applied&quot; needs evidence: a receipt from the employer, or your own attestation (labelled as such).</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-4">
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Evidence type</legend>
              {(
                [
                  ["external_receipt", "External receipt", "A confirmation email, application ID or portal screenshot description."],
                  ["user_attestation", "My attestation", "I submitted it but have no receipt. Recorded as self-reported."],
                ] as const
              ).map(([value, label, hint]) => (
                <div key={value} className="flex items-start gap-2">
                  <input
                    type="radio"
                    id={`ev-${applicationId}-${value}`}
                    name={`ev-${applicationId}`}
                    value={value}
                    checked={evidenceType === value}
                    onChange={() => setEvidenceType(value)}
                    className="mt-1 size-4 accent-[var(--primary)]"
                  />
                  <Label htmlFor={`ev-${applicationId}-${value}`} className="font-normal leading-snug">
                    <span className="font-medium">{label}</span>
                    <span className="block text-xs text-muted-foreground">{hint}</span>
                  </Label>
                </div>
              ))}
            </fieldset>
            <Field id={`ev-detail-${applicationId}`} label="Details" required hint="At least 3 characters, e.g. the confirmation number.">
              <Textarea rows={3} value={detail} onChange={(e) => setDetail(e.target.value)} maxLength={2000} />
            </Field>
            {confirm.error && (
              <Alert variant="destructive">
                <AlertTitle>Couldn&apos;t record submission</AlertTitle>
                <AlertDescription>{errorMessage(confirm.error)}</AlertDescription>
              </Alert>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={confirm.isPending || detail.trim().length < 3}>
                {confirm.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                Record as applied
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function evidenceLabel(evidence: Record<string, unknown> | null | undefined): string | null {
  if (!evidence) return null;
  const type = asString(evidence.evidence_type) ?? asString(evidence.type);
  return type ? titleCase(type) : null;
}

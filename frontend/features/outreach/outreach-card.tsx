"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertOctagonIcon, AlertTriangleIcon, CheckIcon, Loader2Icon, MailIcon, SaveIcon, SendIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ApprovalDialog, PayloadField } from "@/components/approval-dialog";
import { CopyButton } from "@/components/copy-button";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { Time } from "@/components/time";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRejectApproval } from "@/features/approvals/pending-approvals";
import { useGoogleConnected } from "@/hooks/use-me";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isRuleBased } from "@/lib/analysis";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { claimCheck, personalizationEvidence } from "@/lib/shapes";
import { asArray, asString, titleCase } from "@/lib/utils";
import type { ApprovalOut, OutreachOut } from "@/types/models";

export const MESSAGE_TYPE_LABELS: Record<string, string> = {
  linkedin_connection: "LinkedIn connection note",
  linkedin_follow_up: "LinkedIn follow-up",
  referral_request: "Referral request",
  hiring_manager_message: "Hiring manager message",
  recruiter_email: "Recruiter email",
  recruiter_follow_up: "Recruiter follow-up",
  thank_you: "Thank-you note",
};

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  draft: "muted",
  edited: "info",
  approved: "violet",
  gmail_draft_created: "info",
  sent: "success",
  manually_sent: "success",
  discarded: "outline",
};

/** Default LinkedIn connection note limit (FR-OUT-04, configurable on the backend). */
const LINKEDIN_NOTE_LIMIT = 200;

const DONE_STATUSES = ["sent", "manually_sent", "discarded"];

export function OutreachCard({ item }: { item: OutreachOut }) {
  const qc = useQueryClient();
  const googleConnected = useGoogleConnected();
  const [subject, setSubject] = useState(item.subject ?? "");
  const [body, setBody] = useState(item.body);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [approval, setApproval] = useState<ApprovalOut | null>(null);
  const [approveKey, setApproveKey] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["outreach"] });
  const dirty = body !== item.body || (item.channel === "email" && subject !== (item.subject ?? ""));
  const done = DONE_STATUSES.includes(item.status);
  const checks = claimCheck(item.claim_check);
  const evidence = personalizationEvidence(item.personalization_evidence);
  const isEmail = item.channel === "email";
  const isConnectionNote = item.message_type === "linkedin_connection";
  const overLimit = isConnectionNote && body.length > LINKEDIN_NOTE_LIMIT;
  const headingId = `outreach-${item.id}-title`;

  const save = useMutation({
    mutationFn: () => api.outreach.patch(item.id, { body, ...(isEmail ? { subject: subject || null } : {}) }),
    onSuccess: () => {
      toast.success("Draft saved");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const discard = useMutation({
    mutationFn: () => api.outreach.patch(item.id, { discard: true }),
    onSuccess: () => {
      toast.success("Draft discarded");
      setConfirmDiscard(false);
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const gmailDraft = useMutation({
    mutationFn: () => api.outreach.gmailDraft(item.id, newIdempotencyKey()),
    onSuccess: () => {
      toast.success("Gmail draft created — review and send it from Gmail.");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const markSent = useMutation({
    mutationFn: () => api.outreach.markSent(item.id, newIdempotencyKey()),
    onSuccess: () => {
      toast.success("Marked as sent");
      void invalidate();
      void qc.invalidateQueries({ queryKey: ["people"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const requestApproval = useMutation({
    mutationFn: () => api.outreach.requestApproval(item.id, newIdempotencyKey()),
    onSuccess: (a) => {
      setApproval(a);
      setApproveKey(newIdempotencyKey());
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const approve = useMutation({
    mutationFn: () => {
      if (!approval || !approveKey) throw new Error("No approval in progress.");
      return api.outreach.approve(item.id, { approval_id: approval.approval_id, payload_hash: approval.payload_hash, confirm: true }, approveKey);
    },
    onSuccess: (res) => {
      toast.success(res.status === "sent" ? "Email sent" : `Approved (${res.status})`);
      setApproval(null);
      void invalidate();
      void qc.invalidateQueries({ queryKey: ["people"] });
    },
  });

  const rejectApproval = useRejectApproval(() => setApproval(null));
  const canPatch = hasEndpoint("PATCH", "/outreach/{}");
  const canGmail = isEmail && googleConnected && hasEndpoint("POST", "/outreach/{}/gmail-draft") && !done && !item.gmail_draft_id;
  const canMarkSent = !isEmail && hasEndpoint("POST", "/outreach/{}/mark-sent") && !done;
  const canSend =
    isEmail &&
    googleConnected &&
    hasEndpoint("POST", "/outreach/{}/request-approval") &&
    hasEndpoint("POST", "/outreach/{}/approve") &&
    !done &&
    Boolean(item.recipient_email);
  const preview = approval?.payload_preview ?? {};
  const attachments = asArray(preview.attachments);

  return (
    <Card aria-labelledby={headingId}>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 id={headingId} className="font-semibold">
              {MESSAGE_TYPE_LABELS[item.message_type] ?? titleCase(item.message_type)}
              {item.recipient_name && <span className="font-normal text-muted-foreground"> → {item.recipient_name}</span>}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
              <Badge variant="outline">{isEmail ? "Email" : "LinkedIn"}</Badge>
              <Badge variant={STATUS_VARIANT[item.status] ?? "secondary"}>{titleCase(item.status)}</Badge>
              {item.requires_review && !done && <Badge variant="warning">Needs your review</Badge>}
              {item.model_id === "user" ? (
                <ProvenanceBadge kind="explicit" label="Written by you" />
              ) : isRuleBased(item.prompt_version, item.model_id) ? (
                <ProvenanceBadge kind="heuristic" label="Template draft" />
              ) : (
                <ProvenanceBadge kind="inferred" label="LLM draft" />
              )}
              {item.job_id && (
                <Link href={`/jobs/${item.job_id}`} className="text-primary underline-offset-2 hover:underline">
                  View job
                </Link>
              )}
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Updated <Time value={item.updated_at} />
            {item.sent_at && (
              <>
                <br />
                Sent <Time value={item.sent_at} />
              </>
            )}
          </p>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {checks.blocking.length > 0 && (
          <Alert variant="destructive">
            <AlertOctagonIcon aria-hidden="true" />
            <AlertTitle>Blocking claim-check issues</AlertTitle>
            <AlertDescription>
              <p className="mb-1 text-xs">Fix these before sending — approval is refused while they remain.</p>
              <ul className="list-disc pl-5">
                {checks.blocking.map((v, i) => (
                  <li key={i}>
                    <span className="font-medium">{titleCase(v.code)}:</span> {v.detail}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        {checks.warnings.length > 0 && (
          <Alert variant="warning">
            <AlertTriangleIcon aria-hidden="true" />
            <AlertTitle>Warnings</AlertTitle>
            <AlertDescription>
              <ul className="list-disc pl-5">
                {checks.warnings.map((v, i) => (
                  <li key={i}>
                    <span className="font-medium">{titleCase(v.code)}:</span> {v.detail}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {isEmail && (
          <p className="text-sm">
            <span className="text-muted-foreground">To: </span>
            {item.recipient_email ?? <span className="text-muted-foreground">No verified public email — use Gmail draft or copy.</span>}
          </p>
        )}
        {isEmail && (
          <Field id={`subj-${item.id}`} label="Subject">
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} disabled={done || !canPatch} />
          </Field>
        )}
        <Field
          id={`body-${item.id}`}
          label="Message"
          hint={isConnectionNote ? `${body.length} / ${LINKEDIN_NOTE_LIMIT} characters` : `${body.length} characters`}
          error={overLimit ? `LinkedIn connection notes are limited to ${LINKEDIN_NOTE_LIMIT} characters.` : null}
        >
          <Textarea rows={isConnectionNote ? 4 : 9} value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000} disabled={done || !canPatch} />
        </Field>

        {evidence.length > 0 && (
          <details className="rounded-md border p-3 text-sm">
            <summary className="cursor-pointer font-medium">Personalisation evidence ({evidence.length})</summary>
            <ul className="mt-2 space-y-1.5">
              {evidence.map((e, i) => (
                <li key={i} className="flex flex-wrap items-start gap-1.5">
                  {e.source && <Badge variant="outline">{titleCase(e.source)}</Badge>}
                  <span className="whitespace-pre-wrap">{e.fact}</span>
                </li>
              ))}
            </ul>
          </details>
        )}

        <div className="flex flex-wrap gap-2">
          {canPatch && !done && (
            <Button size="sm" onClick={() => save.mutate()} disabled={!dirty || save.isPending || !body.trim()}>
              {save.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <SaveIcon aria-hidden="true" />}
              Save edits
            </Button>
          )}
          <CopyButton text={isEmail && subject ? `Subject: ${subject}\n\n${body}` : body} label={dirty ? "Copy (unsaved edits)" : "Copy"} />
          {canGmail && (
            <Button size="sm" variant="outline" onClick={() => gmailDraft.mutate()} disabled={gmailDraft.isPending || dirty}>
              {gmailDraft.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <MailIcon aria-hidden="true" />}
              Create Gmail draft
            </Button>
          )}
          {item.gmail_draft_id && <Badge variant="info">Gmail draft created</Badge>}
          {canSend && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => requestApproval.mutate()}
              disabled={requestApproval.isPending || dirty || checks.blocking.length > 0}
              title={checks.blocking.length ? "Resolve blocking issues first" : dirty ? "Save your edits first" : undefined}
            >
              {requestApproval.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <SendIcon aria-hidden="true" />}
              Send email…
            </Button>
          )}
          {canMarkSent && (
            <Button size="sm" variant="outline" onClick={() => markSent.mutate()} disabled={markSent.isPending || dirty}>
              {markSent.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <CheckIcon aria-hidden="true" />}
              Mark as sent
            </Button>
          )}
          {canPatch && !done && (
            <Button size="sm" variant="ghost" className="text-red-700 hover:text-red-800" onClick={() => setConfirmDiscard(true)}>
              <Trash2Icon aria-hidden="true" />
              Discard
            </Button>
          )}
        </div>
        {isEmail && !googleConnected && !done && (
          <p className="text-xs text-muted-foreground">
            Connect Google in{" "}
            <Link href="/settings?tab=integrations" className="text-primary underline-offset-2 hover:underline">
              Settings → Integrations
            </Link>{" "}
            to create Gmail drafts or send.
          </p>
        )}
        {!isEmail && !done && <p className="text-xs text-muted-foreground">LinkedIn messages are sent by you: copy, send on LinkedIn, then mark as sent.</p>}
      </CardContent>

      <Dialog open={confirmDiscard} onOpenChange={setConfirmDiscard}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Discard this draft?</DialogTitle>
            <DialogDescription>The draft is kept for your records but won&apos;t be offered for sending.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDiscard(false)}>
              Keep it
            </Button>
            <Button variant="destructive" onClick={() => discard.mutate()} disabled={discard.isPending}>
              {discard.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ApprovalDialog
        open={Boolean(approval)}
        onOpenChange={(o) => {
          if (!o) {
            setApproval(null);
            approve.reset();
          }
        }}
        title="Approve sending this email"
        description="This exact email will be sent from your connected Gmail account. Nothing else will be sent."
        expiresAt={approval?.expires_at}
        confirmLabel="Send email"
        acknowledgement="I have reviewed the recipient, subject and body above and approve sending exactly this email."
        onConfirm={() => approve.mutate()}
        pending={approve.isPending}
        error={approve.error}
        onReject={approval && hasEndpoint("POST", "/approvals/{}/reject") ? () => rejectApproval.mutate(approval.approval_id) : undefined}
        rejecting={rejectApproval.isPending}
      >
        <dl className="divide-y">
          <PayloadField label="To" value={asString(preview.to)} />
          <PayloadField label="Subject" value={asString(preview.subject)} />
          <PayloadField label="Body" value={asString(preview.body)} />
          <PayloadField label="Attachments" value={attachments.length ? attachments.map((a) => asString(a) ?? JSON.stringify(a)).join(", ") : "None"} />
        </dl>
      </ApprovalDialog>
    </Card>
  );
}

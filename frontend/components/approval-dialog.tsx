"use client";

import { Loader2Icon, ShieldCheckIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Time } from "@/components/time";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";

/**
 * Explicit approval step (FR-UI-05): shows the exact payload and requires a confirm checkbox before the action runs.
 * The caller owns the idempotency key so a retried confirm replays instead of executing twice.
 */
export function ApprovalDialog({
  open,
  onOpenChange,
  title,
  description,
  expiresAt,
  confirmLabel,
  acknowledgement,
  onConfirm,
  pending,
  error,
  onReject,
  rejecting,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  expiresAt?: string | null;
  confirmLabel: string;
  acknowledgement: string;
  onConfirm: () => void;
  pending?: boolean;
  error?: unknown;
  /** Decline the approval (POST /approvals/{id}/reject). Rendered only when provided. */
  onReject?: () => void;
  rejecting?: boolean;
  /** The exact payload preview. */
  children: ReactNode;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const checkboxId = useId();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setConfirmed(false);
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheckIcon className="size-5 text-primary" aria-hidden="true" />
            {title}
          </DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>

        <div className="rounded-md border bg-muted/40 p-3" aria-label="Exactly what will be approved">
          {children}
        </div>
        {expiresAt && (
          <p className="text-xs text-muted-foreground">
            This approval expires <Time value={expiresAt} />.
          </p>
        )}

        <div className="flex items-start gap-2">
          <Checkbox id={checkboxId} checked={confirmed} onCheckedChange={(v) => setConfirmed(v === true)} disabled={pending} />
          <Label htmlFor={checkboxId} className="leading-snug font-normal">
            {acknowledgement}
          </Label>
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage(error)}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          {onReject && (
            <Button variant="ghost" className="text-red-700 hover:text-red-800 sm:mr-auto" onClick={onReject} disabled={pending || rejecting}>
              {rejecting && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Reject
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending || rejecting}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={!confirmed || pending}>
            {pending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Plain-text key/value rendering of a payload preview. */
export function PayloadField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid gap-0.5 py-1.5 sm:grid-cols-[7rem_1fr] sm:gap-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="min-w-0 whitespace-pre-wrap break-words text-sm">{value || <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

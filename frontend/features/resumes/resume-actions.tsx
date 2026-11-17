"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DownloadIcon, Loader2Icon, StarIcon, Trash2Icon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage, isApiError, newIdempotencyKey } from "@/lib/api";
import { isTerminalStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { saveBlob } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const MAX_BYTES = 5 * 1024 * 1024;

export function UploadResumeCard() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [run, setRun] = useState<{ runId: string; resumeId: string | null } | null>(null);
  const upload = useMutation({
    mutationFn: () => api.resumes.upload(file as File, label.trim() || undefined, newIdempotencyKey()),
    onSuccess: (res) => {
      setRun({ runId: res.workflow_id, resumeId: res.subject?.type === "resume" ? res.subject.id : null });
      setFile(null);
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      void qc.invalidateQueries({ queryKey: ["resumes"] });
    },
  });
  if (!hasEndpoint("POST", "/resumes/upload")) return null;

  const dupId = isApiError(upload.error) && upload.error.code === "duplicate" ? (upload.error.details.resume_id as string | undefined) : undefined;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    upload.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Upload a resume</h2>
        </CardTitle>
        <CardDescription>PDF or DOCX, up to 5 MB. Parsing extracts skills, experience and projects for you to review.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field id="resume-file" label="File" required error={localError}>
            <Input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                setLocalError(null);
                upload.reset();
                if (f && f.size > MAX_BYTES) {
                  setLocalError("That file is larger than 5 MB.");
                  setFile(null);
                  return;
                }
                setFile(f);
              }}
            />
          </Field>
          <Field id="resume-label" label="Label (optional)" hint="e.g. GenAI / LLM Engineer">
            <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} />
          </Field>
          <Button type="submit" disabled={!file || upload.isPending}>
            {upload.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <UploadIcon aria-hidden="true" />}
            Upload
          </Button>
        </form>
        {upload.error && (
          <Alert variant={dupId ? "info" : "destructive"}>
            <AlertDescription>
              {dupId ? "This file is already in your resume library. " : errorMessage(upload.error)}
              {dupId && (
                <Link href={`/resumes/${dupId}`} className="underline">
                  Open the existing resume
                </Link>
              )}
            </AlertDescription>
          </Alert>
        )}
        {run && (
          <RunProgress
            runId={run.runId}
            title="Parsing resume"
            onSettled={() => void qc.invalidateQueries({ queryKey: ["resumes"] })}
            actions={(r) => (
              <>
                {run.resumeId && isTerminalStatus(r.status) && (
                  <Button asChild size="sm">
                    <Link href={`/resumes/${run.resumeId}`}>Review parsed data</Link>
                  </Button>
                )}
                {isTerminalStatus(r.status) && (
                  <Button size="sm" variant="ghost" onClick={() => setRun(null)}>
                    Dismiss
                  </Button>
                )}
              </>
            )}
          />
        )}
      </CardContent>
    </Card>
  );
}

export function SetDefaultButton({ resumeId, isDefault, label }: { resumeId: string; isDefault: boolean; label: string }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: () => api.resumes.patch(resumeId, { is_default: true }),
    onSuccess: () => {
      toast.success(`"${label}" is now your default resume`);
      void qc.invalidateQueries({ queryKey: ["resumes"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (isDefault || !hasEndpoint("PATCH", "/resumes/{}")) return null;
  return (
    <Button size="sm" variant="outline" onClick={() => patch.mutate()} disabled={patch.isPending} aria-label={`Make ${label} the default resume`}>
      {patch.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <StarIcon aria-hidden="true" />}
      Make default
    </Button>
  );
}

export function DownloadButton({ resumeId, versionId, filename, label = "Download" }: { resumeId: string; versionId: string; filename?: string; label?: string }) {
  const download = useMutation({
    mutationFn: () => api.resumes.download(resumeId, versionId, filename),
    onSuccess: (res) => {
      if (res.kind === "url") {
        window.open(res.url, "_blank", "noopener,noreferrer");
        return;
      }
      saveBlob(res.blob, res.filename);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasEndpoint("GET", "/resumes/{}/versions/{}/download")) return null;
  return (
    <Button size="sm" variant="outline" onClick={() => download.mutate()} disabled={download.isPending}>
      {download.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <DownloadIcon aria-hidden="true" />}
      {label}
    </Button>
  );
}

export function DeleteResumeButton({ resumeId, label, onDeleted }: { resumeId: string; label: string; onDeleted?: () => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const del = useMutation({
    mutationFn: () => api.resumes.delete(resumeId),
    onSuccess: () => {
      toast.success("Resume deleted");
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ["resumes"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      onDeleted?.();
    },
  });
  if (!hasEndpoint("DELETE", "/resumes/{}")) return null;
  return (
    <>
      <Button size="sm" variant="ghost" className="text-red-700 hover:text-red-800" onClick={() => setOpen(true)} aria-label={`Delete ${label}`}>
        <Trash2Icon aria-hidden="true" />
        Delete
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) del.reset();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete “{label}”?</DialogTitle>
            <DialogDescription>This deletes the resume, every version and its stored files. Match results for it are removed.</DialogDescription>
          </DialogHeader>
          {del.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(del.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => del.mutate()} disabled={del.isPending}>
              {del.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Delete resume
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

"use client";

import { useMutation } from "@tanstack/react-query";
import { DownloadIcon, Loader2Icon, Trash2Icon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { NotAvailable } from "@/components/query-state";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { isSuccessStatus } from "@/lib/agent-run";
import { useAuth } from "@/lib/auth/auth-context";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { saveBlob } from "@/lib/utils";

function ExportCard() {
  const [runId, setRunId] = useState<string | null>(null);
  const download = useMutation({
    mutationFn: (id: string) => api.account.downloadExport(id),
    onSuccess: (res) => saveBlob(res.blob, res.filename),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const exportData = useMutation({
    mutationFn: () => api.account.export(newIdempotencyKey()),
    onSuccess: (res) => setRunId(res.workflow_id),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasEndpoint("POST", "/account/export")) return <NotAvailable feature="Data export" endpoint="POST /account/export" />;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Export your data</h2>
        </CardTitle>
        <CardDescription>A machine-readable archive of your profile, resumes, jobs, people, outreach and applications.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={() => exportData.mutate()} disabled={exportData.isPending || Boolean(runId)}>
          {exportData.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <DownloadIcon aria-hidden="true" />}
          Build export
        </Button>
        {runId && (
          <RunProgress
            runId={runId}
            title="Building export"
            actions={(run) =>
              isSuccessStatus(run.status) && hasEndpoint("GET", "/account/exports/{}") ? (
                <Button size="sm" onClick={() => download.mutate(run.id)} disabled={download.isPending}>
                  {download.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <DownloadIcon aria-hidden="true" />}
                  Download export (.zip)
                </Button>
              ) : null
            }
          />
        )}
      </CardContent>
    </Card>
  );
}

function DeleteAccountCard() {
  const { signOut } = useAuth();
  const [typed, setTyped] = useState("");
  const del = useMutation({
    mutationFn: api.account.delete,
    onSuccess: () => {
      toast.success("Your account and all data were deleted.");
      void signOut("deleted");
    },
  });
  if (!hasEndpoint("DELETE", "/account")) return <NotAvailable feature="Account deletion" endpoint="DELETE /account" />;
  function submit(e: FormEvent) {
    e.preventDefault();
    if (typed === "DELETE") del.mutate();
  }
  return (
    <Card className="border-red-300">
      <CardHeader>
        <CardTitle>
          <h2 className="text-red-800">Delete account</h2>
        </CardTitle>
        <CardDescription>Permanently deletes your account, every resume file, job, contact, draft, application and run. This can&apos;t be undone.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <Field id="delete-confirm" label='Type "DELETE" to confirm'>
            <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} />
          </Field>
          {del.error && (
            <Alert variant="destructive">
              <AlertTitle>Couldn&apos;t delete the account</AlertTitle>
              <AlertDescription>{errorMessage(del.error)}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" variant="destructive" disabled={typed !== "DELETE" || del.isPending}>
            {del.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <Trash2Icon aria-hidden="true" />}
            Delete my account and all data
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function DataTab() {
  return (
    <div className="space-y-6">
      <ExportCard />
      <DeleteAccountCard />
    </div>
  );
}

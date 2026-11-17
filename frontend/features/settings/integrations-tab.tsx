"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, MailIcon, UnplugIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { meQueryKey, useMe } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asRecord, asString, safeHref, titleCase } from "@/lib/utils";

const OAUTH_RESULT: Record<string, { variant: "success" | "warning" | "destructive"; text: string }> = {
  connected: { variant: "success", text: "Google connected. You can now create Gmail drafts." },
  denied: { variant: "warning", text: "Google access was not granted. Nothing was connected." },
  error: { variant: "destructive", text: "Connecting Google failed. Try again." },
};

export function IntegrationsTab() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const oauthResult = OAUTH_RESULT[params.get("google") ?? ""];
  const me = useMe();
  const [confirm, setConfirm] = useState(false);
  const connect = useMutation({
    mutationFn: api.integrations.googleAuthorize,
    onSuccess: (res) => {
      const href = safeHref(res.url);
      if (!href) {
        toast.error("The server returned an invalid authorisation URL.");
        return;
      }
      window.location.assign(href);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const disconnect = useMutation({
    mutationFn: api.integrations.googleDisconnect,
    onSuccess: () => {
      toast.success("Google disconnected and tokens deleted");
      setConfirm(false);
      void qc.invalidateQueries({ queryKey: meQueryKey });
    },
  });

  if (me.isPending) return <LoadingState label="Loading integrations…" />;
  if (me.isError) return <ErrorState error={me.error} onRetry={() => void me.refetch()} />;

  const google = asRecord(asRecord(me.data.integrations).google);
  const connected = google.connected === true;
  const configured = google.configured !== false;
  const status = asString(google.status);
  const account = asString(google.account_email);
  const canConnect = hasEndpoint("GET", "/integrations/google/authorize");
  const canDisconnect = hasEndpoint("DELETE", "/integrations/google");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="flex items-center gap-2">
            <MailIcon className="size-4" aria-hidden="true" />
            Google (Gmail)
            <Badge variant={connected ? "success" : status === "expired" ? "warning" : "muted"}>
              {connected ? "Connected" : status ? titleCase(status) : "Not connected"}
            </Badge>
          </h2>
        </CardTitle>
        <CardDescription>
          Uses the narrow <code>gmail.compose</code> scope to create drafts. Sending is a separate, approval-gated action. Tokens stay on the
          server, encrypted.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {oauthResult && (
          <Alert variant={oauthResult.variant}>
            <AlertDescription>{oauthResult.text}</AlertDescription>
          </Alert>
        )}
        {account && <p className="text-sm">Account: {account}</p>}
        {!configured && (
          <Alert variant="info">
            <AlertDescription>Google OAuth isn&apos;t configured on this server (GOOGLE_OAUTH_CLIENT_ID is unset).</AlertDescription>
          </Alert>
        )}
        {status === "expired" && (
          <Alert variant="warning">
            <AlertDescription>The Google connection expired (testing-mode tokens last 7 days). Reconnect to keep creating drafts.</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-wrap gap-2">
          {configured && canConnect && !connected && (
            <Button onClick={() => connect.mutate()} disabled={connect.isPending}>
              {connect.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              {status ? "Reconnect Google" : "Connect Google"}
            </Button>
          )}
          {(connected || status) && canDisconnect && (
            <Button variant="outline" onClick={() => setConfirm(true)}>
              <UnplugIcon aria-hidden="true" />
              Disconnect
            </Button>
          )}
        </div>
      </CardContent>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect Google?</DialogTitle>
            <DialogDescription>Access is revoked and stored tokens are deleted. Existing Gmail drafts stay in Gmail.</DialogDescription>
          </DialogHeader>
          {disconnect.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(disconnect.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>
              {disconnect.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

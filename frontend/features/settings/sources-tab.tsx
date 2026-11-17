"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartPulseIcon, Loader2Icon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ExternalLink } from "@/components/external-link";
import { EmptyState, NotAvailable, QueryView } from "@/components/query-state";
import { Time } from "@/components/time";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api, itemsOf } from "@/lib/endpoints";
import { asRecord, asString, safeHref, titleCase } from "@/lib/utils";
import type { SourceOut, SourceType } from "@/types/models";

export const SOURCE_TYPES: { value: SourceType; label: string; identifier: string; hint: string; isUrl: boolean }[] = [
  { value: "greenhouse", label: "Greenhouse", identifier: "Board token", hint: "From boards.greenhouse.io/<token>", isUrl: false },
  { value: "lever", label: "Lever", identifier: "Company handle", hint: "From jobs.lever.co/<handle>", isUrl: false },
  { value: "ashby", label: "Ashby", identifier: "Job board name", hint: "From jobs.ashbyhq.com/<name>", isUrl: false },
  { value: "rss", label: "RSS feed", identifier: "Feed URL", hint: "A public RSS/Atom feed of job posts", isUrl: true },
  { value: "career_page", label: "Career page", identifier: "Page URL", hint: "A careers page exposing schema.org JobPosting", isUrl: true },
];

function AddSourceForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<SourceType>("greenhouse");
  const [identifier, setIdentifier] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [termsNote, setTermsNote] = useState("");
  const meta = SOURCE_TYPES.find((s) => s.value === type)!;
  const invalidUrl = meta.isUrl && identifier.trim() !== "" && !safeHref(identifier.trim());
  const create = useMutation({
    mutationFn: () =>
      api.sources.create({
        source_type: type,
        identifier: identifier.trim(),
        name: name.trim() || null,
        company_name: company.trim() || null,
        terms_note: termsNote.trim() || null,
        enabled: true,
        config: {},
      }),
    onSuccess: () => {
      toast.success("Source added");
      void qc.invalidateQueries({ queryKey: ["sources"] });
      onDone();
    },
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!identifier.trim() || invalidUrl) return;
    create.mutate();
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Add a source</h2>
        </CardTitle>
        <CardDescription>Only documented public job-board APIs, feeds and career pages. LinkedIn is never crawled.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <Field id="src-type" label="Type" required>
            <NativeSelect value={type} onChange={(e) => setType(e.target.value as SourceType)}>
              {SOURCE_TYPES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="src-id" label={meta.identifier} required hint={meta.hint} error={invalidUrl ? "Enter a full http(s) URL." : null}>
            <Input type={meta.isUrl ? "url" : "text"} value={identifier} onChange={(e) => setIdentifier(e.target.value)} maxLength={500} />
          </Field>
          <Field id="src-name" label="Display name">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </Field>
          <Field id="src-company" label="Company name">
            <Input value={company} onChange={(e) => setCompany(e.target.value)} maxLength={200} />
          </Field>
          <Field id="src-terms" label="Terms note" hint="Where you checked this source permits automated access" className="sm:col-span-2">
            <Input value={termsNote} onChange={(e) => setTermsNote(e.target.value)} maxLength={500} />
          </Field>
          {create.error && (
            <Alert variant="destructive" className="sm:col-span-2">
              <AlertDescription>{errorMessage(create.error)}</AlertDescription>
            </Alert>
          )}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" disabled={create.isPending || !identifier.trim() || invalidUrl}>
              {create.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Add source
            </Button>
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SourceRow({ source }: { source: SourceOut }) {
  const qc = useQueryClient();
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["sources"] });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api.sources.patch(source.id, { enabled }),
    onSuccess: (_d, enabled) => {
      toast.success(enabled ? "Source enabled" : "Source disabled");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const check = useMutation({
    mutationFn: () => api.sources.healthCheck(source.id, newIdempotencyKey()),
    onSuccess: (res) => {
      setHealth(asRecord(res));
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () => api.sources.delete(source.id),
    onSuccess: () => {
      toast.success("Source deleted");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const ok = source.last_status === "ok" || source.last_status === "completed" || source.last_status === "healthy";
  const healthOk = health ? health.ok === true || health.status === "ok" || health.healthy === true : null;
  return (
    <TableRow>
      <TableCell className="min-w-48">
        <p className="font-medium">{source.name}</p>
        <p className="break-all text-xs text-muted-foreground">
          {titleCase(source.source_type)} ·{" "}
          {safeHref(source.identifier) ? <ExternalLink href={source.identifier}>{source.identifier}</ExternalLink> : source.identifier}
        </p>
      </TableCell>
      <TableCell>
        {hasEndpoint("PATCH", "/sources/{}") ? (
          <Switch
            checked={source.enabled}
            disabled={toggle.isPending}
            onCheckedChange={(v) => toggle.mutate(v)}
            aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.name}`}
          />
        ) : (
          <Badge variant={source.enabled ? "success" : "muted"}>{source.enabled ? "Enabled" : "Disabled"}</Badge>
        )}
      </TableCell>
      <TableCell className="min-w-44 text-sm">
        {source.last_status ? <Badge variant={ok ? "success" : "destructive"}>{titleCase(source.last_status)}</Badge> : <span className="text-muted-foreground">Never crawled</span>}
        <div className="text-xs text-muted-foreground">
          <Time value={source.last_crawled_at} />
        </div>
        {source.consecutive_failures > 0 && <div className="text-xs text-red-700">{source.consecutive_failures} consecutive failures</div>}
        {source.last_error && <p className="mt-1 max-w-xs whitespace-pre-wrap text-xs text-red-700">{source.last_error}</p>}
      </TableCell>
      <TableCell className="min-w-40 text-sm">
        {health && (
          <p role="status" className={healthOk ? "text-emerald-700" : "text-red-700"}>
            {healthOk ? "Healthy" : "Unhealthy"}
            {asString(health.message) || asString(health.detail) ? `: ${asString(health.message) ?? asString(health.detail)}` : ""}
          </p>
        )}
      </TableCell>
      <TableCell>
        <div className="flex gap-1">
          {hasEndpoint("POST", "/sources/{}/health-check") && (
            <Button size="sm" variant="outline" onClick={() => check.mutate()} disabled={check.isPending} aria-label={`Health check ${source.name}`}>
              {check.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <HeartPulseIcon aria-hidden="true" />}
              Check
            </Button>
          )}
          {hasEndpoint("DELETE", "/sources/{}") && (
            <Button size="icon" variant="ghost" onClick={() => del.mutate()} disabled={del.isPending} aria-label={`Delete ${source.name}`}>
              <Trash2Icon aria-hidden="true" />
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

export function SourcesTab() {
  const enabled = hasEndpoint("GET", "/sources");
  const query = useQuery({ queryKey: ["sources"], queryFn: api.sources.list, enabled });
  const [adding, setAdding] = useState(false);
  if (!enabled) return <NotAvailable feature="Source configuration" endpoint="GET /sources" />;
  return (
    <div className="space-y-4">
      {adding ? (
        <AddSourceForm onDone={() => setAdding(false)} />
      ) : (
        hasEndpoint("POST", "/sources") && (
          <Button onClick={() => setAdding(true)}>
            <PlusIcon aria-hidden="true" />
            Add source
          </Button>
        )
      )}
      <QueryView query={query} loadingLabel="Loading sources…" errorTitle="Couldn't load sources">
        {(data) => {
          const sources = itemsOf(data);
          if (!sources.length) return <EmptyState title="No sources yet" description="Add a Greenhouse, Lever or Ashby board, an RSS feed or a career page." />;
          return (
            <Card>
              <Table aria-label="Sources">
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Enabled</TableHead>
                    <TableHead>Last crawl</TableHead>
                    <TableHead>Health check</TableHead>
                    <TableHead>
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sources.map((s) => (
                    <SourceRow key={s.id} source={s} />
                  ))}
                </TableBody>
              </Table>
            </Card>
          );
        }}
      </QueryView>
    </div>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, Loader2Icon, Trash2Icon, XIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { EmptyState, QueryView } from "@/components/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asString, titleCase } from "@/lib/utils";
import type { FactOut } from "@/types/models";

const FACT_TYPES = ["skill", "experience", "project", "education", "certification", "achievement"];

export function factSummary(f: FactOut): { primary: string; secondary: string | null } {
  const d = f.data ?? {};
  const primary = asString(d.name) ?? asString(d.title) ?? asString(d.degree) ?? asString(d.text) ?? JSON.stringify(d);
  const secondary = asString(d.company) ?? asString(d.institution) ?? asString(d.issuer) ?? asString(d.year) ?? null;
  return { primary, secondary };
}

function FactRow({ fact }: { fact: FactOut }) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["profile", "facts"] });
  const patch = useMutation({
    mutationFn: (status: "confirmed" | "rejected") => api.profile.patchFact(fact.id, { status }),
    onSuccess: (_d, status) => {
      toast.success(status === "confirmed" ? "Confirmed" : "Rejected");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: () => api.profile.deleteFact(fact.id),
    onSuccess: () => {
      toast.success("Removed");
      void invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const { primary, secondary } = factSummary(fact);
  const isSkill = fact.fact_type === "skill";
  const hasSkill = fact.data?.has_skill !== false;
  // A suggestion hasn't been answered yet, so only label it once confirmed or explicitly set.
  const showHas = isSkill && (fact.status === "confirmed" || typeof fact.data?.has_skill === "boolean");
  const canPatch = hasEndpoint("PATCH", "/profile/facts/{}");
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {primary}
          {secondary && <span className="font-normal text-muted-foreground"> · {secondary}</span>}
        </p>
        <div className="mt-0.5 flex flex-wrap gap-1.5">
          {fact.source === "user_entered" ? (
            <ProvenanceBadge kind="explicit" label="You entered" />
          ) : fact.source === "resume_derived" ? (
            <ProvenanceBadge kind="inferred" label="From resume" />
          ) : (
            <ProvenanceBadge kind="inferred" label={titleCase(fact.source)} />
          )}
          {showHas && <Badge variant={hasSkill ? "success" : "destructive"}>{hasSkill ? "I have it" : "I don't have it"}</Badge>}
          {fact.status === "rejected" && <Badge variant="muted">Rejected</Badge>}
        </div>
      </div>
      <div className="flex gap-1">
        {fact.status === "suggested" && canPatch && (
          <>
            <Button size="sm" onClick={() => patch.mutate("confirmed")} disabled={patch.isPending} aria-label={`Confirm ${primary}`}>
              <CheckIcon aria-hidden="true" />
              Confirm
            </Button>
            <Button size="sm" variant="outline" onClick={() => patch.mutate("rejected")} disabled={patch.isPending} aria-label={`Reject ${primary}`}>
              <XIcon aria-hidden="true" />
              Reject
            </Button>
          </>
        )}
        {hasEndpoint("DELETE", "/profile/facts/{}") && (
          <Button size="icon" variant="ghost" onClick={() => del.mutate()} disabled={del.isPending} aria-label={`Delete ${primary}`}>
            <Trash2Icon aria-hidden="true" />
          </Button>
        )}
      </div>
    </li>
  );
}

function AddSkill() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: (has: boolean) => api.profile.addFact({ fact_type: "skill", data: { name: name.trim(), has_skill: has } }),
    onSuccess: (_d, has) => {
      toast.success(has ? `Added ${name.trim()} as a skill you have` : `Recorded that you don't have ${name.trim()}`);
      setName("");
      void qc.invalidateQueries({ queryKey: ["profile", "facts"] });
    },
  });
  if (!hasEndpoint("POST", "/profile/facts")) return null;
  const submit = (has: boolean) => (e?: FormEvent) => {
    e?.preventDefault();
    if (name.trim()) add.mutate(has);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Add a skill</h2>
        </CardTitle>
        <CardDescription>
          Confirmed skills count as &quot;profile only&quot; evidence. Marking one you don&apos;t have makes it &quot;confirmed missing&quot; —
          the only way a skill is reported as missing.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit(true)} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field id="add-skill" label="Skill" className="flex-1">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kubernetes" maxLength={80} />
          </Field>
          <Button type="submit" disabled={!name.trim() || add.isPending}>
            {add.isPending && add.variables === true && <Loader2Icon className="animate-spin" aria-hidden="true" />}I have it
          </Button>
          <Button type="button" variant="outline" disabled={!name.trim() || add.isPending} onClick={() => submit(false)()}>
            {add.isPending && add.variables === false && <Loader2Icon className="animate-spin" aria-hidden="true" />}I don&apos;t have it
          </Button>
        </form>
        {add.error && (
          <Alert variant="destructive" className="mt-3">
            <AlertDescription>{errorMessage(add.error)}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

export function FactsTab() {
  const query = useQuery({ queryKey: ["profile", "facts"], queryFn: () => api.profile.facts() });
  const [showRejected, setShowRejected] = useState(false);
  return (
    <div className="space-y-6">
      <AddSkill />
      <QueryView query={query} loadingLabel="Loading profile facts…" errorTitle="Couldn't load profile facts">
        {(facts) => {
          if (!facts.length)
            return <EmptyState title="No profile facts yet" description="Upload a resume to get suggestions, or add skills above." />;
          const suggested = facts.filter((f) => f.status === "suggested");
          const rejected = facts.filter((f) => f.status === "rejected");
          const confirmed = facts.filter((f) => f.status === "confirmed");
          return (
            <div className="space-y-6">
              {suggested.length > 0 && (
                <Card className="border-amber-300">
                  <CardHeader>
                    <CardTitle>
                      <h2>Suggestions to review ({suggested.length})</h2>
                    </CardTitle>
                    <CardDescription>Extracted from your resumes. Only confirmed facts are used in outreach and applications.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ul className="divide-y">
                      {suggested.map((f) => (
                        <FactRow key={f.id} fact={f} />
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
              {FACT_TYPES.map((type) => {
                const items = confirmed.filter((f) => f.fact_type === type);
                if (!items.length) return null;
                return (
                  <Card key={type}>
                    <CardHeader>
                      <CardTitle>
                        <h2>
                          {titleCase(type)}s ({items.length})
                        </h2>
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="divide-y">
                        {items.map((f) => (
                          <FactRow key={f.id} fact={f} />
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                );
              })}
              {rejected.length > 0 && (
                <div>
                  <Button variant="ghost" size="sm" onClick={() => setShowRejected((s) => !s)} aria-expanded={showRejected}>
                    {showRejected ? "Hide" : "Show"} rejected ({rejected.length})
                  </Button>
                  {showRejected && (
                    <ul className="mt-2 divide-y rounded-lg border px-4">
                      {rejected.map((f) => (
                        <FactRow key={f.id} fact={f} />
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

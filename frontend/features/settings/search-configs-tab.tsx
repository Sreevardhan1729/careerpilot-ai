"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { EmptyState, QueryView } from "@/components/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asNumber, asString } from "@/lib/utils";
import type { SearchConfigIn, SearchConfigOut } from "@/types/models";
import { CheckboxSet, joinList, numOrNull, parseList } from "./common";

const WORK_MODES = ["remote", "hybrid", "onsite"] as const;

interface Band {
  label: string;
  min: string;
  max: string;
}

function toForm(c: SearchConfigOut | null) {
  return {
    name: c?.name ?? "New search",
    role_filters: joinList(c?.role_filters),
    locations: joinList(c?.locations),
    skills: joinList(c?.skills),
    work_modes: [...(c?.work_modes ?? ["remote", "hybrid", "onsite"])],
    bands: (c?.experience_bands ?? []).map((b) => ({
      label: asString(b.label) ?? "",
      min: asNumber(b.min)?.toString() ?? "",
      max: asNumber(b.max)?.toString() ?? "",
    })) as Band[],
    salary_minimum: c?.salary_minimum?.toString() ?? "",
    salary_currency: c?.salary_currency ?? "INR",
    salary_period: c?.salary_period ?? "annual",
    is_active: c?.is_active ?? true,
  };
}

function toBody(f: ReturnType<typeof toForm>): SearchConfigIn {
  return {
    name: f.name.trim() || "Default",
    role_filters: parseList(f.role_filters),
    locations: parseList(f.locations),
    skills: parseList(f.skills),
    work_modes: f.work_modes,
    experience_bands: f.bands
      .filter((b) => b.label.trim() || b.min || b.max)
      .map((b) => ({ label: b.label.trim() || `${b.min}–${b.max} years`, min: numOrNull(b.min), max: numOrNull(b.max) })),
    salary_minimum: numOrNull(f.salary_minimum),
    salary_currency: f.salary_currency.trim().toUpperCase() || null,
    salary_period: f.salary_period || null,
    is_active: f.is_active,
  };
}

function ConfigForm({ config, onDone }: { config: SearchConfigOut | null; onDone?: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState(() => toForm(config));
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const prefix = config?.id ?? "new";
  const save = useMutation({
    mutationFn: () => (config ? api.searchConfigs.patch(config.id, toBody(f)) : api.searchConfigs.create(toBody(f))),
    onSuccess: () => {
      toast.success("Search preferences saved");
      void qc.invalidateQueries({ queryKey: ["search-configs"] });
      onDone?.();
    },
  });
  const del = useMutation({
    mutationFn: () => api.searchConfigs.delete(config!.id),
    onSuccess: () => {
      toast.success("Search deleted");
      void qc.invalidateQueries({ queryKey: ["search-configs"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canSave = config ? hasEndpoint("PATCH", "/search-configs/{}") : hasEndpoint("POST", "/search-configs");

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="flex items-center gap-2">
            {config ? config.name : "New search configuration"}
            {config && <Badge variant={config.is_active ? "success" : "muted"}>{config.is_active ? "Active" : "Inactive"}</Badge>}
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <Field id={`${prefix}-name`} label="Name">
            <Input value={f.name} onChange={(e) => set("name", e.target.value)} maxLength={80} />
          </Field>
          <div className="flex items-center gap-2 self-end pb-2">
            <Switch id={`${prefix}-active`} checked={f.is_active} onCheckedChange={(v) => set("is_active", v)} />
            <Label htmlFor={`${prefix}-active`}>Active (used by daily discovery)</Label>
          </div>
          <Field id={`${prefix}-roles`} label="Role filters" hint="Comma separated title keywords" className="sm:col-span-2">
            <Textarea rows={2} value={f.role_filters} onChange={(e) => set("role_filters", e.target.value)} />
          </Field>
          <Field id={`${prefix}-locs`} label="Locations" hint="Comma separated">
            <Input value={f.locations} onChange={(e) => set("locations", e.target.value)} />
          </Field>
          <Field id={`${prefix}-skills`} label="Skills" hint="Comma separated">
            <Input value={f.skills} onChange={(e) => set("skills", e.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <CheckboxSet legend="Work modes" name={`${prefix}-wm`} options={WORK_MODES} value={f.work_modes} onChange={(v) => set("work_modes", v)} />
          </div>
          <fieldset className="space-y-2 sm:col-span-2">
            <legend className="text-sm font-medium">Experience bands (years)</legend>
            {f.bands.map((b, i) => (
              <div key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_6rem_6rem_auto]">
                <Field id={`${prefix}-band-${i}-label`} label="Label">
                  <Input value={b.label} onChange={(e) => set("bands", f.bands.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                </Field>
                <Field id={`${prefix}-band-${i}-min`} label="Min">
                  <Input type="number" min={0} step={0.5} value={b.min} onChange={(e) => set("bands", f.bands.map((x, j) => (j === i ? { ...x, min: e.target.value } : x)))} />
                </Field>
                <Field id={`${prefix}-band-${i}-max`} label="Max">
                  <Input type="number" min={0} step={0.5} value={b.max} onChange={(e) => set("bands", f.bands.map((x, j) => (j === i ? { ...x, max: e.target.value } : x)))} />
                </Field>
                <Button type="button" size="icon" variant="ghost" aria-label={`Remove band ${b.label || i + 1}`} onClick={() => set("bands", f.bands.filter((_, j) => j !== i))}>
                  <Trash2Icon aria-hidden="true" />
                </Button>
              </div>
            ))}
            <Button type="button" size="sm" variant="outline" onClick={() => set("bands", [...f.bands, { label: "", min: "", max: "" }])}>
              <PlusIcon aria-hidden="true" />
              Add band
            </Button>
          </fieldset>
          <fieldset className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
            <legend className="mb-1 text-sm font-medium">Minimum salary</legend>
            <Field id={`${prefix}-sal`} label="Amount">
              <Input type="number" min={0} value={f.salary_minimum} onChange={(e) => set("salary_minimum", e.target.value)} />
            </Field>
            <Field id={`${prefix}-cur`} label="Currency">
              <Input value={f.salary_currency} onChange={(e) => set("salary_currency", e.target.value)} maxLength={3} />
            </Field>
            <Field id={`${prefix}-period`} label="Period">
              <NativeSelect value={f.salary_period} onChange={(e) => set("salary_period", e.target.value)}>
                <option value="annual">Annual</option>
                <option value="monthly">Monthly</option>
                <option value="hourly">Hourly</option>
              </NativeSelect>
            </Field>
          </fieldset>
          {save.error && (
            <Alert variant="destructive" className="sm:col-span-2">
              <AlertDescription>{errorMessage(save.error)}</AlertDescription>
            </Alert>
          )}
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            {canSave && (
              <Button type="submit" disabled={save.isPending}>
                {save.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                {config ? "Save changes" : "Create search"}
              </Button>
            )}
            {!config && onDone && (
              <Button type="button" variant="outline" onClick={onDone}>
                Cancel
              </Button>
            )}
            {config && hasEndpoint("DELETE", "/search-configs/{}") && (
              <Button type="button" variant="ghost" className="text-red-700" onClick={() => del.mutate()} disabled={del.isPending}>
                <Trash2Icon aria-hidden="true" />
                Delete
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function SearchConfigsTab() {
  const query = useQuery({ queryKey: ["search-configs"], queryFn: api.searchConfigs.list });
  const [adding, setAdding] = useState(false);
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Daily discovery pre-filters listings by these roles and locations before analysis, to protect the LLM budget.
      </p>
      <QueryView query={query} loadingLabel="Loading search preferences…" errorTitle="Couldn't load search preferences">
        {(configs) => (
          <div className="space-y-4">
            {configs.length === 0 && !adding && <EmptyState title="No search configurations" description="Create one to guide discovery." />}
            {configs.map((c) => (
              <ConfigForm key={`${c.id}-${c.name}-${c.is_active}`} config={c} />
            ))}
          </div>
        )}
      </QueryView>
      {adding ? (
        <ConfigForm config={null} onDone={() => setAdding(false)} />
      ) : (
        hasEndpoint("POST", "/search-configs") && (
          <Button variant="outline" onClick={() => setAdding(true)}>
            <PlusIcon aria-hidden="true" />
            New search configuration
          </Button>
        )
      )}
    </div>
  );
}

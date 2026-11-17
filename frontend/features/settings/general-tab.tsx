"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { QueryView } from "@/components/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { RuleBasedBanner } from "@/features/dashboard/dashboard-view";
import { meQueryKey } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asRecord, asString, titleCase } from "@/lib/utils";
import type { SettingsOut } from "@/types/models";

function timezones(current: string): string[] {
  let zones: string[] = [];
  try {
    zones = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? [];
  } catch {
    zones = [];
  }
  if (!zones.length) zones = ["Asia/Kolkata", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Singapore"];
  return zones.includes(current) ? zones : [current, ...zones];
}

function Info({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value ?? "—"}</dd>
    </div>
  );
}

function GeneralForm({ settings }: { settings: SettingsOut }) {
  const qc = useQueryClient();
  const [timezone, setTimezone] = useState(settings.timezone);
  const [time, setTime] = useState(settings.scheduler_local_time);
  const [autoOutreach, setAutoOutreach] = useState(settings.auto_generate_outreach);
  const zones = useMemo(() => timezones(settings.timezone), [settings.timezone]);
  const save = useMutation({
    mutationFn: () => api.settings.put({ timezone, scheduler_local_time: time, auto_generate_outreach: autoOutreach }),
    onSuccess: () => {
      toast.success("Settings saved");
      void qc.invalidateQueries({ queryKey: ["settings"] });
      void qc.invalidateQueries({ queryKey: meQueryKey });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const dirty = timezone !== settings.timezone || time !== settings.scheduler_local_time || autoOutreach !== settings.auto_generate_outreach;
  const canSave = hasEndpoint("PUT", "/settings");
  const llm = asRecord(settings.llm);
  const emb = asRecord(settings.embeddings);
  const provider = asString(llm.provider);

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Preferences</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
            <Field id="tz" label="Timezone" hint="All times in the app are shown in this timezone.">
              <NativeSelect value={timezone} onChange={(e) => setTimezone(e.target.value)} disabled={!canSave}>
                {zones.map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field id="sched-time" label="Daily run time" hint="Stored preference; the actual trigger is the GitHub Actions cron.">
              <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={!canSave} />
            </Field>
            <div className="flex items-start gap-2 sm:col-span-2">
              <Switch id="auto-outreach" checked={autoOutreach} onCheckedChange={setAutoOutreach} disabled={!canSave} />
              <Label htmlFor="auto-outreach" className="leading-snug font-normal">
                Auto-generate outreach drafts for top jobs after the daily run
                <span className="block text-xs text-muted-foreground">Drafts only — nothing is ever sent automatically.</span>
              </Label>
            </div>
            {save.error && (
              <Alert variant="destructive" className="sm:col-span-2">
                <AlertDescription>{errorMessage(save.error)}</AlertDescription>
              </Alert>
            )}
            {canSave && (
              <div className="sm:col-span-2">
                <Button type="submit" disabled={!dirty || save.isPending || !/^\d{2}:\d{2}$/.test(time)}>
                  {save.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                  Save
                </Button>
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>AI configuration</h2>
          </CardTitle>
          <CardDescription>Set on the server through environment variables. Keys are never sent to the browser.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {provider === "none" && <RuleBasedBanner />}
          <dl className="grid gap-4 sm:grid-cols-3">
            <Info label="LLM provider" value={provider ? titleCase(provider) : null} />
            <Info label="LLM model" value={asString(llm.model)} />
            <Info label="Mode" value={asString(llm.mode) === "heuristic" ? "Rule-based (deterministic)" : asString(llm.mode) ? "LLM" : null} />
            <Info label="Daily LLM call budget" value={asString(llm.daily_call_budget)} />
            <Info label="Embedding provider" value={asString(emb.provider) ? titleCase(asString(emb.provider)) : null} />
            <Info label="Embedding model" value={[asString(emb.model), asString(emb.dimensions) && `${asString(emb.dimensions)} dims`].filter(Boolean).join(" · ") || null} />
            <Info label="People search provider" value={settings.search_provider === "none" ? "None configured" : titleCase(settings.search_provider)} />
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

export function GeneralTab() {
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings.get });
  return (
    <QueryView query={query} loadingLabel="Loading settings…" errorTitle="Couldn't load settings">
      {(s) => <GeneralForm key={`${s.timezone}-${s.scheduler_local_time}-${s.auto_generate_outreach}`} settings={s} />}
    </QueryView>
  );
}

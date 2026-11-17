"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { QueryView } from "@/components/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { meQueryKey } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import type { ProfileOut, ProfileUpdate } from "@/types/models";
import { CheckboxSet, joinList, numOrNull, parseList } from "./common";

const WORK_MODES = ["remote", "hybrid", "onsite"] as const;
const EMPLOYMENT_TYPES = ["full_time", "part_time", "contract", "internship", "temporary"] as const;

type FormState = ReturnType<typeof toForm>;

function toForm(p: ProfileOut) {
  return {
    full_name: p.full_name ?? "",
    preferred_email: p.preferred_email ?? "",
    phone: p.phone ?? "",
    current_location: p.current_location ?? "",
    preferred_locations: joinList(p.preferred_locations),
    preferred_work_modes: [...(p.preferred_work_modes ?? [])] as string[],
    graduation_year: p.graduation_year?.toString() ?? "",
    total_experience_months: p.total_experience_months?.toString() ?? "",
    preferred_roles: joinList(p.preferred_roles),
    preferred_industries: joinList(p.preferred_industries),
    portfolio_url: p.portfolio_url ?? "",
    github_url: p.github_url ?? "",
    linkedin_url: p.linkedin_url ?? "",
    salary_minimum: p.salary_preference?.minimum?.toString() ?? "",
    salary_currency: p.salary_preference?.currency ?? "INR",
    salary_period: (p.salary_preference?.period ?? "annual") as string,
    employment_type_preferences: [...(p.employment_type_preferences ?? [])] as string[],
    notice_period_days: p.notice_period_days?.toString() ?? "",
    work_authorization: p.work_authorization ?? "",
  };
}

const str = (s: string) => (s.trim() ? s.trim() : null);

/** Only changed fields are sent, so untouched resume-derived values keep their provenance. */
export function profileChanges(original: FormState, f: FormState): ProfileUpdate {
  const body: Record<string, unknown> = {};
  const scalar = ["full_name", "preferred_email", "phone", "current_location", "portfolio_url", "github_url", "linkedin_url", "work_authorization"] as const;
  for (const k of scalar) if (f[k] !== original[k]) body[k] = str(f[k]);
  for (const k of ["preferred_locations", "preferred_roles", "preferred_industries"] as const) {
    if (f[k] !== original[k]) body[k] = parseList(f[k]);
  }
  for (const k of ["graduation_year", "total_experience_months", "notice_period_days"] as const) {
    if (f[k] !== original[k]) body[k] = numOrNull(f[k]);
  }
  for (const k of ["preferred_work_modes", "employment_type_preferences"] as const) {
    if ([...f[k]].sort().join() !== [...original[k]].sort().join()) body[k] = f[k];
  }
  if (f.salary_minimum !== original.salary_minimum || f.salary_currency !== original.salary_currency || f.salary_period !== original.salary_period) {
    body.salary_preference = {
      minimum: numOrNull(f.salary_minimum),
      currency: str(f.salary_currency)?.toUpperCase() ?? null,
      period: f.salary_period as "annual" | "monthly" | "hourly",
    };
  }
  return body as ProfileUpdate;
}

function SourceBadge({ source }: { source: string | undefined }) {
  if (source === "user_entered") return <ProvenanceBadge kind="explicit" label="You entered" describe={false} />;
  if (source === "resume_derived") return <ProvenanceBadge kind="inferred" label="From resume" describe={false} />;
  if (source) return <ProvenanceBadge kind="unverified" label={source.replace(/_/g, " ")} describe={false} />;
  return null;
}

function ProfileForm({ profile }: { profile: ProfileOut }) {
  const qc = useQueryClient();
  const [original] = useState(() => toForm(profile));
  const [f, setF] = useState(original);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((prev) => ({ ...prev, [k]: v }));
  const changes = profileChanges(original, f);
  const dirty = Object.keys(changes).length > 0;
  const save = useMutation({
    mutationFn: () => api.profile.put(changes),
    onSuccess: () => {
      toast.success("Profile saved. Job rankings are being refreshed.");
      void qc.invalidateQueries({ queryKey: ["profile"] });
      void qc.invalidateQueries({ queryKey: meQueryKey });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
  const canSave = hasEndpoint("PUT", "/profile");
  const src = profile.field_sources ?? {};
  const L = (label: string, key: string): ReactNode => (
    <span className="inline-flex items-center gap-1.5">
      {label} <SourceBadge source={src[key]} />
    </span>
  );

  function submit(e: FormEvent) {
    e.preventDefault();
    if (dirty) save.mutate();
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Candidate profile</h2>
          </CardTitle>
          <CardDescription>Used for ranking (experience, location, salary) and for answers in prepared applications.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field id="pf-name" label={L("Full name", "full_name")}>
            <Input value={f.full_name} onChange={(e) => set("full_name", e.target.value)} maxLength={120} autoComplete="name" />
          </Field>
          <Field id="pf-email" label={L("Preferred email", "preferred_email")}>
            <Input type="email" value={f.preferred_email} onChange={(e) => set("preferred_email", e.target.value)} maxLength={200} autoComplete="email" />
          </Field>
          <Field id="pf-phone" label={L("Phone", "phone")}>
            <Input type="tel" value={f.phone} onChange={(e) => set("phone", e.target.value)} maxLength={40} autoComplete="tel" />
          </Field>
          <Field id="pf-loc" label={L("Current location", "current_location")}>
            <Input value={f.current_location} onChange={(e) => set("current_location", e.target.value)} maxLength={120} />
          </Field>
          <Field id="pf-grad" label={L("Graduation year", "graduation_year")}>
            <Input type="number" min={1950} max={2100} value={f.graduation_year} onChange={(e) => set("graduation_year", e.target.value)} />
          </Field>
          <Field id="pf-exp" label={L("Total experience (months)", "total_experience_months")} hint="Used for experience eligibility in the Job Score.">
            <Input type="number" min={0} max={600} value={f.total_experience_months} onChange={(e) => set("total_experience_months", e.target.value)} />
          </Field>
          <Field id="pf-notice" label={L("Notice period (days)", "notice_period_days")}>
            <Input type="number" min={0} max={365} value={f.notice_period_days} onChange={(e) => set("notice_period_days", e.target.value)} />
          </Field>
          <Field id="pf-auth" label={L("Work authorisation", "work_authorization")}>
            <Input value={f.work_authorization} onChange={(e) => set("work_authorization", e.target.value)} maxLength={300} />
          </Field>
          <Field id="pf-portfolio" label={L("Portfolio URL", "portfolio_url")}>
            <Input type="url" value={f.portfolio_url} onChange={(e) => set("portfolio_url", e.target.value)} maxLength={300} />
          </Field>
          <Field id="pf-github" label={L("GitHub URL", "github_url")}>
            <Input type="url" value={f.github_url} onChange={(e) => set("github_url", e.target.value)} maxLength={300} />
          </Field>
          <Field id="pf-linkedin" label={L("LinkedIn URL", "linkedin_url")}>
            <Input type="url" value={f.linkedin_url} onChange={(e) => set("linkedin_url", e.target.value)} maxLength={300} />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Preferences</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field id="pf-roles" label={L("Preferred roles", "preferred_roles")} hint="Comma separated" className="sm:col-span-2">
            <Textarea rows={2} value={f.preferred_roles} onChange={(e) => set("preferred_roles", e.target.value)} />
          </Field>
          <Field id="pf-locs" label={L("Preferred locations", "preferred_locations")} hint="Comma separated, e.g. Bengaluru, Remote India">
            <Input value={f.preferred_locations} onChange={(e) => set("preferred_locations", e.target.value)} />
          </Field>
          <Field id="pf-ind" label={L("Preferred industries", "preferred_industries")} hint="Comma separated">
            <Input value={f.preferred_industries} onChange={(e) => set("preferred_industries", e.target.value)} />
          </Field>
          <CheckboxSet legend="Preferred work modes" name="pf-wm" options={WORK_MODES} value={f.preferred_work_modes} onChange={(v) => set("preferred_work_modes", v)} />
          <CheckboxSet
            legend="Employment types"
            name="pf-et"
            options={EMPLOYMENT_TYPES}
            value={f.employment_type_preferences}
            onChange={(v) => set("employment_type_preferences", v)}
          />
          <fieldset className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
            <legend className="mb-1 inline-flex items-center gap-1.5 text-sm font-medium">
              Minimum salary <SourceBadge source={src.salary_preference} />
            </legend>
            <Field id="pf-sal-min" label="Amount">
              <Input type="number" min={0} value={f.salary_minimum} onChange={(e) => set("salary_minimum", e.target.value)} />
            </Field>
            <Field id="pf-sal-cur" label="Currency" hint="3-letter code">
              <Input value={f.salary_currency} onChange={(e) => set("salary_currency", e.target.value)} maxLength={3} />
            </Field>
            <Field id="pf-sal-period" label="Period">
              <NativeSelect value={f.salary_period} onChange={(e) => set("salary_period", e.target.value)}>
                <option value="annual">Annual</option>
                <option value="monthly">Monthly</option>
                <option value="hourly">Hourly</option>
              </NativeSelect>
            </Field>
          </fieldset>
        </CardContent>
      </Card>

      {save.error && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(save.error)}</AlertDescription>
        </Alert>
      )}
      {canSave && (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!dirty || save.isPending}>
            {save.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
            Save profile
          </Button>
          {dirty && <span className="text-sm text-muted-foreground">Unsaved changes</span>}
        </div>
      )}
    </form>
  );
}

export function ProfileTab() {
  const query = useQuery({ queryKey: ["profile"], queryFn: api.profile.get });
  return (
    <QueryView query={query} loadingLabel="Loading profile…" errorTitle="Couldn't load your profile">
      {(p) => <ProfileForm key={p.updated_at} profile={p} />}
    </QueryView>
  );
}

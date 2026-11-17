"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, PlusIcon, SaveIcon, Trash2Icon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { cleanParsed, emptyEducation, emptyExperience, emptyProject, emptySkill, normalizeParsed, type EditableParsed } from "./parsed";

const SKILL_SECTIONS = ["skills", "project", "experience", "summary"];

const SEP = { lines: { join: "\n", split: /\n/ }, commas: { join: ", ", split: /,/ } } as const;

/**
 * A list edited as free text (one per line / comma separated). Keeps the raw text locally so typing a trailing newline
 * or comma isn't swallowed; reports the parsed list upward.
 */
function ListField({
  id,
  label,
  value,
  onChange,
  mode,
  disabled,
  rows,
}: {
  id: string;
  label: string;
  value: string[] | undefined;
  onChange: (v: string[]) => void;
  mode: keyof typeof SEP;
  disabled?: boolean;
  rows?: number;
}) {
  const [raw, setRaw] = useState(() => (value ?? []).join(SEP[mode].join));
  const handle = (text: string) => {
    setRaw(text);
    onChange(
      text
        .split(SEP[mode].split)
        .map((x) => x.trim())
        .filter(Boolean),
    );
  };
  return (
    <Field id={id} label={label} hint={mode === "lines" ? "One per line" : "Comma separated"}>
      {mode === "lines" ? (
        <Textarea rows={rows ?? 3} value={raw} disabled={disabled} onChange={(e) => handle(e.target.value)} />
      ) : (
        <Input value={raw} disabled={disabled} onChange={(e) => handle(e.target.value)} />
      )}
    </Field>
  );
}

function Group({ title, description, onAdd, addLabel, children }: { title: string; description?: string; onAdd?: () => void; addLabel?: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-3 rounded-lg border p-4">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      {description && <p className="-mt-2 text-xs text-muted-foreground">{description}</p>}
      {children}
      {onAdd && (
        <Button type="button" size="sm" variant="outline" onClick={onAdd}>
          <PlusIcon aria-hidden="true" />
          {addLabel ?? "Add"}
        </Button>
      )}
    </fieldset>
  );
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button type="button" size="icon" variant="ghost" onClick={onClick} aria-label={label} className="text-red-700">
      <Trash2Icon aria-hidden="true" />
    </Button>
  );
}

/**
 * Review and correct parsed resume data. Saving PUTs the full EditableParsed object; the backend treats corrections as
 * authoritative and rebuilds chunks/embeddings (the original file is untouched).
 */
export function ParsedDataEditor({ resumeId, versionId, parsed }: { resumeId: string; versionId: string; parsed: unknown }) {
  const qc = useQueryClient();
  const [data, setData] = useState<EditableParsed>(() => normalizeParsed(parsed));
  const [dirty, setDirty] = useState(false);
  // Bumped when rows are removed or edits discarded, so ListField's local text re-syncs with the data.
  const [generation, setGeneration] = useState(0);
  const canSave = hasEndpoint("PUT", "/resumes/{}/versions/{}/parsed-data");

  const save = useMutation({
    mutationFn: () => api.resumes.putParsed(resumeId, versionId, cleanParsed(data)),
    onSuccess: () => {
      toast.success("Corrections saved. Matching will use them.");
      setDirty(false);
      void qc.invalidateQueries({ queryKey: ["resumes"] });
    },
  });

  function update(fn: (d: EditableParsed) => EditableParsed) {
    setData((d) => fn(d));
    setDirty(true);
  }

  function removeRow(fn: (d: EditableParsed) => EditableParsed) {
    update(fn);
    setGeneration((g) => g + 1);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  const disabled = !canSave || save.isPending;
  const contact = data.contact ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>Parsed data</h2>
        </CardTitle>
        <CardDescription>Check what was extracted and fix anything wrong. Your corrections replace the parsed values.</CardDescription>
      </CardHeader>
      <CardContent>
        <form key={generation} onSubmit={submit} className="space-y-5">
          <Group title="Contact">
            <div className="grid gap-3 sm:grid-cols-2">
              {(
                [
                  ["name", "Name"],
                  ["email", "Email"],
                  ["phone", "Phone"],
                  ["location", "Location"],
                  ["linkedin_url", "LinkedIn URL"],
                  ["github_url", "GitHub URL"],
                  ["portfolio_url", "Portfolio URL"],
                ] as const
              ).map(([key, label]) => (
                <Field key={key} id={`contact-${key}`} label={label}>
                  <Input
                    value={contact[key] ?? ""}
                    disabled={disabled}
                    onChange={(e) => update((d) => ({ ...d, contact: { ...d.contact, [key]: e.target.value || null } }))}
                  />
                </Field>
              ))}
            </div>
          </Group>

          <Field id="parsed-summary" label="Summary">
            <Textarea rows={3} value={data.summary ?? ""} disabled={disabled} maxLength={2000} onChange={(e) => update((d) => ({ ...d, summary: e.target.value }))} />
          </Field>

          <Group
            title={`Skills (${data.skills.length})`}
            description="Where each skill appears. Skills only in the skills section count as weakly highlighted."
            onAdd={disabled ? undefined : () => update((d) => ({ ...d, skills: [...d.skills, emptySkill()] }))}
            addLabel="Add skill"
          >
            {data.skills.length === 0 && <p className="text-sm text-muted-foreground">No skills extracted.</p>}
            <ul className="space-y-2">
              {data.skills.map((s, i) => (
                <li key={i} className="grid items-end gap-2 sm:grid-cols-[1fr_9rem_2fr_auto]">
                  <Field id={`skill-${i}-name`} label="Skill">
                    <Input value={s.name} disabled={disabled} maxLength={80} onChange={(e) => update((d) => ({ ...d, skills: d.skills.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) }))} />
                  </Field>
                  <Field id={`skill-${i}-section`} label="Found in">
                    <NativeSelect value={s.section} disabled={disabled} onChange={(e) => update((d) => ({ ...d, skills: d.skills.map((x, j) => (j === i ? { ...x, section: e.target.value } : x)) }))}>
                      {SKILL_SECTIONS.map((sec) => (
                        <option key={sec} value={sec}>
                          {sec}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                  <Field id={`skill-${i}-evidence`} label="Evidence">
                    <Input value={s.evidence ?? ""} disabled={disabled} maxLength={300} onChange={(e) => update((d) => ({ ...d, skills: d.skills.map((x, j) => (j === i ? { ...x, evidence: e.target.value } : x)) }))} />
                  </Field>
                  {!disabled && <RemoveButton label={`Remove skill ${s.name || i + 1}`} onClick={() => update((d) => ({ ...d, skills: d.skills.filter((_, j) => j !== i) }))} />}
                </li>
              ))}
            </ul>
          </Group>

          <Group
            title={`Experience (${data.experience.length})`}
            onAdd={disabled ? undefined : () => update((d) => ({ ...d, experience: [...d.experience, emptyExperience()] }))}
            addLabel="Add experience"
          >
            {data.experience.map((x, i) => {
              const set = (patch: Partial<typeof x>) => update((d) => ({ ...d, experience: d.experience.map((e, j) => (j === i ? { ...e, ...patch } : e)) }));
              return (
                <div key={i} className="space-y-3 rounded-md border bg-muted/20 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{x.title || x.company || `Experience ${i + 1}`}</p>
                    {!disabled && <RemoveButton label={`Remove experience ${i + 1}`} onClick={() => removeRow((d) => ({ ...d, experience: d.experience.filter((_, j) => j !== i) }))} />}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Field id={`exp-${i}-title`} label="Title">
                      <Input value={x.title ?? ""} disabled={disabled} onChange={(e) => set({ title: e.target.value })} />
                    </Field>
                    <Field id={`exp-${i}-company`} label="Company">
                      <Input value={x.company ?? ""} disabled={disabled} onChange={(e) => set({ company: e.target.value })} />
                    </Field>
                    <Field id={`exp-${i}-start`} label="Start">
                      <Input value={x.start ?? ""} disabled={disabled} onChange={(e) => set({ start: e.target.value })} placeholder="2024-06" />
                    </Field>
                    <Field id={`exp-${i}-end`} label="End">
                      <Input value={x.end ?? ""} disabled={disabled} onChange={(e) => set({ end: e.target.value })} placeholder="present" />
                    </Field>
                    <Field id={`exp-${i}-months`} label="Months">
                      <Input type="number" min={0} max={600} value={x.months ?? ""} disabled={disabled} onChange={(e) => set({ months: e.target.value === "" ? null : Number(e.target.value) })} />
                    </Field>
                    <div className="flex items-center gap-2 self-end pb-2">
                      <Checkbox id={`exp-${i}-intern`} checked={x.is_internship ?? false} disabled={disabled} onCheckedChange={(c) => set({ is_internship: c === true })} />
                      <Label htmlFor={`exp-${i}-intern`} className="font-normal">
                        Internship
                      </Label>
                    </div>
                  </div>
                  <ListField id={`exp-${i}-bullets`} label="Bullets" mode="lines" value={x.bullets} disabled={disabled} onChange={(v) => set({ bullets: v })} />
                  <ListField id={`exp-${i}-tech`} label="Technologies" mode="commas" value={x.technologies} disabled={disabled} onChange={(v) => set({ technologies: v })} />
                </div>
              );
            })}
          </Group>

          <Group
            title={`Projects (${data.projects.length})`}
            onAdd={disabled ? undefined : () => update((d) => ({ ...d, projects: [...d.projects, emptyProject()] }))}
            addLabel="Add project"
          >
            {data.projects.map((x, i) => {
              const set = (patch: Partial<typeof x>) => update((d) => ({ ...d, projects: d.projects.map((e, j) => (j === i ? { ...e, ...patch } : e)) }));
              return (
                <div key={i} className="space-y-3 rounded-md border bg-muted/20 p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{x.title || `Project ${i + 1}`}</p>
                    {!disabled && <RemoveButton label={`Remove project ${i + 1}`} onClick={() => removeRow((d) => ({ ...d, projects: d.projects.filter((_, j) => j !== i) }))} />}
                  </div>
                  <Field id={`proj-${i}-title`} label="Title">
                    <Input value={x.title ?? ""} disabled={disabled} onChange={(e) => set({ title: e.target.value })} />
                  </Field>
                  <Field id={`proj-${i}-desc`} label="Description">
                    <Textarea rows={2} value={x.description ?? ""} maxLength={1500} disabled={disabled} onChange={(e) => set({ description: e.target.value })} />
                  </Field>
                  <ListField id={`proj-${i}-bullets`} label="Bullets" mode="lines" value={x.bullets} disabled={disabled} onChange={(v) => set({ bullets: v })} />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <ListField id={`proj-${i}-tech`} label="Technologies" mode="commas" value={x.technologies} disabled={disabled} onChange={(v) => set({ technologies: v })} />
                    <ListField id={`proj-${i}-links`} label="Links" mode="commas" value={x.links} disabled={disabled} onChange={(v) => set({ links: v })} />
                  </div>
                </div>
              );
            })}
          </Group>

          <Group
            title={`Education (${data.education.length})`}
            onAdd={disabled ? undefined : () => update((d) => ({ ...d, education: [...d.education, emptyEducation()] }))}
            addLabel="Add education"
          >
            {data.education.map((x, i) => {
              const set = (patch: Partial<typeof x>) => update((d) => ({ ...d, education: d.education.map((e, j) => (j === i ? { ...e, ...patch } : e)) }));
              return (
                <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_7rem_1fr_auto]">
                  <Field id={`edu-${i}-degree`} label="Degree">
                    <Input value={x.degree ?? ""} disabled={disabled} onChange={(e) => set({ degree: e.target.value })} />
                  </Field>
                  <Field id={`edu-${i}-inst`} label="Institution">
                    <Input value={x.institution ?? ""} disabled={disabled} onChange={(e) => set({ institution: e.target.value })} />
                  </Field>
                  <Field id={`edu-${i}-year`} label="Year">
                    <Input value={x.year ?? ""} disabled={disabled} onChange={(e) => set({ year: e.target.value })} />
                  </Field>
                  <Field id={`edu-${i}-details`} label="Details">
                    <Input value={x.details ?? ""} disabled={disabled} onChange={(e) => set({ details: e.target.value })} />
                  </Field>
                  {!disabled && <RemoveButton label={`Remove education ${i + 1}`} onClick={() => update((d) => ({ ...d, education: d.education.filter((_, j) => j !== i) }))} />}
                </div>
              );
            })}
          </Group>

          <ListField id="parsed-certs" label="Certifications" mode="lines" rows={2} value={data.certifications} disabled={disabled} onChange={(v) => update((d) => ({ ...d, certifications: v }))} />

          {save.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(save.error)}</AlertDescription>
            </Alert>
          )}
          {canSave && (
            <div className="sticky bottom-0 flex items-center gap-3 border-t bg-card py-3">
              <Button type="submit" disabled={!dirty || save.isPending}>
                {save.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <SaveIcon aria-hidden="true" />}
                Save corrections
              </Button>
              {dirty && <span className="text-sm text-muted-foreground">Unsaved changes</span>}
              {dirty && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setData(normalizeParsed(parsed));
                    setDirty(false);
                    setGeneration((g) => g + 1);
                  }}
                >
                  Discard changes
                </Button>
              )}
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

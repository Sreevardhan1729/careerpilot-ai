"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagonIcon, ArrowDownIcon, ArrowRightIcon, ArrowUpIcon, Loader2Icon, PlusIcon, Trash2Icon, WandSparklesIcon } from "lucide-react";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { ApprovalDialog, PayloadField } from "@/components/approval-dialog";
import { ErrorState, LoadingState } from "@/components/query-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useRejectApproval } from "@/features/approvals/pending-approvals";
import { errorMessage, newIdempotencyKey } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { asArray, asRecord, asString, titleCase } from "@/lib/utils";
import type { ApprovalOut } from "@/types/models";
import { normalizeParsed } from "./parsed";
import { buildTailoredPayload, editableTexts, initialSkillOrder, moveItem, resumeSkills, tailoredProblems, type VersionChange } from "./tailored";

/** Inline rendering of a 422 from POST /resumes/{id}/versions (claim-check violations, unknown skills or text). */
export function TailoredProblemsView({ error }: { error: unknown }) {
  if (!error) return null;
  const p = tailoredProblems(error);
  if (!p) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive">
      <AlertOctagonIcon aria-hidden="true" />
      <AlertTitle>The server rejected this version</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{p.message}</p>
        {p.violations.length > 0 && (
          <ul className="list-disc pl-5" aria-label="Claim-check violations">
            {p.violations.map((v, i) => (
              <li key={i}>
                <span className="font-medium">{titleCase(v.code)}:</span> {v.detail}
              </li>
            ))}
          </ul>
        )}
        {p.unknownSkills.length > 0 && <p>Not in this resume: {p.unknownSkills.join(", ")}. Remove them from the skill order.</p>}
        {p.unknownBefore && (
          <p>
            This text isn&apos;t in the resume version (it must match exactly): <q className="italic">{p.unknownBefore}</q>
          </p>
        )}
        {p.fieldErrors.length > 0 && (
          <ul className="list-disc pl-5">
            {p.fieldErrors.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        )}
      </AlertDescription>
    </Alert>
  );
}

/** Approve + activate a pending tailored version (POST /resumes/{id}/versions/{vid}/activate). */
export function VersionApprovalDialog({
  resumeId,
  versionId,
  approval,
  open,
  onOpenChange,
  onActivated,
}: {
  resumeId: string;
  versionId: string;
  approval: ApprovalOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onActivated?: () => void;
}) {
  const qc = useQueryClient();
  // One key per approval: a retried confirm replays instead of activating twice.
  const [key] = useState(newIdempotencyKey);
  const activate = useMutation({
    mutationFn: () =>
      api.resumes.activateVersion(resumeId, versionId, { approval_id: approval.approval_id, payload_hash: approval.payload_hash, confirm: true }, key),
    onSuccess: () => {
      toast.success("Tailored version activated. Matching now uses it.");
      void qc.invalidateQueries({ queryKey: ["resumes"] });
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      onOpenChange(false);
      onActivated?.();
    },
  });
  const reject = useRejectApproval(() => onOpenChange(false));
  const p = asRecord(approval.payload_preview);
  const changes = asArray(p.changes).map((c) => asRecord(c));
  const skillOrder = asArray(p.skill_order).map((s) => asString(s)).filter((s): s is string => !!s);
  return (
    <ApprovalDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) activate.reset();
        onOpenChange(o);
      }}
      title="Activate tailored resume version"
      description="Activating makes this the current version used for matching and applications. The original stays available."
      expiresAt={approval.expires_at}
      confirmLabel="Activate version"
      acknowledgement="I have checked every change and the skill order above, they are true for me, and I want to activate this version."
      onConfirm={() => activate.mutate()}
      pending={activate.isPending}
      error={activate.error}
      onReject={hasEndpoint("POST", "/approvals/{}/reject") ? () => reject.mutate(approval.approval_id) : undefined}
      rejecting={reject.isPending}
    >
      <dl className="divide-y">
        <PayloadField label="Resume" value={[asString(p.resume), asString(p.version_number) && `v${asString(p.version_number)}`].filter(Boolean).join(" · ")} />
        <PayloadField label="Summary" value={asString(p.change_summary)} />
        <PayloadField
          label="Changes"
          value={
            changes.length ? (
              <ol className="list-decimal space-y-2 pl-5">
                {changes.map((c, i) => (
                  <li key={i}>
                    <span className="text-xs uppercase text-muted-foreground">{asString(c.section)}</span>
                    <p className="text-muted-foreground line-through">
                      <span className="sr-only">Before: </span>
                      {asString(c.before)}
                    </p>
                    <p>
                      <span className="sr-only">After: </span>
                      {asString(c.after)}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              "No text changes"
            )
          }
        />
        <PayloadField label="Skill order" value={skillOrder.length ? skillOrder.join(", ") : "Unchanged"} />
      </dl>
    </ApprovalDialog>
  );
}

function Section({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <fieldset className="space-y-2 rounded-lg border p-3">
      <legend className="px-1 text-sm font-semibold">{title}</legend>
      {description && <p className="-mt-1 text-xs text-muted-foreground">{description}</p>}
      {children}
    </fieldset>
  );
}

interface Edit {
  id: number;
  key: string;
  after: string;
}

function TailoredForm({
  resumeId,
  jobId,
  jobTitle,
  suggestedSkillOrder,
  rewrites,
  onCreated,
  onCancel,
}: {
  resumeId: string;
  jobId: string | null;
  jobTitle: string | null;
  suggestedSkillOrder: string[] | null;
  rewrites: VersionChange[];
  onCreated: (versionId: string, approval: ApprovalOut) => void;
  onCancel: () => void;
}) {
  const formId = useId();
  const resume = useQuery({ queryKey: ["resumes", resumeId], queryFn: () => api.resumes.get(resumeId) });
  const parsed = useMemo(() => normalizeParsed(resume.data?.parsed_data), [resume.data?.parsed_data]);
  const skills = useMemo(() => resumeSkills(parsed), [parsed]);
  const texts = useMemo(() => editableTexts(parsed), [parsed]);
  const textByKey = useMemo(() => new Map(texts.map((t) => [t.key, t])), [texts]);
  const knownText = useMemo(() => new Set(texts.map((t) => t.text.trim())), [texts]);

  const [order, setOrder] = useState<string[] | null>(null);
  const skillOrder = order ?? initialSkillOrder(skills, suggestedSkillOrder);
  const [picked, setPicked] = useState<Set<number>>(() => new Set());
  const [edits, setEdits] = useState<Edit[]>([]);
  const [nextId, setNextId] = useState(1);
  const [summary, setSummary] = useState("");
  const [clientErrors, setClientErrors] = useState<string[]>([]);

  const create = useMutation({
    mutationFn: (payload: NonNullable<ReturnType<typeof buildTailoredPayload>["payload"]>) => api.resumes.createVersion(resumeId, payload),
    onSuccess: (res) => onCreated(res.version.id, res.approval),
  });

  if (resume.isPending) return <LoadingState label="Loading resume…" />;
  if (resume.isError) return <ErrorState error={resume.error} onRetry={() => void resume.refetch()} />;
  if (!resume.data.parsed_data || !resume.data.current_version) {
    return <Alert variant="info"><AlertDescription>This resume has no parsed data yet, so it can&apos;t be tailored.</AlertDescription></Alert>;
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const { payload, errors } = buildTailoredPayload({
      jobId,
      jobTitle,
      baseVersionId: resume.data?.current_version?.id ?? null,
      originalSkills: skills,
      skillOrder,
      selectedRewrites: rewrites.filter((_, i) => picked.has(i)),
      edits: edits
        .map((ed) => ({ text: textByKey.get(ed.key), after: ed.after }))
        .filter((x): x is { text: NonNullable<typeof x.text>; after: string } => Boolean(x.text))
        .map((x) => ({ before: x.text.text, after: x.after, section: x.text.section })),
      changeSummary: summary,
    });
    setClientErrors(errors);
    if (payload) create.mutate(payload);
  }

  return (
    <form id={formId} onSubmit={submit} className="space-y-4">
      <Section title="Skill order" description="Reorder skills to lead with what this job asks for. Only skills already on the resume can be used.">
        {skills.length === 0 ? (
          <p className="text-sm text-muted-foreground">This resume lists no skills.</p>
        ) : (
          <>
            <ol className="max-h-56 space-y-1 overflow-y-auto pr-1" aria-label="Skill order">
              {skillOrder.map((s, i) => (
                <li key={s} className="flex items-center gap-2 rounded border bg-background px-2 py-1 text-sm">
                  <span className="w-6 text-right tabular-nums text-muted-foreground">{i + 1}.</span>
                  <span className="flex-1">{s}</span>
                  <Button type="button" size="icon" variant="ghost" className="size-7" disabled={i === 0} aria-label={`Move ${s} up`} onClick={() => setOrder(moveItem(skillOrder, i, -1))}>
                    <ArrowUpIcon aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    disabled={i === skillOrder.length - 1}
                    aria-label={`Move ${s} down`}
                    onClick={() => setOrder(moveItem(skillOrder, i, 1))}
                  >
                    <ArrowDownIcon aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap gap-2">
              {suggestedSkillOrder && suggestedSkillOrder.length > 0 && (
                <Button type="button" size="sm" variant="outline" onClick={() => setOrder(initialSkillOrder(skills, suggestedSkillOrder))}>
                  Use suggested order
                </Button>
              )}
              <Button type="button" size="sm" variant="ghost" onClick={() => setOrder(skills)}>
                Reset to resume order
              </Button>
            </div>
          </>
        )}
      </Section>

      {rewrites.length > 0 && (
        <Section title="Suggested rewrites" description="Tick only the ones that are true for you. Each is claim-checked again by the server.">
          <ul className="space-y-2">
            {rewrites.map((r, i) => {
              const id = `${formId}-rw-${i}`;
              const applicable = knownText.has(r.before.trim());
              return (
                <li key={i} className="flex items-start gap-2 rounded border bg-background p-2 text-sm">
                  <Checkbox
                    id={id}
                    disabled={!applicable}
                    checked={picked.has(i)}
                    onCheckedChange={(c) =>
                      setPicked((prev) => {
                        const next = new Set(prev);
                        if (c === true) next.add(i);
                        else next.delete(i);
                        return next;
                      })
                    }
                  />
                  <Label htmlFor={id} className="grid flex-1 gap-1 font-normal leading-snug md:grid-cols-[1fr_auto_1fr]">
                    <span className="text-muted-foreground">
                      <span className="sr-only">Before: </span>
                      {r.before}
                    </span>
                    <ArrowRightIcon className="hidden size-4 md:block" aria-hidden="true" />
                    <span>
                      <span className="sr-only">After: </span>
                      {r.after}
                    </span>
                    {!applicable && <span className="text-xs text-amber-800 md:col-span-3">The original text isn&apos;t in the current version, so this can&apos;t be applied.</span>}
                  </Label>
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      <Section title="Edit a bullet" description="Pick existing text and write its replacement. Keep it true — the server rejects new metrics or skills you can't evidence.">
        {texts.length === 0 && <p className="text-sm text-muted-foreground">No editable text found in this resume.</p>}
        {edits.map((ed, idx) => {
          const t = textByKey.get(ed.key);
          return (
            <div key={ed.id} className="space-y-2 rounded border bg-background p-2">
              <div className="flex items-end gap-2">
                <Field id={`${formId}-edit-${ed.id}-pick`} label={`Text to replace (${idx + 1})`} className="flex-1">
                  <NativeSelect
                    value={ed.key}
                    onChange={(e) => {
                      const key = e.target.value;
                      setEdits((all) => all.map((x) => (x.id === ed.id ? { ...x, key, after: textByKey.get(key)?.text ?? "" } : x)));
                    }}
                  >
                    {texts.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.label}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Button type="button" size="icon" variant="ghost" className="text-red-700" aria-label={`Remove edit ${idx + 1}`} onClick={() => setEdits((all) => all.filter((x) => x.id !== ed.id))}>
                  <Trash2Icon aria-hidden="true" />
                </Button>
              </div>
              {t && <p className="whitespace-pre-wrap rounded bg-muted p-2 text-xs text-muted-foreground">Current: {t.text}</p>}
              <Field id={`${formId}-edit-${ed.id}-after`} label="Replacement">
                <Textarea rows={2} maxLength={1200} value={ed.after} onChange={(e) => setEdits((all) => all.map((x) => (x.id === ed.id ? { ...x, after: e.target.value } : x)))} />
              </Field>
            </div>
          );
        })}
        {texts.length > 0 && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              const first = texts[0];
              setEdits((all) => [...all, { id: nextId, key: first.key, after: first.text }]);
              setNextId((n) => n + 1);
            }}
          >
            <PlusIcon aria-hidden="true" />
            Edit a bullet
          </Button>
        )}
      </Section>

      <Field id={`${formId}-summary`} label="Change summary (optional)" hint="Shown in version history. Generated if left blank.">
        <Input value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={500} />
      </Field>

      {clientErrors.length > 0 && (
        <Alert variant="destructive">
          <AlertDescription>
            <ul className="list-disc pl-5">
              {clientErrors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      <TailoredProblemsView error={create.error} />

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? <Loader2Icon className="animate-spin" aria-hidden="true" /> : <WandSparklesIcon aria-hidden="true" />}
          Create version for review
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * "Create tailored version": form → POST /resumes/{id}/versions (pending approval) → ApprovalDialog → activate.
 */
export function TailoredVersionButton({
  resumeId,
  jobId = null,
  jobTitle = null,
  suggestedSkillOrder = null,
  rewrites = [],
  label = "Create tailored version",
  variant = "outline",
}: {
  resumeId: string;
  jobId?: string | null;
  jobTitle?: string | null;
  suggestedSkillOrder?: string[] | null;
  rewrites?: VersionChange[];
  label?: string;
  variant?: "outline" | "default";
}) {
  const [open, setOpen] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [created, setCreated] = useState<{ versionId: string; approval: ApprovalOut } | null>(null);
  if (!hasEndpoint("POST", "/resumes/{}/versions")) return null;
  return (
    <>
      <Button
        size="sm"
        variant={variant}
        onClick={() => {
          setFormKey((k) => k + 1);
          setOpen(true);
        }}
      >
        <WandSparklesIcon aria-hidden="true" />
        {label}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{jobTitle ? `Tailor this resume for ${jobTitle}` : "Create a tailored version"}</DialogTitle>
            <DialogDescription>
              Creates a new DOCX version for your review. Nothing changes until you approve it, and the original stays available.
            </DialogDescription>
          </DialogHeader>
          <TailoredForm
            key={formKey}
            resumeId={resumeId}
            jobId={jobId}
            jobTitle={jobTitle}
            suggestedSkillOrder={suggestedSkillOrder}
            rewrites={rewrites}
            onCancel={() => setOpen(false)}
            onCreated={(versionId, approval) => {
              setOpen(false);
              setCreated({ versionId, approval });
            }}
          />
        </DialogContent>
      </Dialog>
      {created && hasEndpoint("POST", "/resumes/{}/versions/{}/activate") && (
        <VersionApprovalDialog
          resumeId={resumeId}
          versionId={created.versionId}
          approval={created.approval}
          open={Boolean(created)}
          onOpenChange={(o) => {
            if (!o) setCreated(null);
          }}
        />
      )}
    </>
  );
}

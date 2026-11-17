"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheckIcon, CircleHelpIcon, Loader2Icon, UserPlusIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { safeHref } from "@/lib/utils";
import type { ContactStatus } from "@/types/models";

export const CONTACT_STATUSES: { value: ContactStatus; label: string }[] = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "responded", label: "Responded" },
  { value: "do_not_contact", label: "Do not contact" },
];

/** FR-PPL-05: only `verified_current` may be displayed as "current". */
export function AssociationBadge({ status }: { status: string }) {
  if (status === "verified_current") {
    return (
      <Badge variant="success" title="Evidence confirms they currently work at this company.">
        <BadgeCheckIcon aria-hidden="true" />
        Current (verified)
      </Badge>
    );
  }
  if (status === "likely_current") {
    return (
      <Badge variant="warning" title="Evidence suggests an association, but it isn't confirmed as current.">
        <CircleHelpIcon aria-hidden="true" />
        Likely associated — not confirmed
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="border-dashed border-slate-400 text-slate-700" title="The company association could not be verified.">
      <CircleHelpIcon aria-hidden="true" />
      Association unverified
    </Badge>
  );
}

export function ContactStatusSelect({ personId, value, name, onChanged }: { personId: string; value: string; name: string; onChanged?: () => void }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: (contact_status: ContactStatus) => api.people.patch(personId, { contact_status }),
    onSuccess: () => {
      toast.success("Contact status updated");
      void qc.invalidateQueries({ queryKey: ["people"] });
      onChanged?.();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!hasEndpoint("PATCH", "/people/{}")) return <Badge variant="outline">{CONTACT_STATUSES.find((c) => c.value === value)?.label ?? value}</Badge>;
  return (
    <div className="flex items-center gap-1.5">
      <NativeSelect
        aria-label={`Contact status for ${name}`}
        value={value}
        className="h-8 w-40"
        disabled={patch.isPending}
        onChange={(e) => patch.mutate(e.target.value as ContactStatus)}
      >
        {CONTACT_STATUSES.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </NativeSelect>
      {patch.isPending && <Loader2Icon className="size-4 animate-spin" aria-label="Saving" />}
    </div>
  );
}

export function AddPersonDialog({ jobId, companyName }: { jobId?: string; companyName?: string | null }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", linkedin_url: "", designation: "", company: companyName ?? "", notes: "" });
  const create = useMutation({
    mutationFn: () =>
      api.people.create({
        name: form.name.trim(),
        linkedin_url: form.linkedin_url.trim() || null,
        designation: form.designation.trim() || null,
        company: form.company.trim() || null,
        notes: form.notes.trim() || null,
        job_id: jobId ?? null,
      }),
    onSuccess: () => {
      toast.success("Person added");
      void qc.invalidateQueries({ queryKey: ["people"] });
      setOpen(false);
      setForm({ name: "", linkedin_url: "", designation: "", company: companyName ?? "", notes: "" });
    },
  });
  if (!hasEndpoint("POST", "/people")) return null;
  const urlInvalid = form.linkedin_url.trim() !== "" && !safeHref(form.linkedin_url.trim());

  function submit(e: FormEvent) {
    e.preventDefault();
    if (form.name.trim().length < 2 || urlInvalid) return;
    create.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) create.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <UserPlusIcon aria-hidden="true" />
          Add person
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a person</DialogTitle>
          <DialogDescription>Someone you know of at the company. Profile URLs you add are stored, never fetched from LinkedIn.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <Field id="p-name" label="Name" required>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} minLength={2} maxLength={120} />
          </Field>
          <Field id="p-url" label="Profile URL" hint="LinkedIn or another public profile" error={urlInvalid ? "Enter a full http(s) URL." : null}>
            <Input type="url" value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} maxLength={300} />
          </Field>
          <Field id="p-designation" label="Designation">
            <Input value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} maxLength={200} />
          </Field>
          <Field id="p-company" label="Company">
            <Input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} maxLength={200} />
          </Field>
          <Field id="p-notes" label="Notes">
            <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} maxLength={2000} />
          </Field>
          {create.error && (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage(create.error)}</AlertDescription>
            </Alert>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || form.name.trim().length < 2 || urlInvalid}>
              {create.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
              Add person
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, PenLineIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import type { MessageType, OutreachDraftIn, OutreachOut } from "@/types/models";
import { MESSAGE_TYPE_LABELS, OutreachCard } from "./outreach-card";

const EMAIL_TYPES: MessageType[] = ["recruiter_email", "recruiter_follow_up", "thank_you"];

/** Builds the POST /outreach/drafts body; subject only for email message types. */
export function buildDraftPayload(f: { jobId: string; personId: string; messageType: MessageType; subject: string; body: string }): OutreachDraftIn {
  const isEmail = EMAIL_TYPES.includes(f.messageType);
  return {
    job_id: f.jobId || null,
    person_id: f.personId || null,
    message_type: f.messageType,
    subject: isEmail ? f.subject.trim() || null : null,
    body: f.body.trim(),
  };
}

export function WriteDraftDialog({ defaultJobId }: { defaultJobId?: string | null }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [jobId, setJobId] = useState(defaultJobId ?? "");
  const [personId, setPersonId] = useState("");
  const [messageType, setMessageType] = useState<MessageType>("linkedin_connection");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [created, setCreated] = useState<OutreachOut | null>(null);
  const jobs = useQuery({ queryKey: ["jobs", "picker"], queryFn: () => api.jobs.list({ limit: 100, sort: "-job_score" }), enabled: open });
  const peopleEnabled = open && Boolean(jobId) && hasEndpoint("GET", "/jobs/{}/people");
  const people = useQuery({ queryKey: ["people", "job", jobId], queryFn: () => api.people.forJob(jobId), enabled: peopleEnabled });
  const create = useMutation({
    mutationFn: () => api.outreach.createDraft(buildDraftPayload({ jobId, personId, messageType, subject, body })),
    onSuccess: (res) => {
      setCreated(res);
      toast.success("Draft saved");
      void qc.invalidateQueries({ queryKey: ["outreach"] });
    },
  });
  if (!hasEndpoint("POST", "/outreach/drafts")) return null;
  const isEmail = EMAIL_TYPES.includes(messageType);

  function reset() {
    setCreated(null);
    setBody("");
    setSubject("");
    create.reset();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (body.trim()) create.mutate();
  }

  return (
    <>
      <Button variant="outline" className="w-full" onClick={() => setOpen(true)}>
        <PenLineIcon aria-hidden="true" />
        Write your own draft
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) reset();
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{created ? "Draft saved" : "Write your own draft"}</DialogTitle>
            <DialogDescription>Your draft gets the same claim check as generated drafts. Nothing is sent from here.</DialogDescription>
          </DialogHeader>
          {created ? (
            <div className="space-y-3">
              <OutreachCard item={created} />
              <DialogFooter>
                <Button variant="outline" onClick={reset}>
                  Write another
                </Button>
                <Button onClick={() => setOpen(false)}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
              <Field id="wd-job" label="Job (optional)" hint={jobs.isError ? errorMessage(jobs.error) : undefined}>
                <NativeSelect
                  value={jobId}
                  onChange={(e) => {
                    setJobId(e.target.value);
                    setPersonId("");
                  }}
                  disabled={jobs.isPending}
                >
                  <option value="">{jobs.isPending ? "Loading jobs…" : "No job"}</option>
                  {jobs.data?.items.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title || "Untitled"} — {j.company?.name ?? "Unknown company"}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field id="wd-person" label="Recipient (optional)" hint={people.isError ? errorMessage(people.error) : !jobId ? "Choose a job to pick someone from its people list." : undefined}>
                <NativeSelect value={personId} onChange={(e) => setPersonId(e.target.value)} disabled={!peopleEnabled || people.isPending}>
                  <option value="">{peopleEnabled && people.isPending ? "Loading people…" : "No recipient"}</option>
                  {people.data?.items
                    .filter((p) => p.contact_status !== "do_not_contact")
                    .map((p) => (
                      <option key={p.person_id} value={p.person_id}>
                        {p.name}
                        {p.designation ? ` — ${p.designation}` : ""}
                      </option>
                    ))}
                </NativeSelect>
              </Field>
              <Field id="wd-type" label="Message type" required>
                <NativeSelect value={messageType} onChange={(e) => setMessageType(e.target.value as MessageType)}>
                  {(Object.keys(MESSAGE_TYPE_LABELS) as MessageType[]).map((t) => (
                    <option key={t} value={t}>
                      {MESSAGE_TYPE_LABELS[t]}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              {isEmail && (
                <Field id="wd-subject" label="Subject">
                  <Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} />
                </Field>
              )}
              <Field
                id="wd-body"
                label="Message"
                required
                className="sm:col-span-2"
                hint={messageType === "linkedin_connection" ? `${body.length} / 200 characters for a LinkedIn connection note` : `${body.length} characters`}
              >
                <Textarea rows={7} value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000} />
              </Field>
              {create.error && (
                <Alert variant="destructive" className="sm:col-span-2">
                  <AlertDescription>{errorMessage(create.error)}</AlertDescription>
                </Alert>
              )}
              <DialogFooter className="sm:col-span-2">
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={!body.trim() || create.isPending}>
                  {create.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                  Save draft
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

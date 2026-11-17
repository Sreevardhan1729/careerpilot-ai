"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ClipboardPasteIcon, FileUpIcon, LinkIcon, Loader2Icon, PencilLineIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { RunProgress } from "@/components/run-progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage, isApiError, newIdempotencyKey } from "@/lib/api";
import { isSuccessStatus } from "@/lib/agent-run";
import { hasEndpoint } from "@/lib/capabilities";
import { api, type AnalyzeResult } from "@/lib/endpoints";
import { splitList } from "@/lib/utils";
import type { ManualFields } from "@/types/models";

const MIN_TEXT = 40;
const MAX_TEXT = 60_000;
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const FILE_ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

type Tab = "text" | "url" | "file" | "manual";

interface Started {
  runId: string;
  jobId: string | null;
}

function ErrorBox({ error, onPasteInstead }: { error: unknown; onPasteInstead?: () => void }) {
  if (!error) return null;
  const notPermitted = isApiError(error) && error.code === "source_not_permitted";
  return (
    <Alert variant="destructive">
      <AlertDescription>
        <p>{errorMessage(error)}</p>
        {notPermitted && onPasteInstead && (
          <Button size="sm" variant="outline" className="mt-2 bg-white" onClick={onPasteInstead}>
            <ClipboardPasteIcon aria-hidden="true" />
            Paste the text instead
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

const emptyManual = {
  company: "",
  job_title: "",
  location: "",
  work_mode: "",
  employment_type: "",
  experience: "",
  salary: "",
  application_url: "",
  requirements: "",
  nice_to_have: "",
  responsibilities: "",
  description: "",
};

export function AnalyzeJobDialog({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [open, setOpen] = useState(defaultOpen);
  const [tab, setTab] = useState<Tab>("text");
  const [started, setStarted] = useState<Started | null>(null);

  const [text, setText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileSourceUrl, setFileSourceUrl] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [manual, setManual] = useState(emptyManual);

  function handleResult(result: AnalyzeResult) {
    if (result.kind === "deduplicated") {
      toast.info("You've already analysed this job — opening the existing analysis.");
      setOpen(false);
      router.push(`/jobs/${result.jobId}`);
      return;
    }
    const subject = result.run.subject;
    setStarted({ runId: result.run.workflow_id, jobId: subject?.type === "job" ? subject.id : null });
  }

  const analyzeText = useMutation({
    mutationFn: () => api.jobs.analyzeText({ input_type: "text", text, source_url: sourceUrl.trim() || null }, newIdempotencyKey()),
    onSuccess: handleResult,
  });
  const analyzeUrl = useMutation({
    mutationFn: () => api.jobs.analyzeUrl(url.trim(), newIdempotencyKey()),
    onSuccess: handleResult,
  });
  const analyzeFile = useMutation({
    mutationFn: () => api.jobs.analyzeFile(file as File, fileSourceUrl.trim() || undefined, newIdempotencyKey()),
    onSuccess: handleResult,
  });
  const analyzeManual = useMutation({
    mutationFn: () => {
      const fields: ManualFields = {
        job_title: manual.job_title.trim(),
        company: manual.company.trim() || null,
        location: manual.location.trim() || null,
        work_mode: manual.work_mode || null,
        employment_type: manual.employment_type || null,
        experience: manual.experience.trim() || null,
        salary: manual.salary.trim() || null,
        application_url: manual.application_url.trim() || null,
        requirements: manual.requirements.trim() ? splitList(manual.requirements) : null,
        nice_to_have: manual.nice_to_have.trim() ? splitList(manual.nice_to_have) : null,
        responsibilities: manual.responsibilities.trim() ? splitList(manual.responsibilities) : null,
        description: manual.description.trim() || null,
      };
      return api.jobs.analyzeText({ input_type: "manual", manual_fields: fields }, newIdempotencyKey());
    },
    onSuccess: handleResult,
  });

  const pending = analyzeText.isPending || analyzeUrl.isPending || analyzeFile.isPending || analyzeManual.isPending;

  function reset() {
    setStarted(null);
    [analyzeText, analyzeUrl, analyzeFile, analyzeManual].forEach((m) => m.reset());
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function pasteInstead() {
    if (url.trim()) setSourceUrl(url.trim());
    analyzeUrl.reset();
    setTab("text");
  }

  const textLen = text.trim().length;
  const canFile = hasEndpoint("POST", "/jobs/analyze-file");
  const canUrl = hasEndpoint("POST", "/jobs/analyze-url");

  const submit = (fn: () => void) => (e: FormEvent) => {
    e.preventDefault();
    fn();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <PlusIcon aria-hidden="true" />
          Analyze a job
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Analyze a job</DialogTitle>
          <DialogDescription>
            Requirements are extracted with evidence quotes from the text. Nothing is applied for or sent.
          </DialogDescription>
        </DialogHeader>

        {started ? (
          <div className="space-y-3">
            <RunProgress
              runId={started.runId}
              title="Analysing job"
              onSettled={(run) => {
                void qc.invalidateQueries({ queryKey: ["jobs"] });
                const jobId = started.jobId ?? (run.subject?.type === "job" ? run.subject.id : null);
                if (isSuccessStatus(run.status) && jobId) {
                  toast.success("Job analysed");
                  setOpen(false);
                  reset();
                  router.push(`/jobs/${jobId}`);
                }
              }}
            />
            <div className="flex flex-wrap gap-2">
              {started.jobId && (
                <Button asChild variant="outline" size="sm">
                  <Link href={`/jobs/${started.jobId}`}>Open job now</Link>
                </Button>
              )}
              <Button variant="ghost" size="sm" onClick={reset}>
                Analyze another
              </Button>
            </div>
          </div>
        ) : (
          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
            <TabsList aria-label="How to provide the job">
              <TabsTrigger value="text">
                <ClipboardPasteIcon aria-hidden="true" />
                Paste text
              </TabsTrigger>
              {canUrl && (
                <TabsTrigger value="url">
                  <LinkIcon aria-hidden="true" />
                  URL
                </TabsTrigger>
              )}
              {canFile && (
                <TabsTrigger value="file">
                  <FileUpIcon aria-hidden="true" />
                  File
                </TabsTrigger>
              )}
              <TabsTrigger value="manual">
                <PencilLineIcon aria-hidden="true" />
                Manual fields
              </TabsTrigger>
            </TabsList>

            <TabsContent value="text">
              <form className="space-y-4" onSubmit={submit(() => analyzeText.mutate())}>
                <Field
                  id="jd-text"
                  label="Job description"
                  required
                  hint={`${textLen.toLocaleString()} characters · minimum ${MIN_TEXT}. LinkedIn posts: copy the full post text.`}
                >
                  <Textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} maxLength={MAX_TEXT} />
                </Field>
                <Field id="jd-source-url" label="Source URL (optional)" hint="Stored for provenance only; it is not fetched.">
                  <Input type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" />
                </Field>
                <ErrorBox error={analyzeText.error} />
                <Button type="submit" disabled={pending || textLen < MIN_TEXT}>
                  {analyzeText.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                  Analyze text
                </Button>
              </form>
            </TabsContent>

            {canUrl && (
              <TabsContent value="url">
                <form className="space-y-4" onSubmit={submit(() => analyzeUrl.mutate())}>
                  <Field
                    id="jd-url"
                    label="Job URL"
                    required
                    hint="Greenhouse, Lever and Ashby links use their public APIs. LinkedIn can't be fetched — paste the text instead."
                  >
                    <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://boards.greenhouse.io/…" />
                  </Field>
                  <ErrorBox error={analyzeUrl.error} onPasteInstead={pasteInstead} />
                  <Button type="submit" disabled={pending || !/^https?:\/\/\S+$/i.test(url.trim())}>
                    {analyzeUrl.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                    Fetch and analyze
                  </Button>
                </form>
              </TabsContent>
            )}

            {canFile && (
              <TabsContent value="file">
                <form className="space-y-4" onSubmit={submit(() => analyzeFile.mutate())}>
                  <Field id="jd-file" label="Job description file" required hint="PDF or DOCX, up to 5 MB." error={fileError}>
                    <Input
                      type="file"
                      accept={FILE_ACCEPT}
                      onChange={(e) => {
                        const f = e.target.files?.[0] ?? null;
                        setFileError(null);
                        if (f && f.size > MAX_FILE_BYTES) {
                          setFileError("That file is larger than 5 MB.");
                          setFile(null);
                          return;
                        }
                        setFile(f);
                      }}
                    />
                  </Field>
                  <Field id="jd-file-source" label="Source URL (optional)">
                    <Input type="url" value={fileSourceUrl} onChange={(e) => setFileSourceUrl(e.target.value)} placeholder="https://…" />
                  </Field>
                  <ErrorBox error={analyzeFile.error} />
                  <Button type="submit" disabled={pending || !file}>
                    {analyzeFile.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                    Upload and analyze
                  </Button>
                </form>
              </TabsContent>
            )}

            <TabsContent value="manual">
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit(() => analyzeManual.mutate())}>
                <Field id="m-title" label="Job title" required>
                  <Input value={manual.job_title} onChange={(e) => setManual({ ...manual, job_title: e.target.value })} maxLength={200} />
                </Field>
                <Field id="m-company" label="Company">
                  <Input value={manual.company} onChange={(e) => setManual({ ...manual, company: e.target.value })} maxLength={200} />
                </Field>
                <Field id="m-location" label="Location">
                  <Input value={manual.location} onChange={(e) => setManual({ ...manual, location: e.target.value })} maxLength={200} />
                </Field>
                <Field id="m-mode" label="Work mode">
                  <NativeSelect value={manual.work_mode} onChange={(e) => setManual({ ...manual, work_mode: e.target.value })}>
                    <option value="">Not stated</option>
                    <option value="remote">Remote</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">Onsite</option>
                  </NativeSelect>
                </Field>
                <Field id="m-type" label="Employment type">
                  <NativeSelect value={manual.employment_type} onChange={(e) => setManual({ ...manual, employment_type: e.target.value })}>
                    <option value="">Not stated</option>
                    <option value="full_time">Full time</option>
                    <option value="part_time">Part time</option>
                    <option value="contract">Contract</option>
                    <option value="internship">Internship</option>
                    <option value="temporary">Temporary</option>
                  </NativeSelect>
                </Field>
                <Field id="m-exp" label="Experience" hint="e.g. 0–2 years">
                  <Input value={manual.experience} onChange={(e) => setManual({ ...manual, experience: e.target.value })} maxLength={120} />
                </Field>
                <Field id="m-salary" label="Salary" hint="As stated, e.g. ₹12–18 LPA">
                  <Input value={manual.salary} onChange={(e) => setManual({ ...manual, salary: e.target.value })} maxLength={120} />
                </Field>
                <Field id="m-apply" label="Application URL">
                  <Input type="url" value={manual.application_url} onChange={(e) => setManual({ ...manual, application_url: e.target.value })} />
                </Field>
                <Field id="m-req" label="Requirements" hint="One per line" className="sm:col-span-2">
                  <Textarea rows={3} value={manual.requirements} onChange={(e) => setManual({ ...manual, requirements: e.target.value })} />
                </Field>
                <Field id="m-nice" label="Nice to have" hint="One per line" className="sm:col-span-2">
                  <Textarea rows={2} value={manual.nice_to_have} onChange={(e) => setManual({ ...manual, nice_to_have: e.target.value })} />
                </Field>
                <Field id="m-resp" label="Responsibilities" hint="One per line" className="sm:col-span-2">
                  <Textarea rows={3} value={manual.responsibilities} onChange={(e) => setManual({ ...manual, responsibilities: e.target.value })} />
                </Field>
                <Field id="m-desc" label="Description" className="sm:col-span-2">
                  <Textarea rows={3} value={manual.description} onChange={(e) => setManual({ ...manual, description: e.target.value })} maxLength={30000} />
                </Field>
                <div className="space-y-3 sm:col-span-2">
                  <ErrorBox error={analyzeManual.error} />
                  <Button type="submit" disabled={pending || !manual.job_title.trim()}>
                    {analyzeManual.isPending && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                    Analyze fields
                  </Button>
                </div>
              </form>
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArchiveIcon, ArchiveRestoreIcon, BookmarkIcon, BookmarkCheckIcon, FilterIcon, Loader2Icon, SearchIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/query-state";
import { PriorityBadge } from "@/components/score";
import { Time } from "@/components/time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { formatScore, titleCase } from "@/lib/utils";
import type { JobListItem } from "@/types/models";
import { AnalyzeJobDialog } from "./analyze-job-dialog";
import { activeFilterCount, EMPTY_FILTERS, filtersFromParams, filtersToParams, filtersToQuery, SORT_OPTIONS, type JobFilters } from "./job-filters";
import { ExperienceCell, locationsText, SalaryCell } from "./job-format";

const WORK_MODES = ["remote", "hybrid", "onsite", "unknown"];
const PRIORITIES = ["excellent", "strong", "moderate", "low"];
const STATUSES = ["", "analyzed", "analyzing", "queued", "failed", "archived"];

function CheckboxGroup({ legend, name, options, value, onChange }: { legend: string; name: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {options.map((o) => {
          const id = `${name}-${o}`;
          return (
            <div key={o} className="flex items-center gap-1.5">
              <Checkbox
                id={id}
                checked={value.includes(o)}
                onCheckedChange={(c) => onChange(c === true ? [...value, o] : value.filter((v) => v !== o))}
              />
              <Label htmlFor={id} className="font-normal">
                {titleCase(o)}
              </Label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

function FiltersForm({ initial, onApply }: { initial: JobFilters; onApply: (f: JobFilters) => void }) {
  const [f, setF] = useState(initial);
  const [expanded, setExpanded] = useState(activeFilterCount(initial) > 0);
  const set = <K extends keyof JobFilters>(k: K, v: JobFilters[K]) => setF((prev) => ({ ...prev, [k]: v }));

  function submit(e: FormEvent) {
    e.preventDefault();
    onApply(f);
  }

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <form onSubmit={submit} className="space-y-4" role="search" aria-label="Filter jobs">
          <div className="flex flex-col gap-3 md:flex-row md:items-end">
            <Field id="f-q" label="Search title or company" className="flex-1">
              <Input value={f.q} onChange={(e) => set("q", e.target.value)} placeholder="e.g. Acme or AI Engineer" />
            </Field>
            <Field id="f-sort" label="Sort by" className="md:w-56">
              <NativeSelect value={f.sort} onChange={(e) => set("sort", e.target.value)}>
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <div className="flex gap-2">
              <Button type="submit">
                <SearchIcon aria-hidden="true" />
                Apply
              </Button>
              <Button type="button" variant="outline" onClick={() => setExpanded((x) => !x)} aria-expanded={expanded} aria-controls="more-filters">
                <FilterIcon aria-hidden="true" />
                Filters{activeFilterCount(f) ? ` (${activeFilterCount(f)})` : ""}
              </Button>
            </div>
          </div>

          {expanded && (
            <div id="more-filters" className="grid gap-4 border-t pt-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field id="f-role" label="Role">
                <Input value={f.role} onChange={(e) => set("role", e.target.value)} placeholder="e.g. ML Engineer" />
              </Field>
              <Field id="f-location" label="Location" hint='A city, or "remote"'>
                <Input value={f.location} onChange={(e) => set("location", e.target.value)} />
              </Field>
              <Field id="f-exp" label="Max experience required (years)" hint="Jobs with unstated experience are included">
                <Input type="number" min={0} step={0.5} value={f.experience_max} onChange={(e) => set("experience_max", e.target.value)} />
              </Field>
              <Field id="f-salary" label="Minimum salary" hint="Compared with the disclosed maximum">
                <Input type="number" min={0} value={f.salary_min} onChange={(e) => set("salary_min", e.target.value)} />
              </Field>
              <Field id="f-skills" label="Skills (all required)" hint="Comma separated">
                <Input value={f.skills} onChange={(e) => set("skills", e.target.value)} placeholder="Python, FastAPI" />
              </Field>
              <Field id="f-source" label="Source" hint="Comma separated, e.g. greenhouse, lever">
                <Input value={f.source} onChange={(e) => set("source", e.target.value)} />
              </Field>
              <Field id="f-posted" label="Posted after">
                <Input type="date" value={f.posted_after} onChange={(e) => set("posted_after", e.target.value)} />
              </Field>
              <Field id="f-score" label="Minimum Job Score">
                <Input type="number" min={0} max={100} value={f.min_score} onChange={(e) => set("min_score", e.target.value)} />
              </Field>
              <Field id="f-saved" label="Saved">
                <NativeSelect value={f.saved} onChange={(e) => set("saved", e.target.value as JobFilters["saved"])}>
                  <option value="">All jobs</option>
                  <option value="true">Saved only</option>
                  <option value="false">Not saved</option>
                </NativeSelect>
              </Field>
              <Field id="f-status" label="Status">
                <NativeSelect value={f.status} onChange={(e) => set("status", e.target.value)}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s ? titleCase(s) : "Active (not archived)"}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <div className="sm:col-span-2">
                <CheckboxGroup legend="Work mode" name="wm" options={WORK_MODES} value={f.work_mode} onChange={(v) => set("work_mode", v)} />
              </div>
              <div className="sm:col-span-2">
                <CheckboxGroup legend="Priority" name="pr" options={PRIORITIES} value={f.priority} onChange={(v) => set("priority", v)} />
              </div>
              <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
                <Button type="submit" size="sm">
                  Apply filters
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setF(EMPTY_FILTERS);
                    onApply(EMPTY_FILTERS);
                  }}
                >
                  Clear all
                </Button>
              </div>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}

function RowActions({ job }: { job: JobListItem }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: (body: { saved?: boolean; archived?: boolean }) => api.jobs.patch(job.id, body),
    onSuccess: (_d, body) => {
      if (body.saved !== undefined) toast.success(body.saved ? "Job saved" : "Removed from saved");
      if (body.archived !== undefined) toast.success(body.archived ? "Job archived" : "Job restored");
      void qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const canPatch = hasEndpoint("PATCH", "/jobs/{}");
  const title = job.title || "job";
  const archived = job.status === "archived";
  return (
    <div className="flex items-center gap-1">
      <Button asChild size="sm" variant="outline">
        <Link href={`/jobs/${job.id}`}>Open</Link>
      </Button>
      {canPatch && (
        <>
          <Button
            size="icon"
            variant="ghost"
            aria-label={job.saved ? `Unsave ${title}` : `Save ${title}`}
            aria-pressed={job.saved}
            disabled={patch.isPending}
            onClick={() => patch.mutate({ saved: !job.saved })}
          >
            {job.saved ? <BookmarkCheckIcon className="text-primary" aria-hidden="true" /> : <BookmarkIcon aria-hidden="true" />}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label={archived ? `Restore ${title}` : `Archive ${title}`}
            disabled={patch.isPending}
            onClick={() => patch.mutate({ archived: !archived })}
          >
            {archived ? <ArchiveRestoreIcon aria-hidden="true" /> : <ArchiveIcon aria-hidden="true" />}
          </Button>
        </>
      )}
    </div>
  );
}

export function JobsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = filtersFromParams(params);
  const query = filtersToQuery(filters);
  const filterKey = filtersToParams(filters).toString();

  const jobs = useInfiniteQuery({
    queryKey: ["jobs", "list", filterKey],
    queryFn: ({ pageParam }) => api.jobs.list({ ...query, limit: 25, cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
  });

  function apply(f: JobFilters) {
    const p = filtersToParams(f);
    router.replace(p.toString() ? `${pathname}?${p}` : pathname);
  }

  const items = jobs.data?.pages.flatMap((p) => p.items) ?? [];
  const loadFailed = jobs.isError && !jobs.data;

  return (
    <>
      <PageHeader
        title="Job Search"
        description="Ranked by Job Score — a prioritisation heuristic, not a shortlist probability."
        actions={<AnalyzeJobDialog defaultOpen={params.get("analyze") === "1"} />}
      />
      <FiltersForm key={filterKey} initial={filters} onApply={apply} />

      {jobs.isPending ? (
        <LoadingState label="Loading jobs…" rows={6} />
      ) : loadFailed ? (
        <ErrorState error={jobs.error} title="Couldn't load jobs" onRetry={() => void jobs.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={activeFilterCount(filters) ? "No jobs match these filters" : "No jobs yet"}
          description={
            activeFilterCount(filters)
              ? "Try removing a filter."
              : "Paste a job description, or add sources in Settings so the daily run can discover jobs."
          }
        />
      ) : (
        <Card>
          <Table aria-label="Jobs">
            <TableHeader>
              <TableRow>
                <TableHead>Job</TableHead>
                <TableHead>Location / mode</TableHead>
                <TableHead>Experience</TableHead>
                <TableHead>Salary</TableHead>
                <TableHead>Job Score</TableHead>
                <TableHead>Best resume</TableHead>
                <TableHead>Posted</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="min-w-56">
                    <Link href={`/jobs/${job.id}`} className="font-medium text-primary hover:underline">
                      {job.title || "Untitled job"}
                    </Link>
                    <div className="text-muted-foreground">{job.company?.name ?? "Unknown company"}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {job.status !== "analyzed" && <Badge variant={job.status === "failed" ? "destructive" : "muted"}>{titleCase(job.status)}</Badge>}
                      {job.saved && <Badge variant="info">Saved</Badge>}
                      {job.has_application && <Badge variant="violet">Application</Badge>}
                      {job.sources.map((s) => (
                        <Badge key={s} variant="outline">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="min-w-40">{locationsText(job.locations, job.work_mode)}</TableCell>
                  <TableCell>
                    <ExperienceCell experience={job.experience} />
                  </TableCell>
                  <TableCell className="min-w-36">
                    <SalaryCell salary={job.salary} />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <span className="font-semibold tabular-nums">{formatScore(job.job_score, 1)}</span>
                      <PriorityBadge priority={job.priority} />
                    </div>
                  </TableCell>
                  <TableCell className="min-w-32">
                    {job.best_resume ? (
                      <>
                        <Link href={`/resumes/${job.best_resume.id}`} className="hover:underline">
                          {job.best_resume.label}
                        </Link>
                        <div className="text-xs text-muted-foreground">Match {formatScore(job.match_score, 1)}</div>
                      </>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Time value={job.posted_at} dateOnly />
                  </TableCell>
                  <TableCell>
                    <RowActions job={job} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {jobs.hasNextPage && (
            <div className="border-t p-3 text-center">
              <Button variant="outline" onClick={() => void jobs.fetchNextPage()} disabled={jobs.isFetchingNextPage}>
                {jobs.isFetchingNextPage && <Loader2Icon className="animate-spin" aria-hidden="true" />}
                Load more
              </Button>
            </div>
          )}
          {jobs.isFetchNextPageError && (
            <div className="p-3">
              <ErrorState error={jobs.error} title="Couldn't load more jobs" onRetry={() => void jobs.fetchNextPage()} />
            </div>
          )}
        </Card>
      )}
    </>
  );
}

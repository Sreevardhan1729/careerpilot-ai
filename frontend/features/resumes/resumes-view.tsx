"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { EmptyState, QueryView } from "@/components/query-state";
import { Time } from "@/components/time";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/endpoints";
import { titleCase } from "@/lib/utils";
import { DeleteResumeButton, SetDefaultButton, UploadResumeCard } from "./resume-actions";

export const RESUME_STATUS_VARIANT: Record<string, BadgeVariant> = {
  uploaded: "muted",
  parsing: "info",
  parsed: "success",
  needs_review: "warning",
  failed: "destructive",
};

export function ResumeStatusBadge({ status }: { status: string }) {
  return <Badge variant={RESUME_STATUS_VARIANT[status] ?? "secondary"}>{titleCase(status)}</Badge>;
}

export function ResumesView() {
  const query = useQuery({
    queryKey: ["resumes", "list"],
    queryFn: api.resumes.list,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "parsing" || r.status === "uploaded") ? 4000 : false),
  });
  return (
    <>
      <PageHeader title="Resume Library" description="Every resume version is kept. Matching ranks all of them against each job." />
      <div className="space-y-6">
        <UploadResumeCard />
        <QueryView query={query} loadingLabel="Loading resumes…" errorTitle="Couldn't load resumes">
          {(resumes) =>
            resumes.length === 0 ? (
              <EmptyState title="No resumes yet" description="Upload a PDF or DOCX to start matching jobs against it." />
            ) : (
              <Card>
                <Table aria-label="Resumes">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Resume</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Updated</TableHead>
                      <TableHead>
                        <span className="sr-only">Actions</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resumes.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell>
                          <Link href={`/resumes/${r.id}`} className="font-medium text-primary hover:underline">
                            {r.label}
                          </Link>
                          {r.is_default && (
                            <Badge variant="success" className="ml-2">
                              Default
                            </Badge>
                          )}
                          {r.label_suggested && r.label_suggested !== r.label && (
                            <p className="text-xs text-muted-foreground">Suggested label: {r.label_suggested}</p>
                          )}
                        </TableCell>
                        <TableCell>{r.category ?? "—"}</TableCell>
                        <TableCell>
                          <ResumeStatusBadge status={r.status} />
                        </TableCell>
                        <TableCell>
                          <Time value={r.updated_at} />
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap justify-end gap-1">
                            <SetDefaultButton resumeId={r.id} isDefault={r.is_default} label={r.label} />
                            <DeleteResumeButton resumeId={r.id} label={r.label} />
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            )
          }
        </QueryView>
      </div>
    </>
  );
}

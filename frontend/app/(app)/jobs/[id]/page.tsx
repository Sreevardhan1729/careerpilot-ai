import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/query-state";
import { JobDetailView } from "@/features/job-detail/job-detail-view";

export const metadata: Metadata = { title: "Job Intelligence" };

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={<LoadingState label="Loading job…" />}>
      <JobDetailView id={id} />
    </Suspense>
  );
}

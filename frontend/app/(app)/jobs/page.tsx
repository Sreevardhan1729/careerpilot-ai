import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/query-state";
import { JobsView } from "@/features/jobs/jobs-view";

export const metadata: Metadata = { title: "Job Search" };

export default function JobsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading jobs…" />}>
      <JobsView />
    </Suspense>
  );
}

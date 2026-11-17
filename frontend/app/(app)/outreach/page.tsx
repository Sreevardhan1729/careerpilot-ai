import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/query-state";
import { OutreachView } from "@/features/outreach/outreach-view";

export const metadata: Metadata = { title: "Outreach Center" };

export default function OutreachPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading outreach…" />}>
      <OutreachView />
    </Suspense>
  );
}

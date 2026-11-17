import type { Metadata } from "next";
import { Suspense } from "react";
import { LoadingState } from "@/components/query-state";
import { SettingsView } from "@/features/settings/settings-view";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading settings…" />}>
      <SettingsView />
    </Suspense>
  );
}

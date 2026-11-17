import type { Metadata } from "next";
import { ApplicationsView } from "@/features/applications/applications-view";

export const metadata: Metadata = { title: "Application Tracker" };

export default function ApplicationsPage() {
  return <ApplicationsView />;
}

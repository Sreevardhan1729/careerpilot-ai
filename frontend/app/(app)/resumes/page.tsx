import type { Metadata } from "next";
import { ResumesView } from "@/features/resumes/resumes-view";

export const metadata: Metadata = { title: "Resume Library" };

export default function ResumesPage() {
  return <ResumesView />;
}

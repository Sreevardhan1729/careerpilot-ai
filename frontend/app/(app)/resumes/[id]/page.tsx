import type { Metadata } from "next";
import { ResumeDetailView } from "@/features/resumes/resume-detail-view";

export const metadata: Metadata = { title: "Resume" };

export default async function ResumePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResumeDetailView id={id} />;
}

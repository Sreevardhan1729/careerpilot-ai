import type { BadgeVariant } from "@/components/ui/badge";

/** Resume-vs-job skill statuses (AGENT_DESIGN matching). Each is visually distinct by colour, icon AND text. */
export const SKILL_STATUS_META: Record<string, { label: string; description: string; variant: BadgeVariant; dashed?: boolean }> = {
  strong: { label: "Strong evidence", description: "Shown in a project or experience on the resume.", variant: "success" },
  listed_only: {
    label: "Weakly highlighted",
    description: "Listed in the skills section only — no project or experience shows it.",
    variant: "warning",
  },
  related: { label: "Related skill", description: "A closely related skill appears on the resume.", variant: "info" },
  profile_only: {
    label: "Profile only",
    description: "Confirmed in your profile but not on this resume.",
    variant: "violet",
  },
  no_evidence: {
    label: "No evidence",
    description: "Nothing on the resume or profile shows it. That doesn't mean you lack it.",
    variant: "outline",
    dashed: true,
  },
  confirmed_missing: { label: "Confirmed missing", description: "You marked this skill as one you don't have.", variant: "destructive" },
};

export function skillStatusMeta(status: string) {
  return SKILL_STATUS_META[status] ?? { label: status.replace(/_/g, " "), description: "", variant: "secondary" as BadgeVariant };
}

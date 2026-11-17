import { CheckCircle2Icon, CircleDashedIcon, CircleMinusIcon, GitBranchIcon, ListIcon, UserCheckIcon, XCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { skillStatusMeta } from "@/lib/skill-status";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof CheckCircle2Icon> = {
  strong: CheckCircle2Icon,
  listed_only: ListIcon,
  related: GitBranchIcon,
  profile_only: UserCheckIcon,
  no_evidence: CircleDashedIcon,
  confirmed_missing: XCircleIcon,
};

export function SkillStatusBadge({ status, className }: { status: string; className?: string }) {
  const meta = skillStatusMeta(status);
  const Icon = ICONS[status] ?? CircleMinusIcon;
  return (
    <Badge variant={meta.variant} className={cn(meta.dashed && "border-dashed border-slate-400 text-slate-700", className)} title={meta.description} data-status={status}>
      <Icon aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}

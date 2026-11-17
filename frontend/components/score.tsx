import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { cn, formatScore, titleCase } from "@/lib/utils";

const PRIORITY_VARIANT: Record<string, BadgeVariant> = {
  excellent: "success",
  strong: "info",
  moderate: "warning",
  low: "muted",
};

export function PriorityBadge({ priority }: { priority: string | null | undefined }) {
  if (!priority) return <Badge variant="outline">Unranked</Badge>;
  return <Badge variant={PRIORITY_VARIANT[priority] ?? "secondary"}>{titleCase(priority)}</Badge>;
}

/** A labelled 0–100 bar (role=meter for assistive tech). */
export function ScoreBar({
  label,
  score,
  weight,
  className,
}: {
  label: string;
  score: number | null | undefined;
  weight?: number | null;
  className?: string;
}) {
  const value = score == null ? null : Math.max(0, Math.min(100, score));
  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {value == null ? "Not scored" : formatScore(value)}
          {weight != null && <span className="ml-1 text-xs">× {weight}</span>}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value ?? undefined}
        aria-valuetext={value == null ? "Not scored" : `${formatScore(value)} out of 100`}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary" style={{ width: `${value ?? 0}%` }} />
      </div>
    </div>
  );
}

export function ScorePill({ score, label }: { score: number | null | undefined; label: string }) {
  return (
    <span className="inline-flex items-baseline gap-1 tabular-nums" title={label}>
      <span className="text-base font-semibold">{formatScore(score)}</span>
      <span className="sr-only">{label}</span>
    </span>
  );
}

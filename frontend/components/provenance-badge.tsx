import { AlertTriangleIcon, CalculatorIcon, CircleHelpIcon, QuoteIcon, SparklesIcon } from "lucide-react";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { PROVENANCE_META, salarySourceMeta, type ProvenanceKind } from "@/lib/provenance";
import { cn } from "@/lib/utils";

const STYLE: Record<ProvenanceKind, { variant: BadgeVariant; Icon: typeof QuoteIcon; extra?: string }> = {
  explicit: { variant: "success", Icon: QuoteIcon },
  inferred: { variant: "info", Icon: SparklesIcon },
  estimate: { variant: "warning", Icon: AlertTriangleIcon },
  unverified: { variant: "outline", Icon: CircleHelpIcon, extra: "border-dashed border-slate-400 text-slate-700" },
  heuristic: { variant: "violet", Icon: CalculatorIcon },
};

/**
 * How a value is known. Each kind has its own colour, icon and text so the distinction never relies on colour alone.
 */
export function ProvenanceBadge({
  kind,
  label,
  className,
  describe = true,
}: {
  kind: ProvenanceKind;
  label?: string;
  className?: string;
  /** Include the long description for screen readers. Turn off inside form labels, where it bloats the field name. */
  describe?: boolean;
}) {
  const meta = PROVENANCE_META[kind];
  const style = STYLE[kind];
  return (
    <Badge variant={style.variant} className={cn(style.extra, className)} title={meta.description} data-kind={kind}>
      <style.Icon aria-hidden="true" />
      {label ?? meta.label}
      {describe && <span className="sr-only"> — {meta.description}</span>}
    </Badge>
  );
}

/** Salary source classification (FR-DISC-09): estimates are never shown as confirmed. */
export function SalaryBadge({ sourceType, className }: { sourceType: string | null | undefined; className?: string }) {
  const meta = salarySourceMeta(sourceType);
  if (!meta.kind) {
    return (
      <Badge variant="muted" className={className} title={meta.description} data-kind="not_disclosed">
        {meta.label}
      </Badge>
    );
  }
  return <ProvenanceBadge kind={meta.kind} label={meta.label} className={className} />;
}

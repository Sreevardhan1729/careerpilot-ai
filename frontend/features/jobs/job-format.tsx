import { SalaryBadge } from "@/components/provenance-badge";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { formatSalaryRange } from "@/lib/provenance";
import { locationLabels } from "@/lib/shapes";
import { titleCase } from "@/lib/utils";
import type { ExperienceOut, SalaryOut } from "@/types/models";

export function experienceLabel(e: ExperienceOut | null | undefined): string {
  if (!e || (e.min_years == null && e.max_years == null)) return "Not stated";
  if (e.min_years != null && e.max_years != null) {
    return e.min_years === e.max_years ? `${e.min_years} yrs` : `${e.min_years}–${e.max_years} yrs`;
  }
  if (e.min_years != null) return `${e.min_years}+ yrs`;
  return `Up to ${e.max_years} yrs`;
}

export function ExperienceCell({ experience }: { experience: ExperienceOut }) {
  const known = experience.min_years != null || experience.max_years != null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {experienceLabel(experience)}
      {known && !experience.explicit && <ProvenanceBadge kind="inferred" />}
    </span>
  );
}

export function SalaryCell({ salary }: { salary: SalaryOut }) {
  const range = formatSalaryRange(salary);
  return (
    <span className="inline-flex flex-col gap-1">
      {range && <span className="tabular-nums">{range}</span>}
      <SalaryBadge sourceType={salary.source_type} />
    </span>
  );
}

export function locationsText(locations: unknown, workMode?: string): string {
  const labels = locationLabels(locations);
  const mode = workMode && workMode !== "unknown" ? titleCase(workMode) : null;
  return [labels.join(" · ") || null, mode].filter(Boolean).join(" — ") || "Not stated";
}

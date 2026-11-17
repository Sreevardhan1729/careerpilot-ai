/** Labels for how a value is known (FR-UI-04: estimated, inferred and unverified values are visually distinct). */

export type ProvenanceKind = "explicit" | "inferred" | "estimate" | "unverified" | "heuristic";

export const PROVENANCE_META: Record<ProvenanceKind, { label: string; description: string }> = {
  explicit: { label: "Stated", description: "Stated explicitly in the source text." },
  inferred: { label: "Inferred", description: "Inferred from the source; not stated word for word." },
  estimate: { label: "Estimate", description: "An estimate from a third party. Not confirmed by the employer." },
  unverified: { label: "Unverified", description: "Could not be verified against the source." },
  heuristic: { label: "Heuristic", description: "Computed by deterministic rules — a prioritisation aid, not a fact." },
};

export type SalarySourceType = "jd" | "source_website" | "third_party_estimate" | "not_disclosed";

export const SALARY_SOURCE_META: Record<SalarySourceType, { label: string; kind: ProvenanceKind | null; description: string }> = {
  not_disclosed: { label: "Not disclosed", kind: null, description: "The job does not disclose a salary." },
  jd: { label: "From JD", kind: "explicit", description: "Stated in the job description." },
  source_website: {
    label: "Reported by source",
    kind: "explicit",
    description: "Published by the job board or careers site, not in the description text.",
  },
  third_party_estimate: {
    label: "Third-party estimate — not confirmed",
    kind: "estimate",
    description: "An estimate from a third-party site. The employer has not confirmed it.",
  },
};

export function salarySourceMeta(sourceType: string | null | undefined) {
  return SALARY_SOURCE_META[(sourceType as SalarySourceType) ?? "not_disclosed"] ?? {
    label: "Unknown source",
    kind: "unverified" as const,
    description: "The salary source could not be classified.",
  };
}

/** Pick a kind from job evidence flags. */
export function evidenceKind(e: { explicit?: boolean | null; verified?: boolean | null }): ProvenanceKind {
  if (e.verified === false) return "unverified";
  return e.explicit ? "explicit" : "inferred";
}

const CURRENCY_SYMBOL: Record<string, string> = { INR: "₹", USD: "$", EUR: "€", GBP: "£" };

function trim(n: number): string {
  return n.toFixed(1).replace(/\.0$/, "");
}

function compact(n: number, currency: string | null | undefined): string {
  if (currency === "INR") {
    if (n >= 10_000_000) return `${trim(n / 10_000_000)} Cr`;
    if (n >= 100_000) return `${trim(n / 100_000)} L`;
  }
  if (n >= 1_000_000) return `${trim(n / 1_000_000)}M`;
  if (n >= 1_000) return `${trim(n / 1_000)}k`;
  return String(n);
}

const PERIOD_LABEL: Record<string, string> = { annual: "year", monthly: "month", hourly: "hour" };

export function formatSalaryRange(s: {
  minimum?: number | null;
  maximum?: number | null;
  currency?: string | null;
  period?: string | null;
  source_type?: string | null;
}): string | null {
  if (s.source_type === "not_disclosed" || (s.minimum == null && s.maximum == null)) return null;
  const sym = s.currency ? (CURRENCY_SYMBOL[s.currency] ?? `${s.currency} `) : "";
  const lo = s.minimum != null ? compact(s.minimum, s.currency) : null;
  const hi = s.maximum != null ? compact(s.maximum, s.currency) : null;
  const range = lo && hi && lo !== hi ? `${sym}${lo}–${hi}` : `${sym}${lo ?? hi}`;
  const period = s.period && PERIOD_LABEL[s.period] ? ` / ${PERIOD_LABEL[s.period]}` : "";
  return `${range}${period}`;
}

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatSalaryRange, salarySourceMeta } from "@/lib/provenance";
import { ProvenanceBadge, SalaryBadge } from "./provenance-badge";

describe("ProvenanceBadge", () => {
  it.each([
    ["explicit", "Stated"],
    ["inferred", "Inferred"],
    ["estimate", "Estimate"],
    ["unverified", "Unverified"],
    ["heuristic", "Heuristic"],
  ] as const)("labels %s as %s with an accessible description", (kind, label) => {
    const { container } = render(<ProvenanceBadge kind={kind} />);
    const badge = container.querySelector(`[data-kind="${kind}"]`);
    expect(badge).not.toBeNull();
    expect(badge).toHaveTextContent(label);
    // The description is available to screen readers, not only as colour.
    expect(badge?.querySelector(".sr-only")?.textContent).toMatch(/—/);
  });

  it("gives each kind a distinct style", () => {
    const kinds = ["explicit", "inferred", "estimate", "unverified", "heuristic"] as const;
    const classes = kinds.map((k) => render(<ProvenanceBadge kind={k} />).container.firstElementChild?.className);
    expect(new Set(classes).size).toBe(kinds.length);
  });

  it("accepts a custom label", () => {
    render(<ProvenanceBadge kind="inferred" label="From resume" />);
    expect(screen.getByText("From resume")).toBeInTheDocument();
  });
});

describe("SalaryBadge", () => {
  it.each([
    ["not_disclosed", "Not disclosed"],
    ["jd", "From JD"],
    ["source_website", "Reported by source"],
    ["third_party_estimate", "Third-party estimate — not confirmed"],
  ])("labels %s as %s", (sourceType, label) => {
    render(<SalaryBadge sourceType={sourceType} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("never presents a third-party estimate as confirmed", () => {
    const { container } = render(<SalaryBadge sourceType="third_party_estimate" />);
    expect(container.querySelector('[data-kind="estimate"]')).not.toBeNull();
    expect(salarySourceMeta("third_party_estimate").kind).toBe("estimate");
  });

  it("treats a missing source type as not disclosed", () => {
    render(<SalaryBadge sourceType={null} />);
    expect(screen.getByText("Not disclosed")).toBeInTheDocument();
  });
});

describe("formatSalaryRange", () => {
  it("formats INR in lakhs and hides undisclosed salaries", () => {
    expect(formatSalaryRange({ minimum: 1_200_000, maximum: 1_800_000, currency: "INR", period: "annual", source_type: "jd" })).toBe("₹12 L–18 L / year");
    expect(formatSalaryRange({ minimum: 90_000, maximum: null, currency: "USD", period: "annual", source_type: "source_website" })).toBe("$90k / year");
    expect(formatSalaryRange({ source_type: "not_disclosed" })).toBeNull();
  });
});

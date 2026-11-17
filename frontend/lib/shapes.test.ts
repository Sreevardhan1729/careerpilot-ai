import { describe, expect, it } from "vitest";
import { applicationPreview, claimCheck, effectiveNodes, jobScoreBreakdown, locationLabels, personalizationEvidence, progressNodes, runApproval } from "./shapes";

describe("shape normalisers", () => {
  it("splits claim-check violations by severity", () => {
    const c = claimCheck({
      passed: false,
      violations: [
        { code: "unsupported_metric", severity: "blocking", detail: "'40%' not in facts" },
        { code: "tone", severity: "warning", detail: "long" },
      ],
    });
    expect(c.passed).toBe(false);
    expect(c.blocking.map((v) => v.code)).toEqual(["unsupported_metric"]);
    expect(c.warnings.map((v) => v.code)).toEqual(["tone"]);
    expect(claimCheck(null)).toEqual({ passed: null, blocking: [], warnings: [] });
  });

  it("orders job score components M, F, E_elig, L, S", () => {
    const b = jobScoreBreakdown({
      score: 81.5,
      components: { S: { score: 50, weight: 0.05 }, M: { score: 84, weight: 0.5, explanation: "Best match" }, F: { score: 100, weight: 0.2 } },
      disqualifiers: ["Requires 5+ years"],
    });
    expect(b?.components.map((c) => c.key)).toEqual(["M", "F", "S"]);
    expect(b?.disqualifiers).toEqual(["Requires 5+ years"]);
    expect(jobScoreBreakdown(null)).toBeNull();
    expect(jobScoreBreakdown({})).toBeNull();
  });

  it("reads run approval and progress safely", () => {
    expect(runApproval({ approval_id: "a", payload_hash: "h", payload_preview: { to: "x" } })?.payload_preview).toEqual({ to: "x" });
    expect(runApproval({})).toBeNull();
    expect(progressNodes([{ node: "llm_extract", status: "completed" }, "junk"])).toMatchObject([
      { node: "llm_extract", status: "completed" },
      { node: "step", status: "pending" },
    ]);
  });

  it("flags answers that need user input", () => {
    const p = applicationPreview({
      answers: [
        { question: "Notice period?", answer: "30 days", source_fact_ids: ["f1"] },
        { question: "Visa?", answer: null, needs_user_input: true },
      ],
      manual_steps: ["Open URL"],
    });
    expect(p?.answers.map((a) => a.needsUserInput)).toEqual([false, true]);
    expect(p?.manualSteps).toEqual(["Open URL"]);
  });

  it("accepts both personalisation evidence shapes", () => {
    expect(personalizationEvidence([{ id: "chunk:1", kind: "project", text: "DocQA" }, { fact: "F", source: "job", ref_id: "j" }])).toEqual([
      { fact: "DocQA", source: "project", ref_id: "chunk:1" },
      { fact: "F", source: "job", ref_id: "j" },
    ]);
  });

  it("labels locations", () => {
    expect(locationLabels([{ city: "Bengaluru", country: "IN", raw: "Bengaluru, India" }, { city: "Pune", country: "IN" }])).toEqual([
      "Bengaluru, India",
      "Pune, IN",
    ]);
  });

  it("derives node status when the backend leaves started nodes as running", () => {
    const nodes = progressNodes([
      { node: "fetch_content", status: "running" },
      { node: "extract", status: "running" },
    ]);
    expect(effectiveNodes(nodes, "running").map((n) => n.status)).toEqual(["completed", "running"]);
    expect(effectiveNodes(nodes, "completed").map((n) => n.status)).toEqual(["completed", "completed"]);
    expect(effectiveNodes(nodes, "failed").map((n) => n.status)).toEqual(["completed", "failed"]);
    expect(effectiveNodes(nodes, "awaiting_approval").map((n) => n.status)).toEqual(["completed", "awaiting_approval"]);
  });
});

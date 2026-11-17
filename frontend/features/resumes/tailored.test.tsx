import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildDraftPayload } from "@/features/outreach/write-draft-dialog";
import { ApiError } from "@/lib/api";
import { normalizeParsed } from "./parsed";
import { buildTailoredPayload, editableTexts, initialSkillOrder, moveItem, resumeSkills, tailoredProblems, type TailoredFormState } from "./tailored";
import { TailoredProblemsView } from "./tailored-version-dialog";

const parsed = normalizeParsed({
  summary: "AI engineer building LLM apps.",
  skills: [
    { name: "Python", section: "skills" },
    { name: "FastAPI", section: "skills" },
    { name: "pgvector", section: "project" },
    { name: "python", section: "experience" },
  ],
  experience: [{ title: "AI Engineering Intern", bullets: ["Built a RAG pipeline with LangChain", ""] }],
  projects: [{ title: "DocQA", description: "Question answering over PDFs", bullets: ["Shipped FastAPI services"] }],
  achievements: [{ text: "Won a hackathon" }],
});

const base: TailoredFormState = {
  jobId: "job-1",
  baseVersionId: "ver-1",
  originalSkills: ["Python", "FastAPI", "pgvector"],
  skillOrder: ["Python", "FastAPI", "pgvector"],
  selectedRewrites: [],
  edits: [],
  changeSummary: "",
  jobTitle: "AI Engineer",
};

describe("tailored version form helpers", () => {
  it("lists only texts the backend accepts as `before`", () => {
    const texts = editableTexts(parsed);
    expect(texts.map((t) => t.section)).toEqual(["summary", "experience", "project", "project", "achievement"]);
    expect(texts.map((t) => t.text)).toContain("Built a RAG pipeline with LangChain");
    expect(texts.map((t) => t.text)).not.toContain("");
  });

  it("dedupes resume skills case-insensitively", () => {
    expect(resumeSkills(parsed)).toEqual(["Python", "FastAPI", "pgvector"]);
  });

  it("prefills skill order from suggestions, keeping only the resume's own skills", () => {
    expect(initialSkillOrder(["Python", "FastAPI", "pgvector"], ["pgvector", "Kubernetes", "fastapi"])).toEqual(["pgvector", "FastAPI", "Python"]);
    expect(initialSkillOrder(["Python"], null)).toEqual(["Python"]);
  });

  it("moves items up and down within bounds", () => {
    expect(moveItem(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    expect(moveItem(["a", "b"], 0, -1)).toEqual(["a", "b"]);
  });
});

describe("buildTailoredPayload", () => {
  it("sends only a skill order when nothing else changed", () => {
    const { payload, errors } = buildTailoredPayload({ ...base, skillOrder: ["pgvector", "Python", "FastAPI"] });
    expect(errors).toEqual([]);
    expect(payload).toEqual({
      job_id: "job-1",
      base_version_id: "ver-1",
      changes: [],
      skill_order: ["pgvector", "Python", "FastAPI"],
      change_summary: "Tailored for AI Engineer: skill order updated",
    });
  });

  it("combines ticked rewrites and manual edits, trims them and drops no-op edits", () => {
    const { payload } = buildTailoredPayload({
      ...base,
      selectedRewrites: [{ section: "experience", before: "Built a RAG pipeline with LangChain", after: " Built a RAG pipeline with LangChain and pgvector ", evidence_refs: ["chunk:1"] }],
      edits: [
        { section: "project", before: "Shipped FastAPI services", after: "Shipped FastAPI services for prompt evaluation" },
        { section: "summary", before: "AI engineer building LLM apps.", after: "AI engineer building LLM apps." },
      ],
      changeSummary: "  Lead with retrieval work ",
    });
    expect(payload?.skill_order).toBeNull();
    expect(payload?.changes).toEqual([
      { section: "experience", before: "Built a RAG pipeline with LangChain", after: "Built a RAG pipeline with LangChain and pgvector", evidence_refs: ["chunk:1"] },
      { section: "project", before: "Shipped FastAPI services", after: "Shipped FastAPI services for prompt evaluation", evidence_refs: [] },
    ]);
    expect(payload?.change_summary).toBe("Lead with retrieval work");
  });

  it("refuses an empty version, duplicate edits and skills not on the resume", () => {
    expect(buildTailoredPayload(base).errors[0]).toMatch(/Nothing to change/);
    const dup = buildTailoredPayload({
      ...base,
      edits: [
        { section: "project", before: "Shipped FastAPI services", after: "A" },
        { section: "project", before: "Shipped FastAPI services", after: "B" },
      ],
    });
    expect(dup.payload).toBeNull();
    expect(dup.errors.join(" ")).toMatch(/Two changes edit the same text/);
    const unknown = buildTailoredPayload({ ...base, skillOrder: ["Kubernetes", "Python", "FastAPI", "pgvector"] });
    expect(unknown.errors.join(" ")).toMatch(/aren't in this resume: Kubernetes/);
  });
});

describe("422 violation rendering", () => {
  const violationError = new ApiError({
    status: 422,
    code: "validation_error",
    message: "A change adds something your resume doesn't support.",
    details: {
      violations: [
        { code: "unsupported_metric", severity: "blocking", detail: "'40%' does not appear in your verified facts." },
        { code: "unsupported_skill", severity: "blocking", detail: "Claims Kubernetes, which your resumes/profile don't show." },
      ],
    },
  });

  it("parses violations, unknown skills and unknown text", () => {
    expect(tailoredProblems(violationError)?.violations).toHaveLength(2);
    const unknown = tailoredProblems(
      new ApiError({ status: 422, code: "validation_error", message: "Skill order may only use skills already in this resume.", details: { unknown: ["Kubernetes"] } }),
    );
    expect(unknown?.unknownSkills).toEqual(["Kubernetes"]);
    expect(tailoredProblems(new ApiError({ status: 409, code: "conflict", message: "x" }))).toBeNull();
  });

  it("renders each claim-check violation inline", () => {
    render(<TailoredProblemsView error={violationError} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("A change adds something your resume doesn't support.");
    const list = within(alert).getByRole("list", { name: "Claim-check violations" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Unsupported Metric: '40%' does not appear in your verified facts.");
    expect(items[1]).toHaveTextContent("Unsupported Skill");
  });

  it("renders unknown skills and unknown before text", () => {
    render(
      <TailoredProblemsView
        error={new ApiError({ status: 422, code: "validation_error", message: "Nope.", details: { unknown: ["Kubernetes", "Go"], before: "Made up bullet" } })}
      />,
    );
    expect(screen.getByText(/Not in this resume: Kubernetes, Go/)).toBeInTheDocument();
    expect(screen.getByText("Made up bullet")).toBeInTheDocument();
  });

  it("falls back to the plain message for other errors", () => {
    render(<TailoredProblemsView error={new ApiError({ status: 0, code: "network_error", message: "offline" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/Can't reach the CareerPilot API/);
  });
});

describe("buildDraftPayload", () => {
  it("sends subject only for email message types", () => {
    expect(buildDraftPayload({ jobId: "", personId: "", messageType: "linkedin_connection", subject: "ignored", body: " Hi " })).toEqual({
      job_id: null,
      person_id: null,
      message_type: "linkedin_connection",
      subject: null,
      body: "Hi",
    });
    expect(buildDraftPayload({ jobId: "j", personId: "p", messageType: "recruiter_email", subject: " Hello ", body: "Body" }).subject).toBe("Hello");
  });
});

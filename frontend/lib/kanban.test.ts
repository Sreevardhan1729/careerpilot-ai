import { describe, expect, it } from "vitest";
import { KANBAN_COLUMNS, MANUAL_STATUS_OPTIONS, columnForStatus, groupByColumn } from "./kanban";

describe("D13 tracker column mapping", () => {
  it.each([
    ["interested", "interested"],
    ["resume_selected", "preparing"],
    ["draft_prepared", "preparing"],
    ["awaiting_approval", "awaiting_approval"],
    ["ready_to_submit", "awaiting_approval"],
    ["applied", "applied"],
    ["recruiter_contacted", "recruiter_contacted"],
    ["interview_scheduled", "interview"],
    ["rejected", "rejected"],
    ["offer_received", "offer"],
  ])("%s → %s", (status, column) => {
    expect(columnForStatus(status)).toBe(column);
  });

  it("archives withdrawn and keeps discovered/analysed out of the tracker", () => {
    expect(columnForStatus("withdrawn")).toBe("archived");
    expect(columnForStatus("discovered")).toBe("untracked");
    expect(columnForStatus("analyzed")).toBe("untracked");
  });

  it("has the eight spec columns in order", () => {
    expect(KANBAN_COLUMNS.map((c) => c.title)).toEqual([
      "Interested",
      "Preparing",
      "Awaiting approval",
      "Applied",
      "Recruiter contacted",
      "Interview",
      "Rejected",
      "Offer",
    ]);
  });

  it("groups applications by column", () => {
    const g = groupByColumn([
      { id: "1", status: "draft_prepared" },
      { id: "2", status: "resume_selected" },
      { id: "3", status: "withdrawn" },
      { id: "4", status: "offer_received" },
      { id: "5", status: "analyzed" },
    ]);
    expect(g.columns.preparing.map((a) => a.id)).toEqual(["1", "2"]);
    expect(g.columns.offer.map((a) => a.id)).toEqual(["4"]);
    expect(g.columns.interested).toEqual([]);
    expect(g.archived.map((a) => a.id)).toEqual(["3"]);
    expect(g.untracked.map((a) => a.id)).toEqual(["5"]);
  });

  it("never offers flow-controlled statuses as manual moves", () => {
    for (const s of ["applied", "awaiting_approval", "ready_to_submit"]) {
      expect(MANUAL_STATUS_OPTIONS as readonly string[]).not.toContain(s);
    }
  });
});

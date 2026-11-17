import { describe, expect, it } from "vitest";
import { BACKOFF_AFTER_MS, POLL_FAST_MS, POLL_SLOW_MS, isPausedStatus, isTerminalStatus, pollInterval, shouldPoll } from "./agent-run";

describe("agent run terminal-state logic", () => {
  it.each(["completed", "partially_completed", "failed", "cancelled"])("%s is terminal", (s) => {
    expect(isTerminalStatus(s)).toBe(true);
    expect(shouldPoll(s)).toBe(false);
    expect(pollInterval(s, 0, 1000)).toBe(false);
  });

  it.each(["queued", "running"])("%s keeps polling", (s) => {
    expect(isTerminalStatus(s)).toBe(false);
    expect(shouldPoll(s)).toBe(true);
  });

  it("treats awaiting_approval as a pause, not terminal", () => {
    expect(isTerminalStatus("awaiting_approval")).toBe(false);
    expect(isPausedStatus("awaiting_approval")).toBe(true);
    expect(shouldPoll("awaiting_approval")).toBe(false);
    expect(pollInterval("awaiting_approval", 0, 0)).toBe(false);
  });

  it("polls every 2s, backing off to 5s after 2 minutes", () => {
    expect(pollInterval("running", 0, 0)).toBe(POLL_FAST_MS);
    expect(pollInterval("running", 0, BACKOFF_AFTER_MS - 1)).toBe(2000);
    expect(pollInterval("running", 0, BACKOFF_AFTER_MS)).toBe(POLL_SLOW_MS);
    expect(POLL_SLOW_MS).toBe(5000);
  });

  it("keeps polling while the status is still unknown", () => {
    expect(pollInterval(undefined, 0, 0)).toBe(2000);
    expect(isTerminalStatus(null)).toBe(false);
  });
});

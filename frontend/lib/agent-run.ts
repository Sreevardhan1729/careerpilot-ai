/** Workflow polling rules (docs/API_SPEC.md §1.6, ARCHITECTURE §9). Pure functions so they are unit-testable. */

export const TERMINAL_RUN_STATUSES = ["completed", "partially_completed", "failed", "cancelled"] as const;
export type TerminalRunStatus = (typeof TERMINAL_RUN_STATUSES)[number];

export const POLL_FAST_MS = 2_000;
export const POLL_SLOW_MS = 5_000;
export const BACKOFF_AFTER_MS = 120_000;

export function isTerminalStatus(status: string | null | undefined): status is TerminalRunStatus {
  return !!status && (TERMINAL_RUN_STATUSES as readonly string[]).includes(status);
}

/** `awaiting_approval` pauses a run: stop polling and show the approval UI. It is not terminal. */
export function isPausedStatus(status: string | null | undefined): boolean {
  return status === "awaiting_approval";
}

export function shouldPoll(status: string | null | undefined): boolean {
  return !isTerminalStatus(status) && !isPausedStatus(status);
}

/**
 * Polling interval for the current status, or `false` to stop.
 * Every 2 s while active; backs off to 5 s once the run has been watched for 2 minutes.
 * An unknown status (first fetch not done yet) keeps polling.
 */
export function pollInterval(status: string | null | undefined, watchingSinceMs: number, nowMs: number): number | false {
  if (!shouldPoll(status)) return false;
  return nowMs - watchingSinceMs >= BACKOFF_AFTER_MS ? POLL_SLOW_MS : POLL_FAST_MS;
}

export function isSuccessStatus(status: string | null | undefined): boolean {
  return status === "completed" || status === "partially_completed";
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_approval: "Awaiting your approval",
  partially_completed: "Partially completed",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  skipped: "Skipped",
  pending: "Pending",
  dead: "Failed (gave up)",
};

export function runStatusLabel(status: string | null | undefined): string {
  if (!status) return "Starting…";
  return RUN_STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

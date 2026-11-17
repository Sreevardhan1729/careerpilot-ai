/** Application tracker columns — PRD decision D13. */

export const KANBAN_COLUMNS = [
  { id: "interested", title: "Interested", statuses: ["interested"] },
  { id: "preparing", title: "Preparing", statuses: ["resume_selected", "draft_prepared"] },
  { id: "awaiting_approval", title: "Awaiting approval", statuses: ["awaiting_approval", "ready_to_submit"] },
  { id: "applied", title: "Applied", statuses: ["applied"] },
  { id: "recruiter_contacted", title: "Recruiter contacted", statuses: ["recruiter_contacted"] },
  { id: "interview", title: "Interview", statuses: ["interview_scheduled"] },
  { id: "rejected", title: "Rejected", statuses: ["rejected"] },
  { id: "offer", title: "Offer", statuses: ["offer_received"] },
] as const;

export type KanbanColumnId = (typeof KANBAN_COLUMNS)[number]["id"];

/** Withdrawn applications are archived (hidden from the board). */
export const ARCHIVED_STATUSES = ["withdrawn"] as const;
/** Discovered and analysed jobs live in Job Search, not the tracker. */
export const UNTRACKED_STATUSES = ["discovered", "analyzed"] as const;

export const APPLICATION_STATUS_LABELS: Record<string, string> = {
  discovered: "Discovered",
  analyzed: "Analysed",
  interested: "Interested",
  resume_selected: "Resume selected",
  draft_prepared: "Draft prepared",
  awaiting_approval: "Awaiting approval",
  ready_to_submit: "Ready to submit",
  applied: "Applied",
  recruiter_contacted: "Recruiter contacted",
  interview_scheduled: "Interview scheduled",
  rejected: "Rejected",
  offer_received: "Offer received",
  withdrawn: "Withdrawn",
};

/**
 * Statuses the user may set directly with PATCH. `awaiting_approval` / `ready_to_submit` come from the approval flow,
 * and `applied` requires confirmation evidence (FR-APP-05), so they are never offered here.
 */
export const MANUAL_STATUS_OPTIONS = [
  "interested",
  "resume_selected",
  "draft_prepared",
  "recruiter_contacted",
  "interview_scheduled",
  "rejected",
  "offer_received",
  "withdrawn",
] as const;

export type ColumnPlacement = KanbanColumnId | "archived" | "untracked";

export function columnForStatus(status: string): ColumnPlacement {
  if ((ARCHIVED_STATUSES as readonly string[]).includes(status)) return "archived";
  for (const col of KANBAN_COLUMNS) {
    if ((col.statuses as readonly string[]).includes(status)) return col.id;
  }
  return "untracked";
}

export interface Grouped<T> {
  columns: Record<KanbanColumnId, T[]>;
  archived: T[];
  untracked: T[];
}

export function groupByColumn<T extends { status: string }>(items: T[]): Grouped<T> {
  const columns = Object.fromEntries(KANBAN_COLUMNS.map((c) => [c.id, [] as T[]])) as Record<KanbanColumnId, T[]>;
  const archived: T[] = [];
  const untracked: T[] = [];
  for (const item of items) {
    const placement = columnForStatus(item.status);
    if (placement === "archived") archived.push(item);
    else if (placement === "untracked") untracked.push(item);
    else columns[placement].push(item);
  }
  return { columns, archived, untracked };
}

export function statusLabel(status: string): string {
  return APPLICATION_STATUS_LABELS[status] ?? status.replace(/_/g, " ");
}

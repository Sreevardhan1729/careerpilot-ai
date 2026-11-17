import { DEFAULT_TIMEZONE } from "./env";

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function safeTz(tz: string | null | undefined): string {
  const zone = tz || DEFAULT_TIMEZONE;
  try {
    new Intl.DateTimeFormat("en-IN", { timeZone: zone });
    return zone;
  } catch {
    return DEFAULT_TIMEZONE;
  }
}

/** Formats an ISO timestamp in the user's timezone. Date-only values (YYYY-MM-DD) are never shifted. */
export function formatDateTime(value: string | null | undefined, tz?: string | null): string {
  if (!value) return "—";
  if (DATE_ONLY.test(value)) return formatDate(value, tz);
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: safeTz(tz),
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

export function formatDate(value: string | null | undefined, tz?: string | null): string {
  if (!value) return "—";
  if (DATE_ONLY.test(value)) {
    const [y, m, d] = value.split("-").map(Number);
    return new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }).format(
      new Date(Date.UTC(y, m - 1, d)),
    );
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { timeZone: safeTz(tz), day: "numeric", month: "short", year: "numeric" }).format(d);
}

export function formatRelative(value: string | null | undefined, now: number = Date.now()): string {
  if (!value) return "—";
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return value;
  const diff = Math.round((t - now) / 1000);
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return rtf.format(diff, "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

/** Today's date (YYYY-MM-DD) in the given timezone. */
export function todayIn(tz?: string | null): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: safeTz(tz), year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(),
  );
  return parts;
}

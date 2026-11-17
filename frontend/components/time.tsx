"use client";

import { useTimezone } from "@/hooks/use-me";
import { formatDate, formatDateTime } from "@/lib/time";

/** Renders a UTC timestamp in the user's timezone. */
export function Time({ value, dateOnly = false, className }: { value: string | null | undefined; dateOnly?: boolean; className?: string }) {
  const tz = useTimezone();
  if (!value) return <span className={className}>—</span>;
  return (
    <time dateTime={value} className={className} title={`${formatDateTime(value, tz)} (${tz})`}>
      {dateOnly ? formatDate(value, tz) : formatDateTime(value, tz)}
    </time>
  );
}

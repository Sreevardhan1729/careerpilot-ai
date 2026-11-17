"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth/auth-context";
import { api } from "@/lib/endpoints";
import { DEFAULT_TIMEZONE } from "@/lib/env";

export const meQueryKey = ["me"] as const;

export function useMe() {
  const { status } = useAuth();
  return useQuery({ queryKey: meQueryKey, queryFn: api.me, enabled: status === "authenticated", staleTime: 60_000 });
}

/** The user's display timezone from /me (default Asia/Kolkata). */
export function useTimezone(): string {
  const me = useMe();
  return me.data?.timezone || DEFAULT_TIMEZONE;
}

export function useGoogleConnected(): boolean {
  const me = useMe();
  const google = me.data?.integrations?.google as { connected?: boolean } | undefined;
  return Boolean(google?.connected);
}

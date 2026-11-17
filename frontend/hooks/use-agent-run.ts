"use client";

import { useQuery, type Query } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { isApiError } from "@/lib/api";
import { isPausedStatus, isTerminalStatus, pollInterval } from "@/lib/agent-run";
import { api } from "@/lib/endpoints";
import type { AgentRunOut } from "@/types/models";

export const agentRunKey = (id: string) => ["agent-run", id] as const;

export interface UseAgentRunOptions {
  /** Called once when the run reaches a terminal status or pauses for approval. */
  onSettled?: (run: AgentRunOut) => void;
}

/**
 * Polls GET /agent-runs/{id} every 2 s until the run is terminal (completed | partially_completed | failed | cancelled),
 * backing off to 5 s after 2 minutes. `awaiting_approval` stops polling (the caller shows the approval UI).
 */
export function useAgentRun(id: string | null | undefined, options: UseAgentRunOptions = {}) {
  // When polling of this run started; restarts when a different run is watched or after Retry.
  const watching = useRef<{ id: string | null | undefined; since: number } | null>(null);

  const query = useQuery({
    queryKey: agentRunKey(id ?? "none"),
    queryFn: ({ signal }) => api.runs.get(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: (q: Query<AgentRunOut>) => {
      if (q.state.status === "error") return false;
      const now = Date.now();
      if (!watching.current || watching.current.id !== id) watching.current = { id, since: now };
      return pollInterval(q.state.data?.status, watching.current.since, now);
    },
    refetchIntervalInBackground: true,
    retry: (count, error) => !(isApiError(error) && error.status < 500 && error.status !== 0) && count < 3,
  });

  const settledFor = useRef<string | null>(null);
  const onSettled = options.onSettled;
  const status = query.data?.status;
  useEffect(() => {
    if (!query.data || !status) return;
    const key = `${query.data.id}:${status}`;
    if ((isTerminalStatus(status) || isPausedStatus(status)) && settledFor.current !== key) {
      settledFor.current = key;
      onSettled?.(query.data);
    }
  }, [query.data, status, onSettled]);

  return {
    ...query,
    run: query.data,
    isTerminal: isTerminalStatus(status),
    isPaused: isPausedStatus(status),
    restartPolling: () => {
      watching.current = { id, since: Date.now() };
      settledFor.current = null;
      void query.refetch();
    },
  };
}

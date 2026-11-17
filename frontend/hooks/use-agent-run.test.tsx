import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { configureApi } from "@/lib/api";
import { useAgentRun } from "./use-agent-run";

function run(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    workflow_name: "job_extraction",
    status,
    current_node: null,
    progress: [],
    subject: { type: "job", id: "job-1" },
    output: null,
    error: null,
    approval: null,
    children: [],
    created_at: "2026-11-17T02:30:00Z",
    started_at: null,
    completed_at: null,
    ...extra,
  };
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return Wrapper;
}

describe("useAgentRun", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fetchMock.mockReset();
    configureApi({ baseUrl: "http://api.test/api/v1", fetch: fetchMock as unknown as typeof fetch, getToken: () => "t" });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  const respond = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

  it("polls until the run is terminal and calls onSettled once", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(run("queued")))
      .mockResolvedValueOnce(respond(run("running")))
      .mockResolvedValue(respond(run("completed")));
    const onSettled = vi.fn();
    const { result } = renderHook(() => useAgentRun("run-1", { onSettled }), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.run?.status).toBe("queued"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => expect(result.current.run?.status).toBe("running"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    await waitFor(() => expect(result.current.isTerminal).toBe(true));
    const calls = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchMock.mock.calls.length).toBe(calls); // stopped polling
    expect(onSettled).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/agent-runs/run-1");
  });

  it("stops polling when the run pauses for approval", async () => {
    fetchMock.mockResolvedValue(respond(run("awaiting_approval", { approval: { approval_id: "a1", payload_hash: "sha256:x", payload_preview: {} } })));
    const onSettled = vi.fn();
    const { result } = renderHook(() => useAgentRun("run-1", { onSettled }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isPaused).toBe(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.isTerminal).toBe(false);
    expect(onSettled).toHaveBeenCalledTimes(1);
  });

  it("does nothing without an id", () => {
    const { result } = renderHook(() => useAgentRun(null), { wrapper: wrapper() });
    expect(result.current.run).toBeUndefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

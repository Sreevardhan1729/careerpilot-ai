"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";
import { isApiError } from "@/lib/api";
import { AuthProvider } from "@/lib/auth/auth-context";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        // Don't retry client errors (4xx) — they won't change on retry.
        retry: (failureCount, error) => {
          if (isApiError(error) && !error.isTransient) return false;
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
      <Toaster richColors closeButton position="top-right" />
    </QueryClientProvider>
  );
}

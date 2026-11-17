"use client";

import { AlertTriangleIcon, InboxIcon, Loader2Icon, RotateCwIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage, isApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function LoadingState({ label = "Loading…", rows = 3, className }: { label?: string; rows?: number; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={cn("space-y-3", className)}>
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" aria-hidden="true" />
        {label}
      </span>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = "Couldn't load this",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const requestId = isApiError(error) ? error.requestId : null;
  return (
    <Alert variant="destructive" className={className}>
      <AlertTriangleIcon aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <p>{errorMessage(error)}</p>
        {requestId && <p className="mt-1 text-xs opacity-80">Request ID: {requestId}</p>}
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-3 bg-white" onClick={onRetry}>
            <RotateCwIcon aria-hidden="true" />
            Retry
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center", className)}>
      <div className="text-muted-foreground" aria-hidden="true">
        {icon ?? <InboxIcon className="size-8" />}
      </div>
      <p className="font-medium">{title}</p>
      {description && <div className="max-w-md text-sm text-muted-foreground">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Renders loading / error (with retry) / children for a TanStack query. */
export function QueryView<T>({
  query,
  loadingLabel,
  errorTitle,
  children,
}: {
  query: { data: T | undefined; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  loadingLabel?: string;
  errorTitle?: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <LoadingState label={loadingLabel} />;
  if (query.isError || query.data === undefined)
    return <ErrorState error={query.error} title={errorTitle} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}

export function NotAvailable({ feature, endpoint }: { feature: string; endpoint: string }) {
  return (
    <Alert variant="info">
      <AlertTitle>{feature} isn&apos;t available on this server yet</AlertTitle>
      <AlertDescription>
        The backend doesn&apos;t expose <code className="rounded bg-white/70 px-1">{endpoint}</code> yet, so these actions are
        hidden. They appear automatically once the API provides them (run <code className="rounded bg-white/70 px-1">pnpm gen:api</code>).
      </AlertDescription>
    </Alert>
  );
}

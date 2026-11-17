"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellIcon, CheckIcon } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { ErrorState, LoadingState } from "@/components/query-state";
import { Time } from "@/components/time";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { errorMessage } from "@/lib/api";
import { hasEndpoint } from "@/lib/capabilities";
import { api } from "@/lib/endpoints";
import { cn } from "@/lib/utils";

/** Only in-app relative links are followed from notifications. */
function internalLink(link: string | null | undefined): string | null {
  if (!link || !link.startsWith("/") || link.startsWith("//")) return null;
  return link;
}

export function NotificationsBell() {
  const qc = useQueryClient();
  const enabled = hasEndpoint("GET", "/notifications");
  const query = useQuery({ queryKey: ["notifications"], queryFn: () => api.notifications.list(), enabled, refetchInterval: 60_000 });
  const markRead = useMutation({
    mutationFn: (id: string) => api.notifications.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!enabled) return null;

  const items = query.data ?? [];
  const unread = items.filter((n) => !n.read_at).length;
  const canMark = hasEndpoint("POST", "/notifications/{}/read");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
          <BellIcon aria-hidden="true" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white" aria-hidden="true">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="border-b px-4 py-3">
          <h2 className="font-semibold">Notifications</h2>
        </div>
        <div className="max-h-96 overflow-y-auto p-2">
          {query.isPending ? (
            <LoadingState rows={2} />
          ) : query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : items.length === 0 ? (
            <p className="p-4 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            <ul className="space-y-1">
              {items.map((n) => {
                const href = internalLink(n.link);
                return (
                  <li key={n.id} className={cn("rounded-md p-3 text-sm", !n.read_at && "bg-accent")}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium">
                          {!n.read_at && <span className="sr-only">Unread: </span>}
                          {href ? (
                            <Link href={href} className="hover:underline">
                              {n.title}
                            </Link>
                          ) : (
                            n.title
                          )}
                        </p>
                        {n.body && <p className="mt-0.5 whitespace-pre-wrap text-muted-foreground">{n.body}</p>}
                        <p className="mt-1 text-xs text-muted-foreground">
                          <Time value={n.created_at} />
                        </p>
                      </div>
                      {!n.read_at && canMark && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => markRead.mutate(n.id)}
                          disabled={markRead.isPending && markRead.variables === n.id}
                          aria-label={`Mark "${n.title}" as read`}
                        >
                          <CheckIcon aria-hidden="true" />
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

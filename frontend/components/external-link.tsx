import { ExternalLinkIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn, hostOf, safeHref } from "@/lib/utils";

/** Links to untrusted URLs: http(s) only, new tab, no referrer/opener. Falls back to plain text. */
export function ExternalLink({ href, children, className }: { href: string | null | undefined; children?: ReactNode; className?: string }) {
  const safe = safeHref(href);
  const text = children ?? hostOf(href) ?? href ?? "link";
  if (!safe) return <span className={className}>{text}</span>;
  return (
    <a
      href={safe}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={cn("inline-flex items-center gap-1 break-all text-primary underline-offset-2 hover:underline", className)}
    >
      {text}
      <ExternalLinkIcon className="size-3 shrink-0" aria-hidden="true" />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

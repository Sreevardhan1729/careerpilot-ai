"use client";

import { FileSearchIcon } from "lucide-react";
import type { ReactNode } from "react";
import { ExternalLink } from "@/components/external-link";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { ProvenanceKind } from "@/lib/provenance";
import { cn, formatPercent } from "@/lib/utils";

export interface EvidenceEntry {
  text: string | null | undefined;
  sourceUrl?: string | null;
  sourceTitle?: string | null;
  meta?: ReactNode;
}

/**
 * Shows the evidence behind an extracted value: the quoted text (rendered as plain text), whether it was verified
 * against the source, confidence, and source links.
 */
export function EvidencePopover({
  label,
  evidence,
  verified,
  kind,
  confidence,
  triggerLabel,
  className,
  children,
}: {
  /** What the evidence supports, e.g. "Python (mandatory)". Used for the accessible trigger name. */
  label: string;
  evidence: EvidenceEntry[];
  verified?: boolean | null;
  kind?: ProvenanceKind;
  confidence?: number | null;
  triggerLabel?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  const entries = evidence.filter((e) => e.text || e.sourceUrl);
  const provenance: ProvenanceKind | undefined = kind ?? (verified === false ? "unverified" : verified ? "explicit" : undefined);
  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex items-center gap-1 rounded-md text-xs text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring",
          className,
        )}
        aria-label={`Show evidence for ${label}`}
      >
        {children ?? (
          <>
            <FileSearchIcon className="size-3.5" aria-hidden="true" />
            {triggerLabel ?? "Evidence"}
          </>
        )}
      </PopoverTrigger>
      <PopoverContent aria-label={`Evidence for ${label}`}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{label}</p>
            {provenance && (
              <ProvenanceBadge kind={provenance} label={verified === true ? "Verified in source" : verified === false ? "Not verified" : undefined} />
            )}
            {confidence != null && <span className="text-xs text-muted-foreground">Confidence {formatPercent(confidence)}</span>}
          </div>
          {entries.length === 0 ? (
            <p className="text-muted-foreground">No supporting text was found in the source.</p>
          ) : (
            <ul className="space-y-2">
              {entries.map((e, i) => (
                <li key={i} className="space-y-1">
                  {e.text && (
                    <blockquote className="whitespace-pre-wrap border-l-2 border-primary/40 pl-2 text-sm italic text-foreground">
                      {e.text}
                    </blockquote>
                  )}
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {e.sourceUrl && <ExternalLink href={e.sourceUrl}>{e.sourceTitle || undefined}</ExternalLink>}
                    {e.meta}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

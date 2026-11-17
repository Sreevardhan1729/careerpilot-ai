import * as React from "react";
import { cn } from "@/lib/utils";
import { Label } from "./label";

/** Label + control + optional hint/error, wired with aria-describedby. */
export function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
  required,
}: {
  id: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string | null;
  className?: string;
  required?: boolean;
  children: React.ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean; required?: boolean }>;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control = React.cloneElement(children, {
    id,
    "aria-describedby": describedBy,
    "aria-invalid": error ? true : undefined,
    required,
  });
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id}>
        {label}
        {required && (
          <span className="ml-0.5 text-destructive" aria-hidden="true">
            *
          </span>
        )}
      </Label>
      {control}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

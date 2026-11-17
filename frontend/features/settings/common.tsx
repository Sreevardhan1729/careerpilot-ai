"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { titleCase } from "@/lib/utils";

export const joinList = (xs: string[] | null | undefined) => (xs ?? []).join(", ");
export const parseList = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

export function numOrNull(s: string): number | null {
  if (!s.trim()) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function CheckboxSet({
  legend,
  name,
  options,
  value,
  onChange,
  disabled,
}: {
  legend: string;
  name: string;
  options: readonly string[];
  value: string[];
  onChange: (v: string[]) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {options.map((o) => {
          const id = `${name}-${o}`;
          return (
            <div key={o} className="flex items-center gap-1.5">
              <Checkbox
                id={id}
                disabled={disabled}
                checked={value.includes(o)}
                onCheckedChange={(c) => onChange(c === true ? [...value, o] : value.filter((v) => v !== o))}
              />
              <Label htmlFor={id} className="font-normal">
                {titleCase(o)}
              </Label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

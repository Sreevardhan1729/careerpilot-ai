import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-lg border px-4 py-3 text-sm [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-3.5 [&>svg]:size-4 [&>svg~*]:pl-7", {
  variants: {
    variant: {
      default: "bg-card text-card-foreground",
      destructive: "border-red-300 bg-red-50 text-red-900 [&>svg]:text-red-700",
      warning: "border-amber-300 bg-amber-50 text-amber-950 [&>svg]:text-amber-700",
      info: "border-sky-300 bg-sky-50 text-sky-950 [&>svg]:text-sky-700",
      success: "border-emerald-300 bg-emerald-50 text-emerald-950 [&>svg]:text-emerald-700",
    },
  },
  defaultVariants: { variant: "default" },
});

function Alert({ className, variant, ...props }: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div data-slot="alert" role={variant === "destructive" ? "alert" : "status"} className={cn(alertVariants({ variant }), className)} {...props} />;
}

/** Bold lead-in text (not a heading, so it never breaks the page's heading order). */
function AlertTitle({ className, ...props }: React.ComponentProps<"p">) {
  return <p data-slot="alert-title" className={cn("mb-1 font-semibold leading-tight", className)} {...props} />;
}

function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="alert-description" className={cn("text-sm [&_p]:leading-relaxed", className)} {...props} />;
}

export { Alert, AlertDescription, AlertTitle };

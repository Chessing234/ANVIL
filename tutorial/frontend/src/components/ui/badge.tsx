import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default: "border-transparent bg-slate-800 text-slate-100",
        success: "border-transparent bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
        warning: "border-transparent bg-amber-500/20 text-amber-200 border-amber-500/30",
        critical: "border-transparent bg-rose-500/20 text-rose-200 border-rose-500/30",
        info: "border-transparent bg-blue-500/20 text-blue-200 border-blue-500/30",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

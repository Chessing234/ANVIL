import { GraduationCap } from "lucide-react";

import { cn } from "@/lib/utils";

export interface CSTABadgeProps {
  code: string;
  className?: string;
}

/** CSTA K-12 CS Standards reference chip (display-only). */
export function CSTABadge({ code, className }: CSTABadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-100",
        className,
      )}
      title={`CSTA standard ${code}`}
    >
      <GraduationCap className="h-3 w-3" />
      {code}
    </span>
  );
}

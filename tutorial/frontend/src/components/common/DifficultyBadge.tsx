import { cn } from "@/lib/utils";
import type { DifficultyLevel } from "@/types/education";

const styles: Record<DifficultyLevel, string> = {
  Beginner: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
  Intermediate: "border-amber-500/40 bg-amber-500/15 text-amber-100",
  Advanced: "border-rose-500/40 bg-rose-500/15 text-rose-100",
};

export interface DifficultyBadgeProps {
  level: DifficultyLevel;
  className?: string;
}

export function DifficultyBadge({ level, className }: DifficultyBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide",
        styles[level],
        className,
      )}
    >
      {level}
    </span>
  );
}

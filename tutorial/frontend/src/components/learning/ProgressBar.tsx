import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

export interface ProgressBarProps {
  value: number;
  label?: string;
  className?: string;
}

export function ProgressBar({ value, label, className }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between text-xs text-indigo-100/80">
        <span>{label ?? "Lesson progress"}</span>
        <span className="font-mono text-indigo-50">{pct.toFixed(0)}%</span>
      </div>
      <Progress value={pct} className="h-2 bg-indigo-950/80 [&>div]:bg-gradient-to-r [&>div]:from-indigo-500 [&>div]:to-fuchsia-500" />
    </div>
  );
}

import { cn } from "@/lib/utils";

export interface ConceptTagProps {
  label: string;
  className?: string;
}

export function ConceptTag({ label, className }: ConceptTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-100",
        className,
      )}
    >
      {label}
    </span>
  );
}

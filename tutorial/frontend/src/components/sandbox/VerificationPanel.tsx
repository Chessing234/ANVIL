import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type VerificationState = "idle" | "running" | "passed" | "failed";

export interface VerificationPanelProps {
  state: VerificationState;
  message: string;
  hashHint?: string;
}

export function VerificationPanel({ state, message, hashHint }: VerificationPanelProps) {
  const icon =
    state === "running" ? (
      <Loader2 className="h-5 w-5 animate-spin text-amber-300" />
    ) : state === "passed" ? (
      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
    ) : state === "failed" ? (
      <XCircle className="h-5 w-5 text-rose-400" />
    ) : (
      <Loader2 className="h-5 w-5 text-indigo-300/50" />
    );

  return (
    <Card
      className={cn(
        "border-indigo-800/60",
        state === "passed" && "border-emerald-500/40 bg-emerald-950/30",
        state === "failed" && "border-rose-500/40 bg-rose-950/30",
      )}
    >
      <CardHeader className="flex flex-row items-center gap-2 pb-2">
        {icon}
        <CardTitle className="text-base text-indigo-50">Verification</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-indigo-100/90">
        <p>{message}</p>
        {hashHint ? <p className="font-mono text-xs text-indigo-300/80">{hashHint}</p> : null}
      </CardContent>
    </Card>
  );
}

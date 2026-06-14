import { format } from "date-fns";
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { InvestigationStepRow } from "@/types";

export interface SelfCorrectionLogProps {
  steps: InvestigationStepRow[];
}

export function SelfCorrectionLog({ steps }: SelfCorrectionLogProps) {
  const items = steps.filter((s) => s.is_self_correction);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-amber-200">
          <AlertTriangle className="h-5 w-5" />
          Self-correction log
        </CardTitle>
        <p className="text-sm text-slate-400">Explainable adjustments surfaced for analyst review.</p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[260px] pr-3">
          {items.length === 0 ? (
            <p className="text-sm text-slate-500">No self-corrections recorded.</p>
          ) : (
            <ul className="space-y-3">
              {items.map((s) => (
                <li key={s.id} className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-amber-100/90">
                    <Badge variant="warning">{s.agent_name}</Badge>
                    <span className="text-slate-500">{format(new Date(s.timestamp), "PPpp")}</span>
                  </div>
                  <Separator className="my-2 bg-amber-500/20" />
                  <p className="text-sm text-slate-100">{s.correction_reason ?? "No reason captured."}</p>
                  <p className="mt-2 text-xs text-slate-400">Action: {s.action_taken}</p>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

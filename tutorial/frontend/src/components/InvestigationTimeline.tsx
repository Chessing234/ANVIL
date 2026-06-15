import { format } from "date-fns";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { Fragment, useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { InvestigationStepRow, TimelineNode, TimelineNodeStatus } from "@/types";

export interface InvestigationTimelineProps {
  steps: InvestigationStepRow[];
  onSelectStep?: (step: InvestigationStepRow) => void;
}

function inferStatus(index: number, total: number, tool: string): TimelineNodeStatus {
  if (tool.toLowerCase().includes("error")) return "error";
  if (index === total - 1) return "active";
  return "completed";
}

function mapStepsToNodes(steps: InvestigationStepRow[]): TimelineNode[] {
  const synthetic: TimelineNode = {
    id: "start",
    title: "START",
    subtitle: "Incident ingested",
    timestamp: steps[0]?.timestamp ?? null,
    status: "completed",
    isSelfCorrection: false,
  };
  const mapped = steps.map((s, idx) => ({
    id: s.id,
    title: s.action_taken.slice(0, 40) + (s.action_taken.length > 40 ? "…" : ""),
    subtitle: `${s.agent_name} · ${s.tool_used || "tool"}`,
    timestamp: s.timestamp,
    status: inferStatus(idx, steps.length, s.tool_used),
    isSelfCorrection: s.is_self_correction,
    correctionReason: s.correction_reason ?? undefined,
  }));
  return [synthetic, ...mapped];
}

const iconFor = (node: TimelineNode) => {
  if (node.isSelfCorrection) return AlertTriangle;
  if (node.status === "error") return ShieldAlert;
  if (node.status === "completed") return CheckCircle2;
  if (node.status === "active") return Loader2;
  return Circle;
};

export function InvestigationTimeline({ steps, onSelectStep }: InvestigationTimelineProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const nodes = useMemo(() => mapStepsToNodes(steps), [steps]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Investigation timeline</CardTitle>
        <p className="text-sm text-slate-400">
          Flow from intake through agent actions. Self-corrections use amber emphasis for clarity.
        </p>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto pb-2">
          <div className="flex min-w-[640px] items-center gap-1">
            {nodes.map((node, idx) => {
              const Icon = iconFor(node);
              const active = selectedId === node.id;
              return (
                <Fragment key={node.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(node.id);
                      const match = steps.find((s) => s.id === node.id);
                      if (match) onSelectStep?.(match);
                    }}
                    className={cn(
                      "flex min-w-[140px] max-w-[180px] flex-col items-center rounded-lg border px-3 py-4 text-center transition-colors",
                      node.isSelfCorrection
                        ? "border-amber-500/70 bg-amber-500/10 shadow-[0_0_0_1px_rgba(245,158,11,0.2)]"
                        : "border-slate-800 bg-slate-900/50 hover:border-slate-600",
                      active && "ring-2 ring-emerald-500/50",
                    )}
                  >
                    <div
                      className={cn(
                        "mb-2 flex h-10 w-10 items-center justify-center rounded-full border",
                        node.isSelfCorrection ? "border-amber-400 text-amber-300" : "border-slate-700 text-slate-200",
                      )}
                    >
                      <Icon className={cn("h-5 w-5", node.status === "active" && "animate-spin")} />
                    </div>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{node.title}</div>
                    <div className="mt-1 line-clamp-2 text-[10px] text-slate-500">{node.subtitle}</div>
                    {node.timestamp ? (
                      <div className="mt-2 text-[10px] text-slate-600">
                        {format(new Date(node.timestamp), "HH:mm:ss")}
                      </div>
                    ) : null}
                    {node.isSelfCorrection ? (
                      <Badge variant="warning" className="mt-2 text-[10px]">
                        Self-correction
                      </Badge>
                    ) : null}
                    {node.isSelfCorrection && node.correctionReason ? (
                      <p className="mt-1 line-clamp-3 text-[10px] text-amber-100/90" title={node.correctionReason}>
                        {node.correctionReason}
                      </p>
                    ) : null}
                  </button>
                  {idx < nodes.length - 1 ? (
                    <div className="flex h-10 w-6 shrink-0 items-center justify-center text-slate-600">
                      <ArrowRight className="h-4 w-4" />
                    </div>
                  ) : null}
                </Fragment>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

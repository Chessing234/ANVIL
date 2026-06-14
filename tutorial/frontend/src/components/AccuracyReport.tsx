import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export interface AccuracyReportProps {
  report: Record<string, unknown> | null;
}

type Rating = "HIGH" | "MEDIUM" | "LOW";

function pickRating(confidence: number, corrections: number): Rating {
  if (confidence >= 0.75 && corrections <= 1) return "HIGH";
  if (confidence >= 0.5) return "MEDIUM";
  return "LOW";
}

export function AccuracyReport({ report }: AccuracyReportProps) {
  const parsed = useMemo(() => {
    if (!report) {
      return {
        steps: 0,
        meanConfidence: 0,
        corrections: 0,
        meanExec: 0,
        raw: null as Record<string, unknown> | null,
      };
    }
    const inner = (report.accuracy_report as Record<string, unknown> | undefined) ?? report;
    const steps = Number(inner.steps ?? inner["steps"] ?? 0);
    const meanConfidence = Number(inner.mean_confidence ?? inner["mean_confidence"] ?? 0);
    const corrections = Number(inner.self_corrections ?? inner["self_corrections"] ?? 0);
    const meanExec = Number(inner.mean_execution_ms ?? inner["mean_execution_ms"] ?? 0);
    return { steps, meanConfidence, corrections, meanExec, raw: inner };
  }, [report]);

  const rating = pickRating(parsed.meanConfidence, parsed.corrections);
  const badgeVariant = rating === "HIGH" ? "success" : rating === "MEDIUM" ? "warning" : "critical";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            FIND EVIL! accuracy
          </CardTitle>
          <p className="text-sm text-slate-400">Heuristic scoring derived from investigation telemetry.</p>
        </div>
        <Badge variant={badgeVariant} className="text-sm">
          {rating}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-5">
        {!report ? (
          <p className="text-sm text-slate-500">No accuracy bundle stored for this incident yet.</p>
        ) : (
          <>
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Steps completed</span>
                <span>{parsed.steps}</span>
              </div>
              <Progress value={Math.min(100, parsed.steps * 10)} />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Mean confidence</span>
                <span>{(parsed.meanConfidence * 100).toFixed(1)}%</span>
              </div>
              <Progress value={Math.min(100, parsed.meanConfidence * 100)} />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Self-corrections</span>
                <span>{parsed.corrections}</span>
              </div>
              <Progress value={Math.min(100, parsed.corrections * 20)} />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Mean execution latency</span>
                <span>{parsed.meanExec.toFixed(1)} ms</span>
              </div>
              <Progress value={Math.min(100, parsed.meanExec / 50)} />
            </div>
            <Separator />
            <Tabs defaultValue="summary" className="w-full">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="trace">Execution trace</TabsTrigger>
                <TabsTrigger value="tools">Tool usage</TabsTrigger>
                <TabsTrigger value="corrections">Self-corrections</TabsTrigger>
              </TabsList>
              <TabsContent value="summary">
                <p className="text-sm text-slate-400">
                  Confidence blends agent interpretation scores. Self-corrections are weighted heavier in MEDIUM/LOW
                  ratings.
                </p>
              </TabsContent>
              <TabsContent value="trace">
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border border-slate-800 bg-slate-950 p-3 text-[11px] text-slate-400">
                  {JSON.stringify(parsed.raw, null, 2)}
                </pre>
              </TabsContent>
              <TabsContent value="tools">
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border border-slate-800 bg-slate-950 p-3 text-[11px] text-slate-400">
                  {JSON.stringify(parsed.raw?.tool_usage ?? parsed.raw?.tools ?? report.tool_usage ?? {}, null, 2)}
                </pre>
              </TabsContent>
              <TabsContent value="corrections">
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border border-slate-800 bg-slate-950 p-3 text-[11px] text-slate-400">
                  {JSON.stringify(parsed.raw?.self_correction_details ?? parsed.raw?.corrections ?? {}, null, 2)}
                </pre>
              </TabsContent>
            </Tabs>
          </>
        )}
      </CardContent>
    </Card>
  );
}

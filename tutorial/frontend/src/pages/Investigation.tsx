import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import * as incidentsApi from "@/api/incidents";
import { wsClient } from "@/api/websocket";
import { AccuracyReport } from "@/components/AccuracyReport";
import { EvidencePanel } from "@/components/EvidencePanel";
import { IncidentDetail } from "@/components/IncidentDetail";
import { InvestigationTimeline } from "@/components/InvestigationTimeline";
import { SelfCorrectionLog } from "@/components/SelfCorrectionLog";
import { Terminal } from "@/components/Terminal";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { IncidentDetailResponse, InvestigationStepRow, WsEnvelope } from "@/types";

function incidentFromPayload(data: Record<string, unknown>): string | undefined {
  const v = data["incident_id"];
  return typeof v === "string" ? v : undefined;
}

export function Investigation() {
  const { incidentId } = useParams<{ incidentId: string }>();
  const id = incidentId ?? "";

  const [detail, setDetail] = useState<IncidentDetailResponse | null>(null);
  const [accuracy, setAccuracy] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>(["[soc] awaiting investigation stream…"]);
  const [selectedStep, setSelectedStep] = useState<InvestigationStepRow | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const d = await incidentsApi.getIncident(id);
      setDetail(d);
      const acc = await incidentsApi.getAccuracyReport(id).catch(() => null);
      setAccuracy(acc);
      const rebuilt = d.investigation_steps.flatMap((s) => {
        const head = `${s.agent_name}@${s.tool_used}> ${s.action_taken}`;
        const body = s.raw_output ? `${s.raw_output}` : "";
        return body ? [head, body] : [head];
      });
      setLines(rebuilt.length ? rebuilt : ["[soc] no agent output yet — waiting for coordinator…"]);
      const last = d.investigation_steps[d.investigation_steps.length - 1];
      setSelectedStep(last ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load investigation");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!id) return undefined;
    const off = wsClient.subscribe("*", (msg: WsEnvelope) => {
      const match = incidentFromPayload(msg.data);
      if (match === id && (msg.event === "investigation_step" || msg.event === "incident_update")) {
        setLines((prev) => [...prev.slice(-400), `[ws] ${msg.event} :: ${JSON.stringify(msg.data)}`]);
        void load();
      }
    });
    return off;
  }, [id, load]);

  const headerTitle = useMemo(() => detail?.incident.title ?? "Investigation", [detail]);

  if (!id) {
    return (
      <Alert variant="warning">
        <AlertTitle>Missing incident</AlertTitle>
        <AlertDescription>No incident id supplied in the route.</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Demo surface</p>
          <h1 className="text-2xl font-semibold text-slate-50">{headerTitle}</h1>
          <p className="text-sm text-slate-400">Split-pane investigation cockpit with live bus mirroring.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="info">incident {id}</Badge>
          <Button size="sm" variant="secondary" onClick={() => void load()} disabled={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Investigation unavailable</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{error}</span>
            <Button size="sm" variant="secondary" onClick={() => void load()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {loading && !detail ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : detail ? (
        <div className="grid gap-6 xl:grid-cols-2">
          <div className="space-y-4">
            <InvestigationTimeline steps={detail.investigation_steps} onSelectStep={setSelectedStep} />
            <SelfCorrectionLog steps={detail.investigation_steps} />
          </div>
          <div className="space-y-4">
            <Tabs defaultValue="summary" className="w-full">
              <TabsList className="flex flex-wrap">
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="evidence">Evidence</TabsTrigger>
                <TabsTrigger value="accuracy">Accuracy</TabsTrigger>
              </TabsList>
              <TabsContent value="summary" className="space-y-4">
                <IncidentDetail incident={detail.incident} />
                {selectedStep ? (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Selected step</CardTitle>
                      <p className="text-xs text-slate-500">
                        {selectedStep.agent_name} · {selectedStep.tool_used}
                      </p>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm text-slate-200">
                      <div className="flex flex-wrap gap-2 text-xs">
                        <Badge variant="default">
                          confidence{" "}
                          {(selectedStep.confidence <= 1 ? selectedStep.confidence * 100 : selectedStep.confidence).toFixed(0)}%
                        </Badge>
                        <Badge variant={selectedStep.is_self_correction ? "warning" : "info"}>
                          {selectedStep.is_self_correction ? "self-corrected" : "nominal"}
                        </Badge>
                      </div>
                      <Separator />
                      <div>
                        <div className="text-xs uppercase text-slate-500">Interpretation</div>
                        <p>{selectedStep.interpretation}</p>
                      </div>
                      <div>
                        <div className="text-xs uppercase text-slate-500">Raw output</div>
                        <ScrollArea className="mt-1 h-40 rounded-md border border-slate-800 bg-black/40 p-3 font-mono text-xs text-emerald-200">
                          {selectedStep.raw_output}
                        </ScrollArea>
                      </div>
                    </CardContent>
                  </Card>
                ) : null}
              </TabsContent>
              <TabsContent value="evidence">
                <EvidencePanel items={detail.evidence} />
              </TabsContent>
              <TabsContent value="accuracy">
                <AccuracyReport report={accuracy} />
              </TabsContent>
            </Tabs>
            <Terminal lines={lines} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

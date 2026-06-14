import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import * as agentsApi from "@/api/agents";
import * as incidentsApi from "@/api/incidents";
import * as systemApi from "@/api/system";
import { wsClient } from "@/api/websocket";
import type { AgentRow, ChartPoint, IncidentRow, SystemHealth, SystemMetrics, WsEnvelope } from "@/types";

interface SocShellValue {
  metrics: SystemMetrics | null;
  health: SystemHealth | null;
  incidents: IncidentRow[];
  agents: AgentRow[];
  chartPoints: ChartPoint[];
  terminalLines: string[];
  loading: boolean;
  error: string | null;
  wsConnected: boolean;
  refresh: () => Promise<void>;
  pushTerminalLine: (line: string) => void;
}

const SocShellContext = createContext<SocShellValue | null>(null);

export function SocShellProvider({ children }: { children: ReactNode }) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [incidents, setIncidents] = useState<IncidentRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [chartPoints, setChartPoints] = useState<ChartPoint[]>([]);
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "[soc] terminal online — streaming investigation bus…",
  ]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  const pushTerminalLine = useCallback((line: string) => {
    setTerminalLines((prev) => [...prev.slice(-400), `[${new Date().toISOString()}] ${line}`]);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, h, inc, ag] = await Promise.all([
        systemApi.getMetrics(),
        systemApi.getHealth(),
        incidentsApi.listIncidents({ limit: 100 }),
        agentsApi.listAgents(),
      ]);
      setMetrics(m);
      setHealth(h);
      setIncidents(inc);
      setAgents(ag);
      const now = new Date().toISOString();
      setChartPoints((prev) => {
        const next = [...prev, { t: now, count: inc.length }];
        return next.slice(-24);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    wsClient.connect();
    setWsConnected(wsClient.connected);
    const off = wsClient.subscribe("*", (msg: WsEnvelope) => {
      setWsConnected(wsClient.connected);
      pushTerminalLine(`event=${msg.event} topic=${msg.topic}`);
      if (msg.event === "incident_update" || msg.event === "investigation_step" || msg.event === "lesson_generated") {
        void refresh();
      }
    });
    const poll = window.setInterval(() => {
      setWsConnected(wsClient.connected);
    }, 1000);
    return () => {
      window.clearInterval(poll);
      off();
      wsClient.disconnect();
    };
  }, [pushTerminalLine, refresh]);

  const value = useMemo<SocShellValue>(
    () => ({
      metrics,
      health,
      incidents,
      agents,
      chartPoints,
      terminalLines,
      loading,
      error,
      wsConnected,
      refresh,
      pushTerminalLine,
    }),
    [agents, chartPoints, error, health, incidents, loading, metrics, pushTerminalLine, refresh, terminalLines, wsConnected],
  );

  return <SocShellContext.Provider value={value}>{children}</SocShellContext.Provider>;
}

export function useSocShell(): SocShellValue {
  const ctx = useContext(SocShellContext);
  if (!ctx) throw new Error("useSocShell must be used within SocShellProvider");
  return ctx;
}

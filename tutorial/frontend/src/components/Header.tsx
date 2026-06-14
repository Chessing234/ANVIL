import { formatDistanceToNow } from "date-fns";
import { RefreshCw, Shield, Wifi, WifiOff } from "lucide-react";
import { useCallback } from "react";

import { readApiBaseUrl } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useSocShell } from "@/context/soc-shell";

export function Header() {
  const { metrics, health, incidents, agents, refresh, wsConnected } = useSocShell();
  const activeIncidents = incidents.filter((i) => !["resolved", "closed"].includes(i.status.toLowerCase())).length;
  const onlineAgents = agents.filter((a) => a.status.toLowerCase() === "active").length;

  const handleRefresh = useCallback(() => {
    void refresh();
  }, [refresh]);

  const healthOk = health?.status === "ok";

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            {healthOk ? <Wifi className="h-4 w-4 text-emerald-400" /> : <WifiOff className="h-4 w-4 text-amber-400" />}
            <span>Platform</span>
            <Badge variant={healthOk ? "success" : "warning"}>{health?.status ?? "unknown"}</Badge>
            <Badge variant={wsConnected ? "success" : "default"} className="text-[10px]">
              WS {wsConnected ? "live" : "idle"}
            </Badge>
            {health?.timestamp ? (
              <span className="text-xs text-slate-500">
                synced {formatDistanceToNow(new Date(health.timestamp), { addSuffix: true })}
              </span>
            ) : null}
          </div>
          <Separator orientation="vertical" className="hidden h-6 md:block" />
          <div className="flex flex-wrap gap-2 text-xs text-slate-400">
            <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1">
              Active incidents: <strong className="text-slate-100">{activeIncidents}</strong>
            </span>
            <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1">
              Agents online: <strong className="text-slate-100">{onlineAgents}</strong>
            </span>
            <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1">
              Lessons: <strong className="text-slate-100">{metrics?.lessons ?? "—"}</strong>
            </span>
            <span className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1">
              Students: <strong className="text-slate-100">{metrics?.students ?? "—"}</strong>
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleRefresh} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <div className="hidden max-w-xs items-center gap-2 truncate rounded-md border border-slate-800 px-3 py-1.5 text-xs text-slate-400 sm:flex" title={readApiBaseUrl()}>
            <Shield className="h-4 w-4 shrink-0 text-blue-400" />
            <span className="truncate font-mono text-[11px]">{readApiBaseUrl()}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

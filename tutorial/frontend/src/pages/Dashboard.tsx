import { formatDistanceToNow, isToday } from "date-fns";
import type { LucideIcon } from "lucide-react";
import { Activity, BookOpen, Cpu, ShieldAlert } from "lucide-react";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { AgentStatus } from "@/components/AgentStatus";
import { RealTimeChart } from "@/components/RealTimeChart";
import { Terminal } from "@/components/Terminal";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useSocShell } from "@/context/soc-shell";

function KpiCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: LucideIcon;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-slate-300">{title}</CardTitle>
        <Icon className="h-4 w-4 text-emerald-400" />
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold text-slate-50">{value}</div>
        <p className="text-xs text-slate-500">{hint}</p>
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const { metrics, incidents, agents, chartPoints, terminalLines, loading, error, refresh } = useSocShell();
  const navigate = useNavigate();

  const activeIncidents = useMemo(
    () => incidents.filter((i) => !["resolved", "closed"].includes(i.status.toLowerCase())).length,
    [incidents],
  );

  const investigationsToday = useMemo(
    () =>
      incidents.filter((i) => {
        if (!isToday(new Date(i.updated_at))) return false;
        const s = i.status.toLowerCase();
        return ["investigating", "triaging", "contained", "open"].includes(s);
      }).length,
    [incidents],
  );

  const onlineAgents = useMemo(() => agents.filter((a) => a.status.toLowerCase() === "active").length, [agents]);

  const recent = useMemo(() => {
    return [...incidents]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 8);
  }, [incidents]);

  const terminalPreview = useMemo(() => terminalLines.slice(-18), [terminalLines]);

  return (
    <div className="space-y-6">
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Telemetry fetch failed</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{error}</span>
            <Button size="sm" variant="secondary" onClick={() => void refresh()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {loading && !metrics ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-4 w-32" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-20" />
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <KpiCard
              title="Active incidents"
              value={activeIncidents}
              hint="Open pipeline excluding closed states"
              icon={ShieldAlert}
            />
            <KpiCard
              title="Investigations today"
              value={investigationsToday}
              hint="Incidents touched today in active phases"
              icon={Activity}
            />
            <KpiCard title="Agents online" value={onlineAgents} hint="Agents reporting active heartbeats" icon={Cpu} />
            <KpiCard
              title="Lessons generated"
              value={metrics?.lessons ?? 0}
              hint="Generated curriculum artifacts"
              icon={BookOpen}
            />
          </>
        )}
      </div>

      <RealTimeChart data={chartPoints} />

      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Recent incidents</CardTitle>
            <p className="text-sm text-slate-400">Latest updates stream in over WebSocket without full reloads.</p>
          </CardHeader>
          <CardContent>
            {loading && incidents.length === 0 ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recent.map((row, idx) => (
                    <TableRow
                      key={row.id}
                      className={idx % 2 === 0 ? "bg-slate-900/30 hover:bg-slate-900/50" : "hover:bg-slate-900/40"}
                    >
                      <TableCell className="font-medium text-slate-100">{row.title}</TableCell>
                      <TableCell>
                        <Badge variant="info">{row.severity}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="default">{row.status}</Badge>
                      </TableCell>
                      <TableCell className="text-xs text-slate-400">
                        {formatDistanceToNow(new Date(row.updated_at), { addSuffix: true })}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="secondary" onClick={() => navigate(`/investigations/${row.id}`)}>
                          Investigation
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
        <Terminal lines={terminalPreview} />
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-100">Agent mesh</h2>
          <Badge variant="default">Live status</Badge>
        </div>
        <AgentStatus agents={agents} />
      </div>
    </div>
  );
}

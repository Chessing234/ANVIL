import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AgentRow } from "@/types";

export interface AgentStatusProps {
  agents: AgentRow[];
}

function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (s === "active") return "text-emerald-400";
  if (s === "idle") return "text-slate-400";
  if (s === "offline" || s === "paused") return "text-amber-300";
  return "text-rose-400";
}

function spark(agent: AgentRow) {
  const total = Math.max(1, agent.tasks_completed + agent.tasks_failed);
  const rate = agent.tasks_completed / total;
  return Array.from({ length: 10 }).map((_, i) => ({
    i,
    v: Math.max(0.1, rate + Math.sin(i / 2) * 0.08),
  }));
}

export function AgentStatus({ agents }: AgentStatusProps) {
  const sorted = useMemo(() => [...agents].sort((a, b) => a.name.localeCompare(b.name)), [agents]);
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {sorted.map((agent) => (
        <Card key={agent.id}>
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <CardTitle className="text-base">{agent.name}</CardTitle>
                <p className="text-xs uppercase tracking-wide text-slate-500">{agent.agent_type}</p>
              </div>
              <Badge variant="default" className={statusColor(agent.status)}>
                {agent.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
              <div>
                <div className="text-[10px] uppercase text-slate-500">Tasks ok</div>
                <div className="text-sm text-slate-100">{agent.tasks_completed}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500">Failed</div>
                <div className="text-sm text-slate-100">{agent.tasks_failed}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500">Avg ms</div>
                <div className="text-sm text-slate-100">{agent.avg_task_duration_ms.toFixed(0)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500">Uptime s</div>
                <div className="text-sm text-slate-100">{agent.uptime_seconds.toFixed(0)}</div>
              </div>
            </div>
            <div className="h-16 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={spark(agent)}>
                  <defs>
                    <linearGradient id={`g-${agent.id}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#34d399" stopOpacity={0.8} />
                      <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="i" hide />
                  <YAxis hide domain={[0, "auto"]} />
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }}
                    labelStyle={{ display: "none" }}
                    formatter={(value: number) => [`${(value * 100).toFixed(0)}%`, "load"]}
                  />
                  <Area type="monotone" dataKey="v" stroke="#34d399" fill={`url(#g-${agent.id})`} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

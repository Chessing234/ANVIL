import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ChartPoint } from "@/types";

export interface RealTimeChartProps {
  data: ChartPoint[];
  title?: string;
}

export function RealTimeChart({ data, title = "Incidents over recent refreshes" }: RealTimeChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    label: new Date(d.t).toLocaleTimeString(),
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <p className="text-sm text-slate-400">Each point reflects a dashboard refresh / websocket-driven sync.</p>
      </CardHeader>
      <CardContent className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="label" stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 11 }} />
            <YAxis stroke="#64748b" tick={{ fill: "#94a3b8", fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: "#020617", border: "1px solid #1e293b", borderRadius: 8 }}
              labelStyle={{ color: "#e2e8f0" }}
            />
            <Line type="monotone" dataKey="count" stroke="#38bdf8" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

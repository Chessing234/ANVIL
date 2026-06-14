import { Medal } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { LeaderboardRow } from "@/types/education";

export interface LeaderboardProps {
  weekly: LeaderboardRow[];
  monthly: LeaderboardRow[];
}

export function Leaderboard({ weekly, monthly }: LeaderboardProps) {
  const renderRows = (rows: LeaderboardRow[]) => (
    <div className="space-y-2">
      {rows.map((r) => (
        <div
          key={`${r.rank}-${r.handle}`}
          className={cn(
            "flex items-center justify-between rounded-lg border px-3 py-2 text-sm",
            r.isYou ? "border-fuchsia-500/50 bg-fuchsia-950/30" : "border-indigo-800/50 bg-indigo-950/40",
          )}
        >
          <div className="flex items-center gap-3">
            <span className="w-6 font-mono text-indigo-300">#{r.rank}</span>
            <Medal className={cn("h-4 w-4", r.rank <= 3 ? "text-amber-300" : "text-indigo-500")} />
            <span className="font-medium text-indigo-50">{r.handle}</span>
            {r.isYou ? <Badge className="bg-fuchsia-600/40">You</Badge> : null}
          </div>
          <div className="flex gap-3 text-xs text-indigo-200/90">
            <span>{r.xp} XP</span>
            <span>{r.streak}🔥</span>
            <span>{r.lessonsCompleted} L</span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <Card className="border-indigo-800/60 bg-indigo-950/50">
      <CardHeader>
        <CardTitle className="text-lg text-indigo-50">Leaderboards</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="weekly">
          <TabsList>
            <TabsTrigger value="weekly">This week</TabsTrigger>
            <TabsTrigger value="monthly">This month</TabsTrigger>
          </TabsList>
          <TabsContent value="weekly">{renderRows(weekly)}</TabsContent>
          <TabsContent value="monthly">{renderRows(monthly)}</TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

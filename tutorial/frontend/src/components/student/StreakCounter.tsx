import { Flame } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface StreakCounterProps {
  days: number;
}

export function StreakCounter({ days }: StreakCounterProps) {
  return (
    <Card className="border-amber-500/40 bg-gradient-to-br from-amber-950/50 to-orange-950/40">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-lg text-amber-100">
          <Flame className="h-6 w-6 text-orange-400" />
          {days}-day streak
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-amber-100/90">
        <p>Log learning sessions daily to multiply XP bonuses and climb the leaderboard.</p>
      </CardContent>
    </Card>
  );
}

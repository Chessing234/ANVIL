import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { StudentProfile } from "@/types/education";

export interface ProfileCardProps {
  profile: StudentProfile;
}

export function ProfileCard({ profile }: ProfileCardProps) {
  const pct = Math.min(100, Math.round((profile.xp / profile.xpToNext) * 100));
  return (
    <Card className="overflow-hidden border-indigo-700/50 bg-gradient-to-br from-indigo-950 via-slate-950 to-violet-950/80 p-[1px] shadow-lg">
      <div className="rounded-[11px] bg-slate-950/90">
        <CardHeader className="flex flex-row items-start gap-4">
          <div
            className={`h-16 w-16 rounded-2xl bg-gradient-to-br ${profile.avatarGradient} shadow-inner`}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <CardTitle className="text-2xl text-indigo-50">{profile.displayName}</CardTitle>
            <p className="text-sm text-indigo-200/80">
              Level {profile.level} · <span className="text-fuchsia-200">{profile.levelTitle}</span>
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge className="bg-indigo-600/40 text-indigo-50">{profile.lessonsCompleted} lessons</Badge>
              <Badge className="bg-emerald-600/30 text-emerald-100">
                <Sparkles className="mr-1 inline h-3 w-3" />
                {profile.xp} XP
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="h-2 overflow-hidden rounded-full bg-indigo-950">
            <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-xs text-indigo-200/80">
            {profile.xp} / {profile.xpToNext} XP to next level
          </p>
        </CardContent>
      </div>
    </Card>
  );
}

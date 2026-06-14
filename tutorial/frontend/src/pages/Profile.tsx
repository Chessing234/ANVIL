import { Flame, Shield, Star, Terminal, Trophy } from "lucide-react";
import { useMemo } from "react";

import { Link } from "react-router-dom";

import { Leaderboard } from "@/components/student/Leaderboard";
import { ProfileCard } from "@/components/student/ProfileCard";
import { SkillTree } from "@/components/student/SkillTree";
import { StreakCounter } from "@/components/student/StreakCounter";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEFAULT_PROFILE, MONTHLY_BOARD, WEEKLY_BOARD } from "@/data/profileSeed";
import { readStudentXp } from "@/lib/learnStorage";
import type { AchievementDef } from "@/types/education";

function AchievementIcon({ a }: { a: AchievementDef }) {
  const cls = "h-5 w-5";
  switch (a.icon) {
    case "flame":
      return <Flame className={cls} />;
    case "shield":
      return <Shield className={cls} />;
    case "terminal":
      return <Terminal className={cls} />;
    case "trophy":
      return <Trophy className={cls} />;
    default:
      return <Star className={cls} />;
  }
}

export function Profile() {
  const profile = useMemo(() => {
    const xpLive = readStudentXp();
    return { ...DEFAULT_PROFILE, xp: Math.max(DEFAULT_PROFILE.xp, xpLive) };
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-indigo-50">Profile</h1>
        <p className="mt-1 text-indigo-200/85">XP, streaks, achievements, and knowledge graph—optimized for judge demos.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ProfileCard profile={profile} />
        </div>
        <StreakCounter days={profile.streakDays} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="border-indigo-800/60 bg-indigo-950/50">
          <CardHeader>
            <CardTitle className="text-lg text-indigo-50">Achievements</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {profile.achievements.map((a) => (
              <div
                key={a.id}
                className={`flex gap-3 rounded-xl border p-3 ${
                  a.unlocked ? "border-emerald-500/40 bg-emerald-950/30" : "border-slate-800/80 bg-slate-950/60 opacity-60"
                }`}
              >
                <div className="text-indigo-100">
                  <AchievementIcon a={a} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-indigo-50">{a.title}</h3>
                    {a.unlocked ? <Badge className="bg-emerald-600/30 text-emerald-100">Unlocked</Badge> : null}
                  </div>
                  <p className="text-xs text-indigo-200/80">{a.description}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="rounded-xl border border-indigo-800/60 bg-gradient-to-br from-indigo-950/80 to-slate-950 p-4 text-sm text-indigo-100/90">
          <h3 className="text-base font-semibold text-indigo-50">Level ladder</h3>
          <ul className="mt-2 space-y-2 text-indigo-200/90">
            <li>Script Kiddie → 0 XP</li>
            <li>Security Analyst → 2.5k XP</li>
            <li>Incident Responder → 6k XP</li>
            <li>Threat Hunter → 12k XP</li>
            <li>CISO → 25k XP (showcase tier)</li>
          </ul>
        </div>
      </div>

      <SkillTree />

      <Leaderboard weekly={WEEKLY_BOARD} monthly={MONTHLY_BOARD} />

      <section className="rounded-xl border border-indigo-800/60 bg-indigo-950/40 p-4 text-sm text-indigo-100/90">
        <p>
          Full wallet with filters lives on{" "}
          <Link className="font-semibold text-fuchsia-300 underline" to="/credentials">
            Credentials
          </Link>
          .
        </p>
      </section>
    </div>
  );
}

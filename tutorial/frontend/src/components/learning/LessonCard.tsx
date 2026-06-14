import { Clock, Star } from "lucide-react";
import { Link } from "react-router-dom";

import { ConceptTag } from "@/components/common/ConceptTag";
import { CSTABadge } from "@/components/common/CSTABadge";
import { DifficultyBadge } from "@/components/common/DifficultyBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { LessonSummary } from "@/types/education";

export interface LessonCardProps {
  lesson: LessonSummary;
}

export function LessonCard({ lesson }: LessonCardProps) {
  const pct = lesson.progressPercent ?? 0;
  return (
    <Card className="group overflow-hidden border-indigo-800/50 bg-gradient-to-b from-indigo-950/80 to-slate-950/90 shadow-lg transition hover:border-indigo-500/40 hover:shadow-indigo-900/20">
      <div className={`h-28 bg-gradient-to-br ${lesson.thumbnailGradient} opacity-90 transition group-hover:opacity-100`} />
      <CardHeader className="space-y-2 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <DifficultyBadge level={lesson.difficulty} />
          {lesson.trending ? <Badge className="bg-rose-500/20 text-rose-100">Trending</Badge> : null}
          {lesson.recommended ? <Badge className="bg-emerald-500/20 text-emerald-100">For you</Badge> : null}
        </div>
        <h3 className="text-lg font-semibold leading-snug text-indigo-50">{lesson.title}</h3>
        <p className="text-sm text-indigo-200/80">{lesson.subtitle}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {lesson.concepts.slice(0, 4).map((c) => (
            <ConceptTag key={c} label={c} />
          ))}
        </div>
        <div className="flex flex-wrap gap-1">
          {lesson.cstaCodes.map((code) => (
            <CSTABadge key={code} code={code} />
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs text-indigo-200/80">
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {lesson.durationMinutes} min
          </span>
          <span className="flex items-center gap-1">
            <Star className="h-3.5 w-3.5 text-amber-300" />
            {lesson.rating.toFixed(1)} ({lesson.enrollCount.toLocaleString()})
          </span>
        </div>
        {pct > 0 && pct < 100 ? (
          <div>
            <div className="mb-1 flex justify-between text-[11px] text-indigo-200/80">
              <span>In progress</span>
              <span>{pct}%</span>
            </div>
            <Progress value={pct} className="h-1.5 bg-indigo-950 [&>div]:bg-indigo-500" />
          </div>
        ) : null}
        {pct >= 100 ? <Badge className="bg-emerald-500/20 text-emerald-100">Completed</Badge> : null}
      </CardContent>
      <CardFooter className="flex justify-between gap-2 border-t border-indigo-900/60 pt-4">
        <Button asChild variant="secondary" size="sm">
          <Link to={`/learn/${lesson.id}`}>{pct > 0 && pct < 100 ? "Continue" : "Open"}</Link>
        </Button>
        <Button asChild size="sm" className="bg-indigo-600 hover:bg-indigo-500">
          <Link to={`/learn/${lesson.id}`}>Play</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

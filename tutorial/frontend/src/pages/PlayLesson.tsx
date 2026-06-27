import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import * as lessonsApi from "@/api/lessons";
import { LessonPlayer } from "@/components/learning/LessonPlayer";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getLessonDefinition } from "@/data/educationCatalog";
import { apiLessonToDefinition, isApiLessonId } from "@/lib/apiLessonAdapter";
import { readStudentXp, writeStudentXp } from "@/lib/learnStorage";
import type { LessonDefinition } from "@/types/education";

export function PlayLesson() {
  const { lessonId } = useParams<{ lessonId: string }>();
  const [def, setDef] = useState<LessonDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const staticDef = useMemo(
    () => (lessonId && !isApiLessonId(lessonId) ? getLessonDefinition(lessonId) : null),
    [lessonId],
  );

  useEffect(() => {
    if (!lessonId) {
      setLoading(false);
      return;
    }
    if (!isApiLessonId(lessonId)) {
      setDef(staticDef);
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const detail = await lessonsApi.getLesson(lessonId);
        if (!cancelled) setDef(apiLessonToDefinition(detail));
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load lesson");
          setDef(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [lessonId, staticDef]);

  if (!lessonId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Missing lesson</AlertTitle>
        <AlertDescription>No lesson id in URL.</AlertDescription>
      </Alert>
    );
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!def) {
    return (
      <Alert>
        <AlertTitle>Lesson not found</AlertTitle>
        <AlertDescription className="flex flex-wrap gap-2">
          <span>{error ?? `We could not load ${lessonId}.`}</span>
          <Button asChild variant="secondary" size="sm">
            <Link to="/learn">Back to catalog</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-indigo-300/80">
            {isApiLessonId(lessonId) ? "Live SOC lesson" : "Active lesson"}
          </p>
          <h1 className="text-2xl font-bold text-indigo-50">{def.title}</h1>
        </div>
        <Button asChild variant="outline" className="border-indigo-700 text-indigo-50">
          <Link to="/learn">Catalog</Link>
        </Button>
      </div>
      <LessonPlayer
        lesson={def}
        onXpEarned={(amount) => {
          const cur = readStudentXp();
          writeStudentXp(cur + amount);
        }}
      />
    </div>
  );
}

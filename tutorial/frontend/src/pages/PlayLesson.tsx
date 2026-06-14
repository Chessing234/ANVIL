import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { LessonPlayer } from "@/components/learning/LessonPlayer";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { getLessonDefinition } from "@/data/educationCatalog";
import { readStudentXp, writeStudentXp } from "@/lib/learnStorage";

export function PlayLesson() {
  const { lessonId } = useParams<{ lessonId: string }>();
  const def = useMemo(() => (lessonId ? getLessonDefinition(lessonId) : null), [lessonId]);

  if (!lessonId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Missing lesson</AlertTitle>
        <AlertDescription>No lesson id in URL.</AlertDescription>
      </Alert>
    );
  }

  if (!def) {
    return (
      <Alert>
        <AlertTitle>Lesson not found</AlertTitle>
        <AlertDescription className="flex flex-wrap gap-2">
          <span>We could not load {lessonId}.</span>
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
          <p className="text-xs uppercase tracking-wide text-indigo-300/80">Active lesson</p>
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

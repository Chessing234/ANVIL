import type { LearnProgressPayload } from "@/types/education";

const PREFIX = "tutorial_learn_progress:";

export function readLessonProgress(lessonId: string): LearnProgressPayload | null {
  try {
    const raw = localStorage.getItem(PREFIX + lessonId);
    if (!raw) return null;
    return JSON.parse(raw) as LearnProgressPayload;
  } catch {
    return null;
  }
}

export function writeLessonProgress(payload: LearnProgressPayload): void {
  localStorage.setItem(PREFIX + payload.lessonId, JSON.stringify(payload));
}

export function readStudentXp(): number {
  const v = localStorage.getItem("tutorial_student_xp");
  return v ? Number(v) : 2400;
}

export function writeStudentXp(xp: number): void {
  localStorage.setItem("tutorial_student_xp", String(Math.max(0, Math.floor(xp))));
}

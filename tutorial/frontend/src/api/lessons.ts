import { api } from "@/api/client";

export interface LessonListItem {
  id: string;
  incident_id: string;
  title: string;
  narrative: string;
  difficulty: string;
  estimated_duration_minutes: number;
  created_at: string;
}

export interface LessonDetailResponse {
  id: string;
  incident_id: string;
  title: string;
  narrative: string;
  interactive_elements: Record<string, unknown>[];
  difficulty: string;
  csta_standards: string[];
  estimated_duration_minutes: number;
  concept_coverage: Record<string, unknown>;
  teaching_effectiveness_score: number | null;
  created_at: string;
  updated_at: string;
}

export async function listLessons(params?: { difficulty?: string }): Promise<LessonListItem[]> {
  const { data } = await api.get<LessonListItem[]>("/lessons/", { params });
  return data;
}

export async function getLesson(lessonId: string): Promise<LessonDetailResponse> {
  const { data } = await api.get<LessonDetailResponse>(`/lessons/${lessonId}`);
  return data;
}

export async function getCurriculumMapping(lessonId: string): Promise<{
  lesson_id: string;
  incident_id: string;
  standards_covered: string[];
  concept_coverage: Record<string, unknown>;
}> {
  const { data } = await api.get(`/lessons/${lessonId}/curriculum-mapping`);
  return data as {
    lesson_id: string;
    incident_id: string;
    standards_covered: string[];
    concept_coverage: Record<string, unknown>;
  };
}

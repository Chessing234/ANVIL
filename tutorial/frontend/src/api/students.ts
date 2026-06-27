import { api } from "@/api/client";

export interface StudentResponse {
  id: string;
  name: string;
  email: string;
  experience_level: string;
  preferred_learning_style: string;
  streak_days: number;
  total_time_minutes: number;
  created_at: string;
  last_active_at: string | null;
}

export interface CredentialEntry {
  credential_id: string;
  student_id: string;
  issued_at: string;
  chain: string;
  verification_hash: string;
  lesson_id?: string | null;
  concept_name?: string | null;
  score?: number | null;
  category?: string | null;
}

export async function getDemoStudent(): Promise<StudentResponse> {
  const { data } = await api.get<StudentResponse>("/students/demo");
  return data;
}

export async function getCredentials(studentId: string): Promise<CredentialEntry[]> {
  const { data } = await api.get<CredentialEntry[]>(`/students/${studentId}/credentials`);
  return data;
}

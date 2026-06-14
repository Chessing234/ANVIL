import { api } from "@/api/client";
import type { IncidentDetailResponse, IncidentRow } from "@/types";

export interface IncidentCreatePayload {
  title: string;
  description: string;
  severity: string;
  status?: string;
  incident_type?: string;
  source_ip?: string | null;
  target_asset?: string | null;
}

export async function listIncidents(params?: {
  status?: string;
  severity?: string;
  limit?: number;
  offset?: number;
}): Promise<IncidentRow[]> {
  const { data } = await api.get<IncidentRow[]>("/incidents/", { params });
  return data;
}

export async function getIncident(id: string): Promise<IncidentDetailResponse> {
  const { data } = await api.get<IncidentDetailResponse>(`/incidents/${id}`);
  return data;
}

export async function createIncident(payload: IncidentCreatePayload): Promise<IncidentRow> {
  const { data } = await api.post<IncidentRow>("/incidents/", payload);
  return data;
}

export async function startInvestigation(incidentId: string): Promise<{ incident_id: string; defense_status: string }> {
  const { data } = await api.post(`/incidents/${incidentId}/investigate`);
  return data as { incident_id: string; defense_status: string };
}

export async function getAccuracyReport(incidentId: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`/incidents/${incidentId}/accuracy-report`);
  return data;
}

export async function uploadEvidence(
  incidentId: string,
  file: File,
  params?: { evidence_type?: string; collected_by?: string },
): Promise<{ evidence_id: string; hash_sha256: string }> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post(`/incidents/${incidentId}/evidence`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    params,
  });
  return data as { evidence_id: string; hash_sha256: string };
}

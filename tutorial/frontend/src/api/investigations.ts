import { api } from "@/api/client";
import type { EvidenceRow, InvestigationStepRow } from "@/types";

export interface CustodyReport {
  incident_id: string;
  chains: Record<string, Record<string, unknown>[]>;
}

export async function getInvestigationSteps(incidentId: string): Promise<InvestigationStepRow[]> {
  const { data } = await api.get<InvestigationStepRow[]>(`/investigations/${incidentId}/steps`);
  return data;
}

export async function getSelfCorrections(incidentId: string): Promise<InvestigationStepRow[]> {
  const { data } = await api.get<InvestigationStepRow[]>(`/investigations/${incidentId}/self-corrections`);
  return data;
}

export async function getEvidence(incidentId: string): Promise<EvidenceRow[]> {
  const { data } = await api.get<EvidenceRow[]>(`/investigations/${incidentId}/evidence`);
  return data;
}

export async function getChainOfCustody(incidentId: string): Promise<CustodyReport> {
  const { data } = await api.get<CustodyReport>(`/investigations/${incidentId}/chain-of-custody`);
  return data;
}

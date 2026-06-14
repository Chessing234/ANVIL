import { api } from "@/api/client";
import type { AgentMetrics, AgentRow } from "@/types";

export async function listAgents(): Promise<AgentRow[]> {
  const { data } = await api.get<AgentRow[]>("/agents/");
  return data;
}

export async function getAgentMetrics(name: string): Promise<AgentMetrics> {
  const { data } = await api.get<AgentMetrics>(`/agents/${encodeURIComponent(name)}/metrics`);
  return data;
}

export async function pauseAgent(name: string): Promise<void> {
  await api.post(`/agents/${encodeURIComponent(name)}/pause`);
}

export async function resumeAgent(name: string): Promise<void> {
  await api.post(`/agents/${encodeURIComponent(name)}/resume`);
}

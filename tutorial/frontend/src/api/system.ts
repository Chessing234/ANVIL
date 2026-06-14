import { api } from "@/api/client";
import type { SystemHealth, SystemMetrics } from "@/types";

export async function getHealth(): Promise<SystemHealth> {
  const { data } = await api.get<SystemHealth>("/system/health", {
    validateStatus: (s) => s === 200 || s === 503,
  });
  return data;
}

export async function getMetrics(): Promise<SystemMetrics> {
  const { data } = await api.get<SystemMetrics>("/system/metrics");
  return data;
}

export async function shutdownSystem(): Promise<void> {
  await api.post("/system/shutdown");
}

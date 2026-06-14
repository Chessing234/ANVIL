/** Shared API + UI types (no `any`). */

export interface ApiErrorBody {
  error: string;
  detail: string;
  timestamp: string;
}

export interface IncidentRow {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  source_ip: string | null;
  target_asset: string | null;
  incident_type: string;
  raw_evidence_refs: unknown[];
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  assigned_agents: unknown[];
  tags: unknown[];
}

export interface InvestigationStepRow {
  id: string;
  incident_id: string;
  agent_name: string;
  action_taken: string;
  tool_used: string;
  raw_output: string;
  interpretation: string;
  confidence: number;
  timestamp: string;
  is_self_correction: boolean;
  correction_reason: string | null;
  execution_time_ms: number;
}

export interface EvidenceRow {
  id: string;
  incident_id: string;
  evidence_type: string;
  file_path: string;
  hash_sha256: string;
  file_size_bytes: number;
  metadata: Record<string, unknown>;
  collected_by: string;
  custody_chain: unknown[];
  storage_location: string;
  created_at: string;
  verified_at: string | null;
}

export interface LessonSummaryRow {
  id: string;
  incident_id: string;
  title: string;
  difficulty: string;
  estimated_duration_minutes: number;
  created_at: string;
}

export interface IncidentDetailResponse {
  incident: IncidentRow;
  investigation_steps: InvestigationStepRow[];
  evidence: EvidenceRow[];
  lessons: LessonSummaryRow[];
}

export interface SystemMetrics {
  incidents: number;
  lessons: number;
  students: number;
  agents: number;
}

export interface SystemHealth {
  status: string;
  database: boolean;
  coordinator_initialized: boolean;
  timestamp: string;
}

export interface AgentRow {
  id: string;
  name: string;
  agent_type: string;
  status: string;
  tasks_completed: number;
  tasks_failed: number;
  avg_task_duration_ms: number;
  uptime_seconds: number;
  last_heartbeat_at: string | null;
}

export interface AgentMetrics {
  name: string;
  tasks_completed: number;
  tasks_failed: number;
  avg_task_duration_ms: number;
  uptime_seconds: number;
  failure_rate: number;
}

export interface WsEnvelope {
  event: string;
  topic: string;
  data: Record<string, unknown>;
}

export type TimelineNodeStatus = "pending" | "active" | "completed" | "error";

export interface TimelineNode {
  id: string;
  title: string;
  subtitle: string;
  timestamp: string | null;
  status: TimelineNodeStatus;
  isSelfCorrection: boolean;
  correctionReason?: string;
}

export interface ChartPoint {
  t: string;
  count: number;
}

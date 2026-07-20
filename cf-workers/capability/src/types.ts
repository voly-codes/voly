export interface Env {
  CAPABILITY_DB: D1Database;
}

export interface RolePayload {
  id: string;
  tier: string;
  mode: string;
  system_prompt: string;
  default_executor?: string;
  provider_offset?: number;
  inject_prior_context?: boolean;
  decomposer_signals?: unknown;
  capability_requirements?: unknown;
}

export interface CapabilityPayload {
  score: number;
  confidence?: number;
  sub_scores?: Record<string, number>;
  strengths?: string[];
  weaknesses?: string[];
}

export interface ProfilePayload {
  executor_id: string;
  kind: string;
  capabilities: Record<string, CapabilityPayload>;
  constraints: Record<string, unknown>;
  operational?: Record<string, number>;
}

export interface CapabilityRow {
  executor_id: string;
  kind: string;
  dimension: string;
  sub_dimension: string;
  score: number;
  confidence: number;
  internal_runs: number;
  successful_runs: number;
  updated_at: number;
}

export interface ConstraintRow {
  executor_id: string;
  constraint_name: string;
  value: string;
}

export interface OperationalRow {
  executor_id: string;
  avg_latency_ms: number;
  completion_rate: number;
  retry_rate: number;
  cost_per_task_usd: number;
  total_runs: number;
  updated_at: number;
}

export interface MatchCandidate {
  executor_id: string;
  score: number;
  routing_score: number;
}

export type AppBindings = { Bindings: Env };

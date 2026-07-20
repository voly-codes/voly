import type { CapabilityRow, ConstraintRow, OperationalRow } from "../types";

export function constraintToText(value: unknown): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "";
  return String(value);
}

export function parseConstraintValue(name: string, raw: string): unknown {
  if (raw === "true") return true;
  if (raw === "false") return false;
  if (name === "context_window" || name === "max_output_tokens") {
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0;
  }
  return raw;
}

export function assembleProfile(
  executorId: string,
  caps: CapabilityRow[],
  constraints: ConstraintRow[],
  operational: OperationalRow | null,
): Record<string, unknown> {
  const kind = caps[0]?.kind ?? "executor";
  const capabilities: Record<string, Record<string, unknown>> = {};
  let totalInternal = 0;
  let totalSuccessful = 0;

  for (const row of caps) {
    if (row.sub_dimension === "") {
      capabilities[row.dimension] = {
        score: row.score,
        confidence: row.confidence,
        sub_scores: {},
        strengths: [],
        weaknesses: [],
      };
      totalInternal += row.internal_runs;
      totalSuccessful += row.successful_runs;
    }
  }

  for (const row of caps) {
    if (row.sub_dimension !== "") {
      const domain = capabilities[row.dimension];
      if (domain) {
        (domain.sub_scores as Record<string, number>)[row.sub_dimension] = row.score;
      }
    }
  }

  const constraintsObj: Record<string, unknown> = {};
  for (const row of constraints) {
    constraintsObj[row.constraint_name] = parseConstraintValue(
      row.constraint_name,
      row.value,
    );
  }

  return {
    id: executorId,
    kind,
    capabilities,
    constraints: constraintsObj,
    evidence: {
      internal_runs: totalInternal,
      successful_runs: totalSuccessful,
      benchmark_sources: [],
    },
    operational: operational
      ? {
          avg_latency_ms: operational.avg_latency_ms,
          completion_rate: operational.completion_rate,
          retry_rate: operational.retry_rate,
          cost_per_task_usd: operational.cost_per_task_usd,
          total_runs: operational.total_runs,
        }
      : {
          avg_latency_ms: 0,
          completion_rate: 1,
          retry_rate: 0,
          cost_per_task_usd: 0,
          total_runs: 0,
        },
  };
}

export function computeRoutingScore(
  capabilityScore: number,
  internalRuns: number,
  successfulRuns: number,
  operational: OperationalRow | null,
): number {
  const historicalSuccess = successfulRuns / Math.max(1, internalRuns);
  const costPerTask = operational?.cost_per_task_usd ?? 0;
  const costEfficiency =
    costPerTask === 0 ? 1 : Math.max(0, 1 - costPerTask);
  const avgLatency = operational?.avg_latency_ms ?? 0;
  const latencyScore = Math.max(0, 1 - avgLatency / 120_000);

  return (
    capabilityScore * 0.4 +
    historicalSuccess * 0.2 +
    1.0 * 0.15 +
    0.5 * 0.1 +
    1.0 * 0.05 +
    costEfficiency * 0.05 +
    latencyScore * 0.05
  );
}

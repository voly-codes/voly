import { Hono } from "hono";
import { computeRoutingScore } from "../db/helpers";
import type {
  AppBindings,
  CapabilityRow,
  MatchCandidate,
  OperationalRow,
} from "../types";

export const matchRoutes = new Hono<AppBindings>();

matchRoutes.post("/", async (c) => {
  try {
    const body = await c.req.json<{
      dimension?: string;
      available_executors?: string[];
      project_stack?: string[];
    }>();

    const dimension = body.dimension?.trim();
    const availableSet = body.available_executors?.length
      ? new Set(body.available_executors.map(String))
      : null;

    let capSql = `
      SELECT * FROM executor_capability
      WHERE sub_dimension = ''
    `;
    const capParams: unknown[] = [];
    if (dimension) {
      capSql += " AND dimension = ?";
      capParams.push(dimension);
    }

    const capRows = await c.env.CAPABILITY_DB.prepare(capSql)
      .bind(...capParams)
      .all<CapabilityRow>();

    const opRows = await c.env.CAPABILITY_DB.prepare(
      `SELECT * FROM executor_operational`,
    ).all<OperationalRow>();

    const operationalById = new Map<string, OperationalRow>();
    for (const row of opRows.results ?? []) {
      operationalById.set(row.executor_id, row);
    }

    const grouped = new Map<string, CapabilityRow[]>();
    for (const row of capRows.results ?? []) {
      if (availableSet && !availableSet.has(row.executor_id)) continue;
      const list = grouped.get(row.executor_id) ?? [];
      list.push(row);
      grouped.set(row.executor_id, list);
    }

    const candidates: MatchCandidate[] = [];

    for (const [executorId, rows] of grouped) {
      const avgScore =
        rows.reduce((sum, r) => sum + r.score, 0) / Math.max(1, rows.length);
      const internalRuns = rows.reduce((sum, r) => sum + r.internal_runs, 0);
      const successfulRuns = rows.reduce((sum, r) => sum + r.successful_runs, 0);
      const operational = operationalById.get(executorId) ?? null;

      candidates.push({
        executor_id: executorId,
        score: avgScore,
        routing_score: computeRoutingScore(
          avgScore,
          internalRuns,
          successfulRuns,
          operational,
        ),
      });
    }

    candidates.sort((a, b) => b.routing_score - a.routing_score);

    const top = candidates.slice(0, 5);
    const rest = candidates.slice(5);

    const recommended = top[0] ?? null;
    const fallbacks = top.slice(1);
    const excluded = rest.map((entry) => ({
      executor_id: entry.executor_id,
      reason: "ranked_below_top_5",
    }));

    return c.json({ recommended, fallbacks, excluded });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

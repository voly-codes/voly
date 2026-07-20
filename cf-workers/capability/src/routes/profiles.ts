import { Hono } from "hono";
import { assembleProfile, constraintToText } from "../db/helpers";
import type {
  AppBindings,
  CapabilityRow,
  ConstraintRow,
  OperationalRow,
  ProfilePayload,
} from "../types";

const EMA_ALPHA = 0.15;
const DEBOUNCE_MS = 300_000;

export const profilesRoutes = new Hono<AppBindings>();

profilesRoutes.post("/seed", async (c) => {
  try {
    const body = await c.req.json<{ profiles?: ProfilePayload[] }>();
    const profiles = body.profiles ?? [];
    let seeded = 0;
    let skipped = 0;
    const now = Date.now();

    for (const profile of profiles) {
      const executorId = String(profile.executor_id ?? "").trim();
      if (!executorId) continue;

      const learned = await c.env.CAPABILITY_DB.prepare(
        `SELECT 1 FROM executor_capability
         WHERE executor_id = ? AND internal_runs > 0 LIMIT 1`,
      )
        .bind(executorId)
        .first();

      if (learned) {
        skipped += 1;
        continue;
      }

      await c.env.CAPABILITY_DB.prepare(
        `DELETE FROM executor_capability WHERE executor_id = ?`,
      )
        .bind(executorId)
        .run();

      const kind = String(profile.kind ?? "executor");
      const insertCap = c.env.CAPABILITY_DB.prepare(`
        INSERT INTO executor_capability (
          executor_id, kind, dimension, sub_dimension, score, confidence,
          internal_runs, successful_runs, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?)
      `);

      for (const [dimension, cap] of Object.entries(profile.capabilities ?? {})) {
        await insertCap
          .bind(
            executorId,
            kind,
            dimension,
            "",
            Number(cap.score ?? 0.5),
            Number(cap.confidence ?? 0),
            now,
          )
          .run();

        for (const [subDim, subScore] of Object.entries(cap.sub_scores ?? {})) {
          await insertCap
            .bind(
              executorId,
              kind,
              dimension,
              subDim,
              Number(subScore),
              Number(cap.confidence ?? 0),
              now,
            )
            .run();
        }
      }

      const upsertConstraint = c.env.CAPABILITY_DB.prepare(`
        INSERT INTO executor_constraints (executor_id, constraint_name, value)
        VALUES (?, ?, ?)
        ON CONFLICT(executor_id, constraint_name) DO UPDATE SET value = excluded.value
      `);

      for (const [name, value] of Object.entries(profile.constraints ?? {})) {
        await upsertConstraint
          .bind(executorId, name, constraintToText(value))
          .run();
      }

      if (profile.operational) {
        const op = profile.operational;
        await c.env.CAPABILITY_DB.prepare(`
          INSERT INTO executor_operational (
            executor_id, avg_latency_ms, completion_rate, retry_rate,
            cost_per_task_usd, total_runs, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(executor_id) DO UPDATE SET
            avg_latency_ms = excluded.avg_latency_ms,
            completion_rate = excluded.completion_rate,
            retry_rate = excluded.retry_rate,
            cost_per_task_usd = excluded.cost_per_task_usd,
            total_runs = excluded.total_runs,
            updated_at = excluded.updated_at
        `)
          .bind(
            executorId,
            Number(op.avg_latency_ms ?? 0),
            Number(op.completion_rate ?? 1),
            Number(op.retry_rate ?? 0),
            Number(op.cost_per_task_usd ?? 0),
            Number(op.total_runs ?? 0),
            now,
          )
          .run();
      }

      seeded += 1;
    }

    return c.json({ ok: true, seeded, skipped });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

profilesRoutes.post("/evidence", async (c) => {
  try {
    const body = await c.req.json<{
      executor_id?: string;
      dimension?: string;
      run_score?: number;
      success?: boolean;
      files_changed?: number;
    }>();

    const executorId = String(body.executor_id ?? "").trim();
    const dimension = String(body.dimension ?? "").trim();
    const runScore = Number(body.run_score ?? 0);
    const success = Boolean(body.success);

    if (!executorId || !dimension) {
      return c.json({ ok: false, error: "executor_id and dimension required" }, 400);
    }

    const now = Date.now();
    const debounceCutoff = now - DEBOUNCE_MS;

    const capResult = await c.env.CAPABILITY_DB.prepare(`
      UPDATE executor_capability
      SET score = score * (1.0 - ?) + ? * ?,
          confidence = MIN(confidence + 0.02, 1.0),
          internal_runs = internal_runs + 1,
          successful_runs = successful_runs + ?,
          updated_at = ?
      WHERE executor_id = ? AND dimension = ? AND sub_dimension = ''
        AND updated_at < ?
    `)
      .bind(
        EMA_ALPHA,
        runScore,
        EMA_ALPHA,
        success ? 1 : 0,
        now,
        executorId,
        dimension,
        debounceCutoff,
      )
      .run();

    const emaUpdated = (capResult.meta.changes ?? 0) > 0;

    const opRow = await c.env.CAPABILITY_DB.prepare(
      `SELECT completion_rate FROM executor_operational WHERE executor_id = ?`,
    )
      .bind(executorId)
      .first<{ completion_rate: number }>();

    const prevRate = opRow?.completion_rate ?? 1;
    const newRate = prevRate * (1 - EMA_ALPHA) + (success ? 1 : 0) * EMA_ALPHA;

    await c.env.CAPABILITY_DB.prepare(`
      UPDATE executor_operational
      SET total_runs = total_runs + 1,
          completion_rate = ?,
          updated_at = ?
      WHERE executor_id = ?
    `)
      .bind(newRate, now, executorId)
      .run();

    return c.json({ ok: true, ema_updated: emaUpdated });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

profilesRoutes.get("/:id", async (c) => {
  try {
    const executorId = c.req.param("id");

    const caps = await c.env.CAPABILITY_DB.prepare(
      `SELECT * FROM executor_capability WHERE executor_id = ? ORDER BY dimension, sub_dimension`,
    )
      .bind(executorId)
      .all<CapabilityRow>();

    const constraints = await c.env.CAPABILITY_DB.prepare(
      `SELECT * FROM executor_constraints WHERE executor_id = ?`,
    )
      .bind(executorId)
      .all<ConstraintRow>();

    const operational = await c.env.CAPABILITY_DB.prepare(
      `SELECT * FROM executor_operational WHERE executor_id = ?`,
    )
      .bind(executorId)
      .first<OperationalRow>();

    if (
      (caps.results ?? []).length === 0 &&
      (constraints.results ?? []).length === 0 &&
      !operational
    ) {
      return c.json({ ok: false, error: "profile not found" }, 404);
    }

    const profile = assembleProfile(
      executorId,
      caps.results ?? [],
      constraints.results ?? [],
      operational,
    );

    return c.json(profile);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

import { Hono } from "hono";
import type { AppBindings, CapabilityRow } from "../types";

export const leaderboardRoutes = new Hono<AppBindings>();

leaderboardRoutes.get("/:category", async (c) => {
  try {
    const category = c.req.param("category");

    const rows = await c.env.CAPABILITY_DB.prepare(`
      SELECT executor_id, score, confidence, internal_runs
      FROM executor_capability
      WHERE dimension = ? AND sub_dimension = ''
      ORDER BY score DESC
    `)
      .bind(category)
      .all<Pick<CapabilityRow, "executor_id" | "score" | "confidence" | "internal_runs">>();

    return c.json({
      category,
      entries: rows.results ?? [],
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ ok: false, error: message }, 500);
  }
});

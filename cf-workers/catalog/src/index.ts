import { Hono } from "hono";
import { cors } from "hono/cors";

export interface Env {
  DB: D1Database;
}

interface ModelRow {
  id: string;
  name: string;
  provider: string;
  tier: string;
  input_cost_per_1m: number;
  output_cost_per_1m: number;
  executor_compat: string;
  strengths: string;
  enabled: number;
  updated_at: number;
}

function parseModel(row: ModelRow) {
  return {
    ...row,
    enabled: !!row.enabled,
    executor_compat: JSON.parse(row.executor_compat || "[]"),
    strengths: JSON.parse(row.strengths || "[]"),
  };
}

const app = new Hono<{ Bindings: Env }>();
app.use("*", cors());

app.get("/health", (c) => c.json({ ok: true, service: "codeops-catalog" }));

app.get("/models", async (c) => {
  const tier = c.req.query("tier");
  let stmt = "SELECT * FROM models WHERE enabled = 1";
  const params: unknown[] = [];
  if (tier) {
    stmt += " AND tier = ?";
    params.push(tier);
  }
  stmt += " ORDER BY tier, id";
  const rows = await c.env.DB.prepare(stmt).bind(...params).all<ModelRow>();
  return c.json({ models: (rows.results ?? []).map(parseModel), count: rows.results?.length ?? 0 });
});

app.post("/models/sync", async (c) => {
  const body = await c.req.json<{ models?: Record<string, unknown>[] }>();
  const models = body.models ?? [];
  const now = Date.now();
  let upserted = 0;
  for (const m of models) {
    const id = String(m.id ?? "");
    if (!id) continue;
    await c.env.DB.prepare(
      `INSERT INTO models (id, name, provider, tier, input_cost_per_1m, output_cost_per_1m, executor_compat, strengths, enabled, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
       ON CONFLICT(id) DO UPDATE SET
         name=excluded.name, provider=excluded.provider, tier=excluded.tier,
         executor_compat=excluded.executor_compat, strengths=excluded.strengths,
         enabled=excluded.enabled, updated_at=excluded.updated_at`
    ).bind(
      id,
      String(m.name ?? id),
      String(m.provider ?? ""),
      String(m.tier ?? "standard"),
      Number(m.input_cost_per_1m ?? 0),
      Number(m.output_cost_per_1m ?? 0),
      JSON.stringify(m.executor_compat ?? ["zen"]),
      JSON.stringify(m.strengths ?? []),
      now,
    ).run();
    upserted += 1;
  }
  return c.json({ ok: true, upserted });
});

app.post("/match", async (c) => {
  const body = await c.req.json<{ task?: string; budget_usd?: number }>();
  const task = (body.task ?? "").toLowerCase();
  const rows = await c.env.DB.prepare(
    "SELECT * FROM models WHERE enabled = 1 ORDER BY tier ASC, id ASC"
  ).all<ModelRow>();
  const models = (rows.results ?? []).map(parseModel);

  let executor = "opencode";
  let model = "kimi-k2.6";
  if (/review|audit|checklist|readonly/.test(task)) {
    executor = "zen";
    model = models.find((m) => m.tier === "free")?.id ?? "deepseek-v4-flash-free";
  } else if (/backend|api|tracker|routes/.test(task)) {
    executor = "opencode";
    model = models.find((m) => m.id.includes("deepseek-v4-pro"))?.id ?? "deepseek-v4-pro";
  } else if (/react|tsx|tailwind|ui|kanban/.test(task)) {
    executor = "cursor";
    model = "composer-2.5";
  }

  return c.json({ task: body.task, executor, model, budget_usd: body.budget_usd ?? 1 });
});

export default app;

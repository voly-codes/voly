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
  metadata: string; // JSON blob; v2 extended fields
}

interface ParsedModel {
  id: string;
  name: string;
  provider: string;
  tier: string;
  input_cost_per_1m: number;
  output_cost_per_1m: number;
  executor_compat: unknown[];
  strengths: unknown[];
  enabled: boolean;
  updated_at: number;
  verified?: boolean;
  [key: string]: unknown;
}

// Parse stored JSON columns; metadata carries optional v2 fields.
function parseModel(row: ModelRow): ParsedModel {
  let meta: Record<string, unknown> = {};
  try {
    meta = JSON.parse(row.metadata || "{}");
  } catch {
    meta = {};
  }
  return {
    id: row.id,
    name: row.name,
    provider: row.provider,
    tier: row.tier,
    input_cost_per_1m: row.input_cost_per_1m,
    output_cost_per_1m: row.output_cost_per_1m,
    executor_compat: JSON.parse(row.executor_compat || "[]"),
    strengths: JSON.parse(row.strengths || "[]"),
    enabled: !!row.enabled,
    updated_at: row.updated_at,
    ...meta, // spread v2 fields; callers may ignore unknown keys
  };
}

// Build the metadata JSON blob from an incoming model payload.
function buildMetadata(m: Record<string, unknown>): string {
  const v2Keys = [
    "base_url",
    "context_window",
    "modalities",
    "rate_limit",
    "auth_requirement",
    "api_key_url",
    "supports_tools",
    "source_url",
    "upstream_model_id",
    "source_updated_at",
    "verified",
    "last_verified_at",
  ];
  const meta: Record<string, unknown> = {};
  for (const k of v2Keys) {
    if (m[k] !== undefined && m[k] !== null && m[k] !== "") {
      meta[k] = m[k];
    }
  }
  return JSON.stringify(meta);
}

const app = new Hono<{ Bindings: Env }>();
app.use("*", cors());

app.get("/health", (c) => c.json({ ok: true, service: "voly-catalog" }));

app.get("/models", async (c) => {
  const tier = c.req.query("tier");
  const verified = c.req.query("verified");
  let stmt = "SELECT * FROM models WHERE enabled = 1";
  const params: unknown[] = [];
  if (tier) {
    stmt += " AND tier = ?";
    params.push(tier);
  }
  stmt += " ORDER BY tier, id";
  const rows = await c.env.DB.prepare(stmt).bind(...params).all<ModelRow>();
  let results = (rows.results ?? []).map(parseModel);

  // Optional: filter to verified-only rows (checked in metadata blob)
  if (verified === "true") {
    results = results.filter((m) => m.verified === true);
  }

  return c.json({ models: results, count: results.length });
});

app.post("/models/sync", async (c) => {
  const body = await c.req.json<{ models?: Record<string, unknown>[] }>();
  const models = body.models ?? [];
  const now = Date.now();
  let upserted = 0;
  for (const m of models) {
    const id = String(m.id ?? "");
    if (!id) continue;
    const metadata = buildMetadata(m);
    await c.env.DB.prepare(
      `INSERT INTO models (id, name, provider, tier, input_cost_per_1m, output_cost_per_1m, executor_compat, strengths, enabled, updated_at, metadata)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         name=excluded.name, provider=excluded.provider, tier=excluded.tier,
         input_cost_per_1m=excluded.input_cost_per_1m,
         output_cost_per_1m=excluded.output_cost_per_1m,
         executor_compat=excluded.executor_compat, strengths=excluded.strengths,
         enabled=excluded.enabled, updated_at=excluded.updated_at,
         metadata=excluded.metadata`
    )
      .bind(
        id,
        String(m.name ?? id),
        String(m.provider ?? ""),
        String(m.tier ?? "standard"),
        Number(m.input_cost_per_1m ?? 0),
        Number(m.output_cost_per_1m ?? 0),
        JSON.stringify(m.executor_compat ?? ["zen"]),
        JSON.stringify(m.strengths ?? []),
        now,
        metadata,
      )
      .run();
    upserted += 1;
  }
  return c.json({ ok: true, upserted });
});

app.post("/match", async (c) => {
  // Deprecated: hardcoded catalog match. Prefer capability.voly.codes/match.
  // When CAPABILITY_PROXY_URL is bound, forward dimension-style requests there.
  const proxy = (c.env as { CAPABILITY_PROXY_URL?: string }).CAPABILITY_PROXY_URL;
  if (proxy) {
    try {
      const incoming = await c.req.json();
      const resp = await fetch(`${proxy.replace(/\/$/, "")}/match`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(incoming),
      });
      const data = await resp.json();
      return c.json({ ...data, deprecated: true, proxied_to: "capability" }, resp.status);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return c.json({ ok: false, error: message, deprecated: true }, 502);
    }
  }

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

  return c.json({
    task: body.task,
    executor,
    model,
    budget_usd: body.budget_usd ?? 1,
    deprecated: true,
    migrate_to: "https://capability.voly.codes/match",
  });
});

export default app;

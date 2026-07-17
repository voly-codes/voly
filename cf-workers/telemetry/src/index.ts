/**
 * voly-telemetry — CF Worker ingest for VOLY TaskEvents.
 *
 * Python side: voly/telemetry.py → send_to_pipeline() → POST /events (JSON array).
 *
 * Storage:
 *   - R2 (EVENTS_BUCKET): one object per event at events/<task_id>.json
 *   - D1 (DB): index row in `telemetry` table for list/search queries
 *
 * Endpoints:
 *   POST /events          — ingest batch (array of records); returns {ok,ingested}
 *   GET  /events/:task_id — fetch a single event by task_id
 *   GET  /events          — list recent events (?limit=N&executor=X&status=Y)
 *   GET  /health          — liveness check
 */

import { Hono } from "hono";
import { cors } from "hono/cors";

export interface Env {
  EVENTS_BUCKET: R2Bucket;
  DB: D1Database;
  API_TOKEN?: string;
}

interface EventRecord {
  task_id: string;
  executor?: string;
  status?: string;
  cost_usd?: number;
  duration_seconds?: number;
  input_tokens?: number;
  output_tokens?: number;
  model?: string;
  provider?: string;
  memory_hits?: number;
  [key: string]: unknown;
}

const CREATE_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS telemetry (
    task_id          TEXT PRIMARY KEY,
    executor         TEXT,
    status           TEXT,
    cost_usd         REAL,
    duration_seconds REAL,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    model            TEXT,
    provider         TEXT,
    memory_hits      INTEGER DEFAULT 0,
    created_at       INTEGER NOT NULL
  )
`;

function authorize(c: { req: { header: (name: string) => string | undefined }; env: Env }): boolean {
  const required = c.env.API_TOKEN;
  if (!required) return true;
  const header = c.req.header("Authorization") ?? "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === required;
}

async function ensureTable(db: D1Database): Promise<void> {
  await db.prepare(CREATE_TABLE_SQL).run();
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/health", (c) =>
  c.json({ status: "ok", service: "voly-telemetry" }),
);

app.post("/events", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  let records: EventRecord[];
  try {
    const body = await c.req.json();
    records = Array.isArray(body) ? body : [body];
  } catch {
    return c.json({ error: "invalid JSON" }, 400);
  }

  if (records.length === 0) {
    return c.json({ ok: true, ingested: 0 });
  }

  await ensureTable(c.env.DB);

  const now = Date.now();
  let ingested = 0;

  const stmt = c.env.DB.prepare(`
    INSERT INTO telemetry
      (task_id, executor, status, cost_usd, duration_seconds, input_tokens,
       output_tokens, model, provider, memory_hits, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(task_id) DO UPDATE SET
      executor         = excluded.executor,
      status           = excluded.status,
      cost_usd         = excluded.cost_usd,
      duration_seconds = excluded.duration_seconds,
      input_tokens     = excluded.input_tokens,
      output_tokens    = excluded.output_tokens,
      model            = excluded.model,
      provider         = excluded.provider,
      memory_hits      = excluded.memory_hits
  `);

  for (const rec of records) {
    const taskId = (rec.task_id as string | undefined) ?? "";
    if (!taskId) continue;

    await c.env.EVENTS_BUCKET.put(
      `events/${taskId}.json`,
      JSON.stringify(rec),
      { httpMetadata: { contentType: "application/json" } },
    );

    await stmt.bind(
      taskId,
      rec.executor ?? null,
      rec.status ?? null,
      rec.cost_usd ?? null,
      rec.duration_seconds ?? null,
      rec.input_tokens ?? null,
      rec.output_tokens ?? null,
      rec.model ?? null,
      rec.provider ?? null,
      rec.memory_hits ?? 0,
      now,
    ).run();

    ingested++;
  }

  return c.json({ ok: true, ingested });
});

app.get("/events/:task_id", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const taskId = c.req.param("task_id");
  const obj = await c.env.EVENTS_BUCKET.get(`events/${taskId}.json`);
  if (!obj) return c.json({ error: "Not found" }, 404);

  const text = await obj.text();
  return new Response(text, { headers: { "Content-Type": "application/json" } });
});

app.get("/events", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  await ensureTable(c.env.DB);

  const limit = Math.min(parseInt(c.req.query("limit") ?? "50"), 200);
  const executor = c.req.query("executor");
  const status = c.req.query("status");

  let sql = "SELECT * FROM telemetry";
  const params: unknown[] = [];
  const where: string[] = [];
  if (executor) { where.push("executor = ?"); params.push(executor); }
  if (status) { where.push("status = ?"); params.push(status); }
  if (where.length) sql += " WHERE " + where.join(" AND ");
  sql += " ORDER BY created_at DESC LIMIT ?";
  params.push(limit);

  const rows = await c.env.DB.prepare(sql).bind(...params).all();
  return c.json({ events: rows.results ?? [], count: (rows.results ?? []).length });
});

// /ingest is an alias for /events — matches CF_PIPELINE_TELEMETRY_ENDPOINT convention
app.post("/ingest", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  let records: EventRecord[];
  try {
    const body = await c.req.json();
    records = Array.isArray(body) ? body : [body];
  } catch {
    return c.json({ error: "Invalid JSON" }, 400);
  }

  await ensureTable(c.env.DB);

  let ingested = 0;
  for (const record of records) {
    if (!record?.task_id) continue;
    const key = `events/${record.task_id}.json`;
    await c.env.EVENTS_BUCKET.put(key, JSON.stringify(record), {
      httpMetadata: { contentType: "application/json" },
    });
    const now = Date.now();
    await c.env.DB.prepare(
      `INSERT OR REPLACE INTO telemetry
        (task_id,executor,status,cost_usd,duration_seconds,input_tokens,output_tokens,model,provider,memory_hits,created_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?)`
    ).bind(
      record.task_id,
      record.executor ?? null,
      record.status ?? null,
      record.cost_usd ?? null,
      record.duration_seconds ?? null,
      record.input_tokens ?? null,
      record.output_tokens ?? null,
      record.model ?? null,
      record.provider ?? null,
      record.memory_hits ?? 0,
      now,
    ).run();
    ingested++;
  }

  return c.json({ ok: true, ingested });
});

export default app;

import { Hono } from "hono";
import { cors } from "hono/cors";

export interface Env {
  DB: D1Database;
  SKILLS_BUCKET: R2Bucket;
  VECTORIZE: VectorizeIndex;
  INDEX: KVNamespace;
  AI: Ai;
}

interface SkillRow {
  id: string;
  name: string;
  description: string;
  content: string;
  version: string;
  author: string;
  source: string;
  status: string;
  tags: string;
  capabilities: string;
  required_tools: string;
  compatible_agents: string;
  compatible_languages: string;
  compatible_frameworks: string;
  downloads: number;
  usage_count: number;
  success_rate: number;
  created_at: number;
  updated_at: number;
}

// slim=true strips content — used for list/search responses to keep payloads small
function parseSkill(row: SkillRow, slim = false): Record<string, unknown> {
  const out: Record<string, unknown> = {
    ...row,
    tags: JSON.parse(row.tags || "[]"),
    capabilities: JSON.parse(row.capabilities || "[]"),
    required_tools: JSON.parse(row.required_tools || "[]"),
    compatible_agents: JSON.parse(row.compatible_agents || "[]"),
    compatible_languages: JSON.parse(row.compatible_languages || "[]"),
    compatible_frameworks: JSON.parse(row.compatible_frameworks || "[]"),
  };
  if (slim) delete out["content"];
  return out;
}

const EMBED_MODEL = "@cf/baai/bge-small-en-v1.5" as BaseAiTextEmbeddingsModels;

async function embed(ai: Ai, text: string): Promise<number[] | null> {
  try {
    const result = await ai.run(EMBED_MODEL, { text: [text] });
    return (result as { data: number[][] }).data[0];
  } catch {
    return null;
  }
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

// ── Health ────────────────────────────────────────────────────────────────────

app.get("/health", (c) => c.json({ ok: true, service: "codeops-marketplace" }));

app.get("/health/detailed", async (c) => {
  const services: Record<string, { ok: boolean; latency_ms?: number; error?: string }> = {};
  let skillCount = 0;

  // D1 — run a real query to confirm database + skills table are accessible
  const t0 = Date.now();
  try {
    const row = await c.env.DB
      .prepare("SELECT COUNT(*) as n FROM skills WHERE status = 'active'")
      .first<{ n: number }>();
    skillCount = row?.n ?? 0;
    services.d1 = { ok: true, latency_ms: Date.now() - t0 };
  } catch (e) {
    services.d1 = { ok: false, error: String(e) };
  }

  // KV — write a ephemeral probe key
  const t1 = Date.now();
  try {
    await c.env.INDEX.put("_health", String(Date.now()), { expirationTtl: 60 });
    services.kv = { ok: true, latency_ms: Date.now() - t1 };
  } catch (e) {
    services.kv = { ok: false, error: String(e) };
  }

  // R2 — head() returns null for missing key but throws on connectivity failure
  const t2 = Date.now();
  try {
    await c.env.SKILLS_BUCKET.head("_health");
    services.r2 = { ok: true, latency_ms: Date.now() - t2 };
  } catch (e) {
    services.r2 = { ok: false, error: String(e) };
  }

  // Vectorize — getByIds([]) returns empty but proves the index is reachable
  const t3 = Date.now();
  try {
    await c.env.VECTORIZE.getByIds(["_probe"]);
    services.vectorize = { ok: true, latency_ms: Date.now() - t3 };
  } catch (e) {
    services.vectorize = { ok: false, error: String(e) };
  }

  const allOk = Object.values(services).every((s) => s.ok);
  return c.json(
    { ok: allOk, service: "codeops-marketplace", skills_active: skillCount, services },
    allOk ? 200 : 503,
  );
});

// ── Browse (public, read-only) ─────────────────────────────────────────────────

// GET /skills — list with pagination and filtering
app.get("/skills", async (c) => {
  const page = parseInt(c.req.query("page") ?? "1");
  const limit = Math.min(parseInt(c.req.query("limit") ?? "20"), 100);
  const source = c.req.query("source");
  const status = c.req.query("status") ?? "active";
  const agent = c.req.query("agent");
  const offset = (page - 1) * limit;

  let where = "WHERE s.status = ?";
  const params: unknown[] = [status];

  if (source) { where += " AND s.source = ?"; params.push(source); }
  if (agent)  { where += " AND s.compatible_agents LIKE ?"; params.push(`%"${agent}"%`); }

  const [rows, countRow] = await Promise.all([
    c.env.DB.prepare(
      `SELECT * FROM skills s ${where} ORDER BY s.updated_at DESC LIMIT ? OFFSET ?`,
    ).bind(...params, limit, offset).all<SkillRow>(),
    c.env.DB.prepare(
      `SELECT COUNT(*) as total FROM skills s ${where}`,
    ).bind(...params).first<{ total: number }>(),
  ]);

  return c.json({
    skills: (rows.results ?? []).map((r) => parseSkill(r, true)),
    total: countRow?.total ?? 0,
    page,
    limit,
  });
});

// GET /skills/search — semantic + FTS search (content excluded from results)
app.get("/skills/search", async (c) => {
  const q = c.req.query("q");
  const limit = Math.min(parseInt(c.req.query("limit") ?? "10"), 50);

  if (!q) return c.json({ error: "q is required" }, 400);

  // Try semantic search via Vectorize first
  let vectorIds: string[] = [];
  const vec = await embed(c.env.AI, q);
  if (vec) {
    try {
      const matches = await c.env.VECTORIZE.query(vec, { topK: limit, returnMetadata: "none" });
      vectorIds = matches.matches.map((m) => m.id);
    } catch {
      // Vectorize unavailable — fall through to FTS
    }
  }

  if (vectorIds.length > 0) {
    const placeholders = vectorIds.map(() => "?").join(",");
    const rows = await c.env.DB.prepare(
      `SELECT * FROM skills WHERE id IN (${placeholders}) AND status = 'active'`,
    ).bind(...vectorIds).all<SkillRow>();
    const byId = Object.fromEntries((rows.results ?? []).map((r) => [r.id, r]));
    const ordered = vectorIds.map((id) => byId[id]).filter(Boolean) as SkillRow[];
    return c.json({ skills: ordered.map((r) => parseSkill(r, true)), source: "semantic" });
  }

  // FTS fallback
  const ftsRows = await c.env.DB.prepare(
    `SELECT s.* FROM skills s
     JOIN skills_fts f ON s.id = f.id
     WHERE skills_fts MATCH ? AND s.status = 'active'
     ORDER BY rank LIMIT ?`,
  ).bind(q, limit).all<SkillRow>();

  return c.json({ skills: (ftsRows.results ?? []).map((r) => parseSkill(r, true)), source: "fts" });
});

// GET /skills/:id — metadata + content
app.get("/skills/:id", async (c) => {
  const id = c.req.param("id");

  // KV hot cache
  const cached = await c.env.INDEX.get(`skill:${id}`, "json") as SkillRow | null;
  if (cached) return c.json({ skill: parseSkill(cached), cached: true });

  const row = await c.env.DB.prepare("SELECT * FROM skills WHERE id = ?")
    .bind(id).first<SkillRow>();

  if (!row) return c.json({ error: "Skill not found" }, 404);

  await c.env.INDEX.put(`skill:${id}`, JSON.stringify(row), { expirationTtl: 300 });
  return c.json({ skill: parseSkill(row) });
});

// GET /skills/:id/download — full skill with content; prefers D1, falls back to R2
app.get("/skills/:id/download", async (c) => {
  const id = c.req.param("id");

  const row = await c.env.DB.prepare("SELECT * FROM skills WHERE id = ?")
    .bind(id).first<SkillRow>();

  if (row && row.content) {
    c.executionCtx.waitUntil(
      c.env.DB.prepare("UPDATE skills SET downloads = downloads + 1 WHERE id = ?")
        .bind(id).run(),
    );
    return c.json(parseSkill(row));
  }

  // Fall back to R2 for skills seeded before the content column was added
  const obj = await c.env.SKILLS_BUCKET.get(`${id}.json`);
  if (!obj) return c.json({ error: "Skill not found" }, 404);

  c.executionCtx.waitUntil(
    c.env.DB.prepare("UPDATE skills SET downloads = downloads + 1 WHERE id = ?")
      .bind(id).run(),
  );

  return new Response(obj.body, { headers: { "Content-Type": "application/json" } });
});

// POST /skills — upsert skill (used by `codeops skill seed`)
app.post("/skills", async (c) => {
  let body: Record<string, unknown>;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const id = (body.id as string) || `skill-${Date.now().toString(36)}`;
  const name = body.name as string;
  if (!name) return c.json({ error: "name is required" }, 400);

  const now = Date.now();
  const content = (body.content as string) || "";

  await c.env.DB.prepare(`
    INSERT INTO skills (id, name, description, content, version, author, source, status,
      tags, capabilities, required_tools, compatible_agents, compatible_languages,
      compatible_frameworks, downloads, usage_count, success_rate, created_at, updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name, description=excluded.description, content=excluded.content,
      version=excluded.version, tags=excluded.tags, capabilities=excluded.capabilities,
      compatible_agents=excluded.compatible_agents,
      compatible_languages=excluded.compatible_languages,
      compatible_frameworks=excluded.compatible_frameworks,
      updated_at=excluded.updated_at
  `).bind(
    id,
    name,
    (body.description as string) || "",
    content,
    (body.version as string) || "1.0.0",
    (body.author as string) || "",
    (body.source as string) || "marketplace",
    "active",
    JSON.stringify(body.tags || []),
    JSON.stringify(body.capabilities || []),
    JSON.stringify(body.required_tools || []),
    JSON.stringify(body.compatible_agents || []),
    JSON.stringify(body.compatible_languages || []),
    JSON.stringify(body.compatible_frameworks || []),
    0, 0, 1.0,
    now, now,
  ).run();

  // Mirror to R2 as backup
  c.executionCtx.waitUntil(
    c.env.SKILLS_BUCKET.put(
      `${id}.json`,
      JSON.stringify({ ...body, id, updated_at: now }),
      { httpMetadata: { contentType: "application/json" } },
    ),
  );

  // Upsert vector embedding (fire-and-forget)
  const embedInput = [name, (body.description as string) || "", ...(body.tags as string[] || [])].join(" ");
  c.executionCtx.waitUntil(
    (async () => {
      const vec = await embed(c.env.AI, embedInput);
      if (vec) {
        await c.env.VECTORIZE.upsert([{
          id,
          values: vec,
          metadata: { name, tags: body.tags || [] },
        }]);
      }
    })(),
  );

  // Bust KV cache
  c.executionCtx.waitUntil(c.env.INDEX.delete(`skill:${id}`));

  return c.json({ id, ok: true }, 201);
});

// DELETE /skills/:id — soft delete (set status=archived)
app.delete("/skills/:id", async (c) => {
  const id = c.req.param("id");
  const result = await c.env.DB.prepare(
    "UPDATE skills SET status = 'archived', updated_at = ? WHERE id = ?",
  ).bind(Date.now(), id).run();

  if (result.meta.changes === 0) return c.json({ error: "Skill not found" }, 404);

  await c.env.INDEX.delete(`skill:${id}`);
  return c.json({ ok: true });
});

export default app;

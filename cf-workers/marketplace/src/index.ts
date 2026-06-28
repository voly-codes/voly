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

function parseSkill(row: SkillRow) {
  return {
    ...row,
    tags: JSON.parse(row.tags || "[]"),
    capabilities: JSON.parse(row.capabilities || "[]"),
    required_tools: JSON.parse(row.required_tools || "[]"),
    compatible_agents: JSON.parse(row.compatible_agents || "[]"),
    compatible_languages: JSON.parse(row.compatible_languages || "[]"),
    compatible_frameworks: JSON.parse(row.compatible_frameworks || "[]"),
  };
}

async function embedText(ai: Ai, text: string): Promise<number[]> {
  const result = await ai.run("@cf/google/embeddinggemma-300m" as BaseAiTextEmbeddingsModels, {
    text: [text],
  });
  return (result as { data: number[][] }).data[0];
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

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
  if (agent) { where += " AND s.compatible_agents LIKE ?"; params.push(`%"${agent}"%`); }

  const [rows, countRow] = await Promise.all([
    c.env.DB.prepare(
      `SELECT * FROM skills s ${where} ORDER BY s.updated_at DESC LIMIT ? OFFSET ?`
    ).bind(...params, limit, offset).all<SkillRow>(),
    c.env.DB.prepare(
      `SELECT COUNT(*) as total FROM skills s ${where}`
    ).bind(...params).first<{ total: number }>(),
  ]);

  return c.json({
    skills: (rows.results ?? []).map(parseSkill),
    total: countRow?.total ?? 0,
    page,
    limit,
  });
});

// GET /skills/search — semantic + FTS search
app.get("/skills/search", async (c) => {
  const q = c.req.query("q");
  const limit = Math.min(parseInt(c.req.query("limit") ?? "10"), 50);

  if (!q) return c.json({ error: "q is required" }, 400);

  // Try semantic search via Vectorize first
  let vectorIds: string[] = [];
  try {
    const embedding = await embedText(c.env.AI, q);
    const matches = await c.env.VECTORIZE.query(embedding, { topK: limit, returnMetadata: "none" });
    vectorIds = matches.matches.map((m) => m.id);
  } catch {
    // Vectorize unavailable — fall through to FTS
  }

  if (vectorIds.length > 0) {
    const placeholders = vectorIds.map(() => "?").join(",");
    const rows = await c.env.DB.prepare(
      `SELECT * FROM skills WHERE id IN (${placeholders}) AND status = 'active'`
    ).bind(...vectorIds).all<SkillRow>();

    // Re-order by vector match order
    const byId = Object.fromEntries((rows.results ?? []).map((r) => [r.id, r]));
    const ordered = vectorIds.map((id) => byId[id]).filter(Boolean);
    return c.json({ skills: ordered.map(parseSkill), source: "semantic" });
  }

  // FTS fallback
  const ftsRows = await c.env.DB.prepare(
    `SELECT s.* FROM skills s
     JOIN skills_fts f ON s.id = f.id
     WHERE skills_fts MATCH ? AND s.status = 'active'
     ORDER BY rank LIMIT ?`
  ).bind(q, limit).all<SkillRow>();

  return c.json({ skills: (ftsRows.results ?? []).map(parseSkill), source: "fts" });
});

// GET /skills/:id — get single skill
app.get("/skills/:id", async (c) => {
  const id = c.req.param("id");

  // KV hot cache
  const cached = await c.env.INDEX.get(`skill:${id}`, "json") as SkillRow | null;
  if (cached) return c.json({ skill: parseSkill(cached), cached: true });

  const row = await c.env.DB.prepare(
    "SELECT * FROM skills WHERE id = ?"
  ).bind(id).first<SkillRow>();

  if (!row) return c.json({ error: "Skill not found" }, 404);

  // Cache for 5 min
  await c.env.INDEX.put(`skill:${id}`, JSON.stringify(row), { expirationTtl: 300 });

  return c.json({ skill: parseSkill(row) });
});

// POST /skills — publish new skill
app.post("/skills", async (c) => {
  let body: Record<string, unknown>;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "Invalid JSON body" }, 400);
  }

  const id = (body.id as string) || `skill-${Date.now().toString(36)}`;
  const name = body.name as string;
  const description = (body.description as string) || "";

  if (!name) return c.json({ error: "name is required" }, 400);

  const now = Date.now();
  const row: Omit<SkillRow, "rowid"> = {
    id,
    name,
    description,
    version: (body.version as string) || "1.0.0",
    author: (body.author as string) || "",
    source: (body.source as string) || "marketplace",
    status: "active",
    tags: JSON.stringify(body.tags || []),
    capabilities: JSON.stringify(body.capabilities || []),
    required_tools: JSON.stringify(body.required_tools || []),
    compatible_agents: JSON.stringify(body.compatible_agents || []),
    compatible_languages: JSON.stringify(body.compatible_languages || []),
    compatible_frameworks: JSON.stringify(body.compatible_frameworks || []),
    downloads: 0,
    usage_count: 0,
    success_rate: 1.0,
    created_at: now,
    updated_at: now,
  };

  // Upsert into D1
  await c.env.DB.prepare(`
    INSERT INTO skills (id, name, description, version, author, source, status,
      tags, capabilities, required_tools, compatible_agents, compatible_languages,
      compatible_frameworks, downloads, usage_count, success_rate, created_at, updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name, description=excluded.description, version=excluded.version,
      tags=excluded.tags, capabilities=excluded.capabilities,
      compatible_agents=excluded.compatible_agents,
      compatible_languages=excluded.compatible_languages,
      compatible_frameworks=excluded.compatible_frameworks,
      updated_at=excluded.updated_at
  `).bind(
    row.id, row.name, row.description, row.version, row.author, row.source, row.status,
    row.tags, row.capabilities, row.required_tools, row.compatible_agents,
    row.compatible_languages, row.compatible_frameworks,
    row.downloads, row.usage_count, row.success_rate, row.created_at, row.updated_at,
  ).run();

  // Store full JSON in R2 (includes content field)
  await c.env.SKILLS_BUCKET.put(
    `${id}.json`,
    JSON.stringify({ ...body, id, updated_at: now }),
    { httpMetadata: { contentType: "application/json" } }
  );

  // Upsert vector embedding
  const embedText = [name, description, ...(body.tags as string[] || [])].join(" ");
  try {
    const embedding = await c.env.AI.run("@cf/google/embeddinggemma-300m" as BaseAiTextEmbeddingsModels, {
      text: [embedText],
    });
    await c.env.VECTORIZE.upsert([{
      id,
      values: (embedding as { data: number[][] }).data[0],
      metadata: { name, tags: body.tags || [] },
    }]);
  } catch {
    // Vectorize failure is non-fatal
  }

  // Bust KV cache
  await c.env.INDEX.delete(`skill:${id}`);

  return c.json({ id, ok: true }, 201);
});

// GET /skills/:id/download — download full skill JSON from R2
app.get("/skills/:id/download", async (c) => {
  const id = c.req.param("id");

  const obj = await c.env.SKILLS_BUCKET.get(`${id}.json`);
  if (!obj) return c.json({ error: "Skill not found" }, 404);

  // Increment downloads counter (fire-and-forget)
  c.executionCtx.waitUntil(
    c.env.DB.prepare("UPDATE skills SET downloads = downloads + 1 WHERE id = ?")
      .bind(id).run()
  );

  return new Response(obj.body, {
    headers: { "Content-Type": "application/json" },
  });
});

// DELETE /skills/:id — soft delete (set status=archived)
app.delete("/skills/:id", async (c) => {
  const id = c.req.param("id");
  const result = await c.env.DB.prepare(
    "UPDATE skills SET status = 'archived', updated_at = ? WHERE id = ?"
  ).bind(Date.now(), id).run();

  if (result.meta.changes === 0) return c.json({ error: "Skill not found" }, 404);

  await c.env.INDEX.delete(`skill:${id}`);
  return c.json({ ok: true });
});

// GET /health
app.get("/health", (c) => c.json({ ok: true, service: "codeops-marketplace" }));

export default app;

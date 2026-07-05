import { Hono } from "hono";
import { cors } from "hono/cors";

export interface Env {
  DB: D1Database;
  MEMORY_BUCKET: R2Bucket;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
  API_TOKEN?: string;
}

const EMBED_MODEL = "@cf/google/embeddinggemma-300m";

function authorize(c: { req: { header: (name: string) => string | undefined }; env: Env }): boolean {
  const required = c.env.API_TOKEN;
  if (!required) return true;
  const header = c.req.header("Authorization") ?? "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === required;
}

async function embedText(ai: Ai, text: string): Promise<number[]> {
  const result = await ai.run(EMBED_MODEL as BaseAiTextEmbeddingsModels, { text: [text] });
  return (result as { data: number[][] }).data[0];
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/health", (c) => c.json({ status: "ok", service: "voly-memory" }));

app.post("/memory/add", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const body = await c.req.json<{
    title: string;
    content: string;
    category?: string;
    tags?: string[];
    metadata?: Record<string, unknown>;
    importance?: number;
    id?: string;
  }>();

  if (!body.title || !body.content) {
    return c.json({ error: "title and content required" }, 400);
  }

  const id = body.id ?? crypto.randomUUID();
  const category = body.category ?? "context";
  const tags = body.tags ?? [];
  const now = Date.now();
  const text = `${body.title} ${body.content}`;

  const embedding = await embedText(c.env.AI, text);
  await c.env.VECTORIZE.upsert([
    {
      id,
      values: embedding,
      metadata: {
        title: body.title,
        category,
        tags: JSON.stringify(tags),
        content: body.content.slice(0, 512),
      },
    },
  ]);

  await c.env.DB.prepare(
    `INSERT INTO memories (id, category, title, content, metadata, importance, tags, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       category = excluded.category,
       title = excluded.title,
       content = excluded.content,
       metadata = excluded.metadata,
       importance = excluded.importance,
       tags = excluded.tags,
       updated_at = excluded.updated_at`,
  )
    .bind(
      id,
      category,
      body.title,
      body.content,
      JSON.stringify(body.metadata ?? {}),
      body.importance ?? 0.5,
      JSON.stringify(tags),
      now,
      now,
    )
    .run();

  await c.env.MEMORY_BUCKET.put(
    `memory/${category}/${id}.json`,
    JSON.stringify({ id, title: body.title, content: body.content, category, tags, created_at: now }),
  );

  return c.json({ ok: true, id }, 201);
});

app.post("/memory/search", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const body = await c.req.json<{ query: string; limit?: number; category?: string }>();
  if (!body.query) return c.json({ error: "query required" }, 400);

  const limit = Math.min(body.limit ?? 5, 50);
  const embedding = await embedText(c.env.AI, body.query);
  const matches = await c.env.VECTORIZE.query(embedding, {
    topK: limit,
    returnMetadata: "all",
  });

  const results = (matches.matches ?? []).map((m) => ({
    id: m.id,
    score: m.score,
    title: (m.metadata?.title as string) ?? "",
    category: (m.metadata?.category as string) ?? "",
    content: (m.metadata?.content as string) ?? "",
    tags: JSON.parse((m.metadata?.tags as string) ?? "[]") as string[],
  }));

  if (body.category) {
    return c.json({ results: results.filter((r) => r.category === body.category), source: "semantic" });
  }

  return c.json({ results, source: "semantic" });
});

app.get("/memory/:id", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const row = await c.env.DB.prepare("SELECT * FROM memories WHERE id = ?")
    .bind(c.req.param("id"))
    .first<{
      id: string;
      category: string;
      title: string;
      content: string;
      metadata: string;
      importance: number;
      tags: string;
      created_at: number;
      updated_at: number;
    }>();

  if (!row) return c.json({ error: "Not found" }, 404);
  return c.json({
    id: row.id,
    category: row.category,
    title: row.title,
    content: row.content,
    metadata: JSON.parse(row.metadata || "{}"),
    importance: row.importance,
    tags: JSON.parse(row.tags || "[]"),
    created_at: row.created_at,
    updated_at: row.updated_at,
  });
});

app.get("/memory", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const category = c.req.query("category");
  const limit = Math.min(parseInt(c.req.query("limit") ?? "20"), 100);
  let query = "SELECT id, category, title, importance, updated_at FROM memories";
  const params: unknown[] = [];
  if (category) {
    query += " WHERE category = ?";
    params.push(category);
  }
  query += " ORDER BY updated_at DESC LIMIT ?";
  params.push(limit);

  const rows = await c.env.DB.prepare(query).bind(...params).all();
  return c.json({ memories: rows.results ?? [], count: (rows.results ?? []).length });
});

export default app;

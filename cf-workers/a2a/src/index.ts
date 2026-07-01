import { Hono } from "hono";
import { cors } from "hono/cors";
import { buildBuiltinAgents, getBuiltinAgent } from "./definitions";

export interface Env {
  DB: D1Database;
  A2A_QUEUE: Queue;
  AGENT_WORKER?: Fetcher;
  API_TOKEN?: string;
  AGENT_WORKER_URL?: string;
  AGENT_WORKER_TOKEN?: string;
}

interface QueueMessage {
  task_id: string;
  agent_name: string;
  title: string;
  description: string;
}

function authorize(c: { req: { header: (name: string) => string | undefined }; env: Env }): boolean {
  const required = c.env.API_TOKEN;
  if (!required) return true;
  const header = c.req.header("Authorization") ?? "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === required;
}

async function ensureAgents(db: D1Database, baseUrl: string): Promise<void> {
  const row = await db.prepare("SELECT COUNT(*) as n FROM a2a_agents").first<{ n: number }>();
  if ((row?.n ?? 0) > 0) return;

  const now = Date.now();
  for (const card of buildBuiltinAgents(baseUrl)) {
    await db
      .prepare(
        `INSERT INTO a2a_agents (name, url, card_json, updated_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(name) DO NOTHING`,
      )
      .bind(card.name, card.url, JSON.stringify(card), now)
      .run();
  }
}

async function loadTask(db: D1Database, id: string): Promise<Record<string, unknown> | null> {
  const row = await db
    .prepare("SELECT * FROM a2a_tasks WHERE id = ?")
    .bind(id)
    .first<{
      id: string;
      agent_name: string;
      title: string;
      description: string;
      state: string;
      result: string;
      error: string;
      metadata: string;
      created_at: number;
      updated_at: number;
    }>();
  if (!row) return null;
  return {
    id: row.id,
    agent_name: row.agent_name,
    title: row.title,
    description: row.description,
    state: row.state,
    result: row.result,
    error: row.error,
    metadata: JSON.parse(row.metadata || "{}"),
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function saveTask(
  db: D1Database,
  task: {
    id: string;
    agent_name: string;
    title: string;
    description: string;
    state: string;
    result?: string;
    error?: string;
    metadata?: Record<string, unknown>;
    created_at?: number;
  },
): Promise<void> {
  const now = Date.now();
  const created = task.created_at ?? now;
  await db
    .prepare(
      `INSERT INTO a2a_tasks (id, agent_name, title, description, state, result, error, metadata, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         agent_name = excluded.agent_name,
         title = excluded.title,
         description = excluded.description,
         state = excluded.state,
         result = excluded.result,
         error = excluded.error,
         metadata = excluded.metadata,
         updated_at = excluded.updated_at`,
    )
    .bind(
      task.id,
      task.agent_name,
      task.title,
      task.description,
      task.state,
      task.result ?? "",
      task.error ?? "",
      JSON.stringify(task.metadata ?? {}),
      created,
      now,
    )
    .run();
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/health", (c) =>
  c.json({
    status: "ok",
    service: "codeops-a2a",
    queue: "codeops-a2a-tasks",
  }),
);

app.get("/agents", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const baseUrl = new URL(c.req.url).origin;
  await ensureAgents(c.env.DB, baseUrl);

  const rows = await c.env.DB
    .prepare("SELECT name, url, card_json, updated_at FROM a2a_agents ORDER BY name")
    .all<{ name: string; url: string; card_json: string; updated_at: number }>();

  const agents = (rows.results ?? []).map((row) => JSON.parse(row.card_json));
  return c.json({ agents, count: agents.length });
});

app.get("/agents/:name/card", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const name = c.req.param("name");
  const baseUrl = new URL(c.req.url).origin;
  await ensureAgents(c.env.DB, baseUrl);

  const row = await c.env.DB
    .prepare("SELECT card_json FROM a2a_agents WHERE name = ?")
    .bind(name)
    .first<{ card_json: string }>();

  if (row) {
    return c.json(JSON.parse(row.card_json));
  }

  const builtin = getBuiltinAgent(name, baseUrl);
  if (!builtin) return c.json({ error: "Agent not found" }, 404);
  return c.json(builtin);
});

app.get("/agents/:name/.well-known/agent-card.json", async (c) => {
  const target = new URL(c.req.url);
  target.pathname = `/agents/${c.req.param("name")}/card`;
  return c.redirect(target.toString(), 307);
});

app.post("/agents/register", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const body = await c.req.json<{ card: Record<string, unknown> }>();
  const card = body.card;
  const name = String(card.name ?? "");
  if (!name) return c.json({ error: "card.name required" }, 400);

  const now = Date.now();
  await c.env.DB
    .prepare(
      `INSERT INTO a2a_agents (name, url, card_json, updated_at)
       VALUES (?, ?, ?, ?)
       ON CONFLICT(name) DO UPDATE SET url = excluded.url, card_json = excluded.card_json, updated_at = excluded.updated_at`,
    )
    .bind(name, String(card.url ?? ""), JSON.stringify(card), now)
    .run();

  return c.json({ ok: true, name }, 201);
});

app.post("/tasks", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const body = await c.req.json<{
    agent_name?: string;
    title: string;
    description?: string;
    async?: boolean;
    metadata?: Record<string, unknown>;
  }>();

  const baseUrl = new URL(c.req.url).origin;
  await ensureAgents(c.env.DB, baseUrl);

  const agentName = body.agent_name ?? "";
  if (agentName) {
    const exists = await c.env.DB
      .prepare("SELECT name FROM a2a_agents WHERE name = ?")
      .bind(agentName)
      .first();
    if (!exists) return c.json({ error: `Unknown agent: ${agentName}` }, 404);
  }

  const id = crypto.randomUUID();
  const description = body.description ?? body.title;
  await saveTask(c.env.DB, {
    id,
    agent_name: agentName,
    title: body.title,
    description,
    state: "submitted",
    metadata: body.metadata ?? {},
  });

  if (body.async !== false && agentName) {
    await c.env.A2A_QUEUE.send({
      task_id: id,
      agent_name: agentName,
      title: body.title,
      description,
    } satisfies QueueMessage);
  }

  return c.json({ task_id: id, state: "submitted", agent_name: agentName }, 201);
});

app.get("/tasks/:id", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const task = await loadTask(c.env.DB, c.req.param("id"));
  if (!task) return c.json({ error: "Not found" }, 404);
  return c.json(task);
});

app.put("/tasks/:id", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const id = c.req.param("id");
  const existing = await loadTask(c.env.DB, id);
  if (!existing) return c.json({ error: "Not found" }, 404);

  const body = await c.req.json<{
    state?: string;
    result?: string;
    error?: string;
    metadata?: Record<string, unknown>;
  }>();

  await saveTask(c.env.DB, {
    id,
    agent_name: String(existing.agent_name),
    title: String(existing.title),
    description: String(existing.description),
    state: body.state ?? String(existing.state),
    result: body.result ?? String(existing.result),
    error: body.error ?? String(existing.error),
    metadata: { ...(existing.metadata as Record<string, unknown>), ...(body.metadata ?? {}) },
    created_at: Number(existing.created_at),
  });

  return c.json({ ok: true, task_id: id });
});

app.post("/tasks/:id/complete", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const id = c.req.param("id");
  const existing = await loadTask(c.env.DB, id);
  if (!existing) return c.json({ error: "Not found" }, 404);

  if (existing.state === "completed") {
    return c.json({
      ok: true,
      task_id: id,
      state: "completed",
      noop: true,
      result: String(existing.result ?? ""),
    });
  }

  const body = await c.req.json<{ result: string }>();
  await saveTask(c.env.DB, {
    id,
    agent_name: String(existing.agent_name),
    title: String(existing.title),
    description: String(existing.description),
    state: "completed",
    result: body.result ?? "",
    created_at: Number(existing.created_at),
  });

  return c.json({ ok: true, task_id: id, state: "completed" });
});

app.post("/tasks/:id/fail", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const id = c.req.param("id");
  const existing = await loadTask(c.env.DB, id);
  if (!existing) return c.json({ error: "Not found" }, 404);

  const body = await c.req.json<{ error: string }>();
  await saveTask(c.env.DB, {
    id,
    agent_name: String(existing.agent_name),
    title: String(existing.title),
    description: String(existing.description),
    state: "failed",
    error: body.error ?? "failed",
    created_at: Number(existing.created_at),
  });

  return c.json({ ok: true, task_id: id, state: "failed" });
});

app.get("/tasks", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const state = c.req.query("state");
  const limit = Math.min(parseInt(c.req.query("limit") ?? "20"), 100);

  let query = "SELECT id, agent_name, title, state, updated_at FROM a2a_tasks";
  const params: unknown[] = [];
  if (state) {
    query += " WHERE state = ?";
    params.push(state);
  }
  query += " ORDER BY updated_at DESC LIMIT ?";
  params.push(limit);

  const rows = await c.env.DB.prepare(query).bind(...params).all();
  return c.json({ tasks: rows.results ?? [] });
});

async function processQueueMessage(env: Env, message: QueueMessage): Promise<void> {
  const existing = await loadTask(env.DB, message.task_id);
  if (!existing) return;

  const state = String(existing.state);
  if (state !== "submitted") {
    return;
  }

  await saveTask(env.DB, {
      id: message.task_id,
      agent_name: message.agent_name,
      title: message.title,
      description: message.description,
      state: "working",
      metadata: {
        ...(existing.metadata as Record<string, unknown>),
        queued_at: Date.now(),
      },
      created_at: Number(existing.created_at),
    });

  const agentBase = (env.AGENT_WORKER_URL ?? "").replace(/\/$/, "");
  if (!env.AGENT_WORKER && !agentBase) return;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = env.AGENT_WORKER_TOKEN ?? env.API_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  const path = `/agents/${encodeURIComponent(message.agent_name)}/run`;
  const init: RequestInit = {
    method: "POST",
    headers,
    body: JSON.stringify({
      task: message.description,
      task_id: message.task_id,
    }),
  };

  const res = env.AGENT_WORKER
    ? await env.AGENT_WORKER.fetch(new Request(`https://agent.internal${path}`, init))
    : await fetch(`${agentBase}${path}`, init);

  if (!res.ok) {
    const errText = await res.text();
    await saveTask(env.DB, {
      id: message.task_id,
      agent_name: message.agent_name,
      title: message.title,
      description: message.description,
      state: "failed",
      metadata: {
        ...(existing.metadata as Record<string, unknown>),
        dispatch_error: errText.slice(0, 500),
      },
      created_at: Number(existing.created_at),
    });
  }
}

export default {
  fetch: app.fetch,
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processQueueMessage(env, message.body);
        message.ack();
      } catch {
        message.retry();
      }
    }
  },
};

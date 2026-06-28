import { DurableObject } from "cloudflare:workers";

export interface SpendEnv {
  API_TOKEN?: string;
}

export class SpendTracker extends DurableObject<SpendEnv> {
  constructor(ctx: DurableObjectState, env: SpendEnv) {
    super(ctx, env);
    ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS spend (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent TEXT NOT NULL,
        cost_usd REAL NOT NULL,
        task_id TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        provider TEXT NOT NULL DEFAULT '',
        ts INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_spend_agent_ts ON spend(agent, ts);
    `);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/record" && request.method === "POST") {
      const body = await request.json<{
        agent: string;
        cost_usd: number;
        task_id?: string;
        model?: string;
        provider?: string;
      }>();
      const ts = Date.now();
      this.ctx.storage.sql.exec(
        "INSERT INTO spend (agent, cost_usd, task_id, model, provider, ts) VALUES (?, ?, ?, ?, ?, ?)",
        body.agent,
        body.cost_usd,
        body.task_id ?? "",
        body.model ?? "",
        body.provider ?? "",
        ts,
      );
      return Response.json({ ok: true, agent: body.agent, cost_usd: body.cost_usd, ts });
    }

    if (url.pathname === "/check" && request.method === "GET") {
      const agent = url.searchParams.get("agent") ?? "";
      const limit = parseFloat(url.searchParams.get("limit") ?? "20");
      const since = Date.now() - 86_400_000;
      const row = this.ctx.storage.sql
        .exec(
          "SELECT COALESCE(SUM(cost_usd), 0) as spent FROM spend WHERE agent = ? AND ts > ?",
          agent,
          since,
        )
        .one<{ spent: number }>();
      const spent = row?.spent ?? 0;
      return Response.json({ ok: spent < limit, spent, limit, agent });
    }

    if (url.pathname === "/summary" && request.method === "GET") {
      const days = Math.min(parseInt(url.searchParams.get("days") ?? "1"), 30);
      const since = Date.now() - days * 86_400_000;
      const rows = this.ctx.storage.sql
        .exec(
          `SELECT agent,
                  COUNT(*) as tasks,
                  COALESCE(SUM(cost_usd), 0) as spent
           FROM spend
           WHERE ts > ?
           GROUP BY agent
           ORDER BY spent DESC`,
          since,
        )
        .toArray<{ agent: string; tasks: number; spent: number }>();

      const total = rows.reduce((sum, r) => sum + r.spent, 0);
      return Response.json({ days, total, agents: rows });
    }

    if (url.pathname === "/recent" && request.method === "GET") {
      const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20"), 100);
      const rows = this.ctx.storage.sql
        .exec(
          `SELECT agent, cost_usd, task_id, model, provider, ts
           FROM spend ORDER BY ts DESC LIMIT ?`,
          limit,
        )
        .toArray();
      return Response.json({ entries: rows });
    }

    return Response.json({ error: "not found" }, { status: 404 });
  }
}

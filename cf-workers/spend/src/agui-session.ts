import { DurableObject } from "cloudflare:workers";

const MAX_EVENTS = 200;

export class AGUISession extends DurableObject {
  constructor(ctx: DurableObjectState, env: unknown) {
    super(ctx, env);
    ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payload TEXT NOT NULL,
        ts INTEGER NOT NULL
      );
    `);
  }

  private persistEvent(payload: string): void {
    const ts = Date.now();
    this.ctx.storage.sql.exec("INSERT INTO events (payload, ts) VALUES (?, ?)", payload, ts);
    this.ctx.storage.sql.exec(
      `DELETE FROM events WHERE id NOT IN (
         SELECT id FROM events ORDER BY ts DESC LIMIT ?
       )`,
      MAX_EVENTS,
    );
  }

  private broadcast(message: string): void {
    for (const ws of this.ctx.getWebSockets()) {
      try {
        ws.send(message);
      } catch {
        // ignore closed sockets
      }
    }
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.headers.get("Upgrade") === "websocket") {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      this.ctx.acceptWebSocket(server);
      server.send(JSON.stringify({ type: "META", content: "connected", timestamp: Date.now() }));
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname === "/event" && request.method === "POST") {
      const event = await request.json();
      const message = JSON.stringify(event);
      this.persistEvent(message);
      this.broadcast(message);
      return Response.json({ ok: true });
    }

    if (url.pathname === "/events" && request.method === "GET") {
      const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "50"), MAX_EVENTS);
      const rows = this.ctx.storage.sql
        .exec("SELECT payload, ts FROM events ORDER BY ts DESC LIMIT ?", limit)
        .toArray<{ payload: string; ts: number }>();
      const events = rows.map((r) => JSON.parse(r.payload)).reverse();
      return Response.json({ events });
    }

    if (url.pathname === "/state" && request.method === "GET") {
      return Response.json({
        connections: this.ctx.getWebSockets().length,
        events: this.ctx.storage.sql.exec("SELECT COUNT(*) as n FROM events").one<{ n: number }>()?.n ?? 0,
      });
    }

    return Response.json({ error: "not found" }, { status: 404 });
  }

  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const text = typeof message === "string" ? message : new TextDecoder().decode(message);
    this.persistEvent(text);
    for (const peer of this.ctx.getWebSockets()) {
      if (peer !== ws) {
        peer.send(text);
      }
    }
  }

  async webSocketClose(ws: WebSocket): Promise<void> {
    ws.close();
  }
}

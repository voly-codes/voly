import { Hono } from "hono";
import { cors } from "hono/cors";

export interface Env {
  SPEND_TRACKER: DurableObjectNamespace;
  AGUI_SESSION: DurableObjectNamespace;
  API_TOKEN?: string;
}

function authorize(c: { req: { header: (name: string) => string | undefined }; env: Env }): boolean {
  const required = c.env.API_TOKEN;
  if (!required) return true;
  const header = c.req.header("Authorization") ?? "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === required;
}

async function spendStub(env: Env): Promise<DurableObjectStub> {
  return env.SPEND_TRACKER.get(env.SPEND_TRACKER.idFromName("global"));
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/health", (c) =>
  c.json({
    status: "ok",
    service: "codeops-spend",
    features: ["spend-tracker", "agui-session"],
  }),
);

app.post("/spend/record", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const body = await c.req.json();
  const stub = await spendStub(c.env);
  const resp = await stub.fetch(new Request("https://internal/record", { method: "POST", body: JSON.stringify(body) }));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.get("/spend/check", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const agent = c.req.query("agent") ?? "";
  const limit = c.req.query("limit") ?? "20";
  const stub = await spendStub(c.env);
  const resp = await stub.fetch(new Request(`https://internal/check?agent=${encodeURIComponent(agent)}&limit=${limit}`));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.get("/spend/summary", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const days = c.req.query("days") ?? "1";
  const stub = await spendStub(c.env);
  const resp = await stub.fetch(new Request(`https://internal/summary?days=${days}`));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.get("/spend/recent", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const limit = c.req.query("limit") ?? "20";
  const stub = await spendStub(c.env);
  const resp = await stub.fetch(new Request(`https://internal/recent?limit=${limit}`));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.post("/agui/sessions", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const body = await c.req.json<{ session_id?: string }>().catch(() => ({ session_id: undefined }));
  const sessionId = body.session_id ?? crypto.randomUUID();
  const base = new URL(c.req.url).origin;
  return c.json(
    {
      session_id: sessionId,
      ws_url: `${base}/agui/sessions/${sessionId}/ws`,
      events_url: `${base}/agui/sessions/${sessionId}/events`,
    },
    201,
  );
});

app.all("/agui/sessions/:id/ws", async (c) => {
  const id = c.req.param("id");
  const stub = c.env.AGUI_SESSION.get(c.env.AGUI_SESSION.idFromName(id));
  return stub.fetch(c.req.raw);
});

app.post("/agui/sessions/:id/events", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const id = c.req.param("id");
  const body = await c.req.json();
  const stub = c.env.AGUI_SESSION.get(c.env.AGUI_SESSION.idFromName(id));
  const resp = await stub.fetch(
    new Request("https://internal/event", { method: "POST", body: JSON.stringify(body) }),
  );
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.get("/agui/sessions/:id/events", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const id = c.req.param("id");
  const limit = c.req.query("limit") ?? "50";
  const stub = c.env.AGUI_SESSION.get(c.env.AGUI_SESSION.idFromName(id));
  const resp = await stub.fetch(new Request(`https://internal/events?limit=${limit}`));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

app.get("/agui/sessions/:id/state", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  const id = c.req.param("id");
  const stub = c.env.AGUI_SESSION.get(c.env.AGUI_SESSION.idFromName(id));
  const resp = await stub.fetch(new Request("https://internal/state"));
  return new Response(resp.body, { status: resp.status, headers: { "Content-Type": "application/json" } });
});

export default app;

export { SpendTracker } from "./spend-tracker";
export { AGUISession } from "./agui-session";

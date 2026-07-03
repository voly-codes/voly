import { Hono } from "hono";
import { cors } from "hono/cors";
import { buildBuiltinAgents } from "./definitions";
import { handleInfer } from "./infer";
import type { Env } from "./pipeline";
import { callPipelineRunner, completeA2ATask, getA2ATaskState } from "./pipeline";
import { VOLYMcpAgent } from "./mcp-agent";

function authorize(c: { req: { header: (name: string) => string | undefined }; env: Env }): boolean {
  const required = c.env.API_TOKEN;
  if (!required) return true;
  const header = c.req.header("Authorization") ?? "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === required;
}

const app = new Hono<{ Bindings: Env }>();

app.use("*", cors());

app.get("/health", (c) =>
  c.json({
    status: "ok",
    service: "voly-agent",
    pipeline_configured: Boolean(c.env.PIPELINE_RUNNER_URL),
    a2a_callback_configured: Boolean(c.env.A2A_FEDERATION ?? c.env.A2A_FEDERATION_URL),
    a2a_callback_token_configured: Boolean(c.env.A2A_FEDERATION_TOKEN ?? c.env.API_TOKEN),
    ai_configured: Boolean(c.env.AI),
    mcp: "/mcp",
  }),
);

// Workers AI inference — accepts task + optional local context, returns code blocks.
// The Python WranglerExecutor calls this and passes the response to LocalPatchApplier.
app.post("/infer", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);
  return handleInfer(c.req.raw, c.env);
});

app.get("/agents", (c) => {
  const baseUrl = new URL(c.req.url).origin;
  return c.json({ agents: buildBuiltinAgents(baseUrl) });
});

app.get("/agents/:name/card", (c) => {
  const baseUrl = new URL(c.req.url).origin;
  const card = buildBuiltinAgents(baseUrl).find((a) => a.name === c.req.param("name"));
  if (!card) return c.json({ error: "Agent not found" }, 404);
  return c.json(card);
});

app.get("/agents/:name/.well-known/agent-card.json", (c) => {
  const target = new URL(c.req.url);
  target.pathname = `/agents/${c.req.param("name")}/card`;
  return c.redirect(target.toString(), 307);
});

app.post("/agents/:name/run", async (c) => {
  if (!authorize(c)) return c.json({ error: "Unauthorized" }, 401);

  const agentName = c.req.param("name");
  const body = await c.req.json<{ task: string; cwd?: string; task_id?: string }>();
  if (!body.task) return c.json({ error: "task required" }, 400);

  if (body.task_id) {
    const state = await getA2ATaskState(c.env, body.task_id);
    if (state === "completed" || state === "failed") {
      return c.json({
        agent: agentName,
        success: state === "completed",
        skipped: true,
        state,
        error: state === "failed" ? "task already failed" : undefined,
      });
    }
  }

  const result = await callPipelineRunner(c.env, {
    agent: agentName,
    task: body.task,
    cwd: body.cwd,
    task_id: body.task_id,
  });

  if (body.task_id) {
    await completeA2ATask(c.env, body.task_id, result);
  }

  return c.json({ agent: agentName, ...result });
});

const mcpHandler = VOLYMcpAgent.serve("/mcp", { binding: "CODEOPS_MCP_AGENT" });

export default {
  fetch(request: Request, env: Env, ctx: ExecutionContext): Response | Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/mcp" || url.pathname.startsWith("/mcp/")) {
      return mcpHandler.fetch(request, env, ctx);
    }
    return app.fetch(request, env, ctx);
  },
};

export { VOLYMcpAgent };

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpAgent } from "agents/mcp";
import { z } from "zod";
import type { Env } from "./pipeline";
import { callPipelineRunner } from "./pipeline";

export class VOLYMcpAgent extends McpAgent<Env> {
  server = new McpServer({ name: "voly-agent", version: "1.0.0" });

  async init() {
    this.server.registerTool(
      "run_task",
      {
        description:
          "Execute a task via the local VOLY pipeline (Cursor/Claude Code). Secrets and repo stay on the pipeline host.",
        inputSchema: {
          agent: z.string().describe("Agent role: developer, architect, reviewer, tester, bugfixer, devops, security"),
          task: z.string().describe("Task description"),
          cwd: z.string().optional().describe("Working directory on the pipeline host"),
          task_id: z.string().optional().describe("Optional A2A federation task id"),
        },
      },
      async ({ agent, task, cwd, task_id }) => {
        const result = await callPipelineRunner(this.env, { agent, task, cwd, task_id });
        const text = result.success
          ? (result.response ?? "completed")
          : (result.error ?? "pipeline failed");
        return { content: [{ type: "text", text }] };
      },
    );
  }
}

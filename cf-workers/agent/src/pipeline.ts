export interface Env {
  PIPELINE_RUNNER_URL?: string;
  PIPELINE_RUNNER_TOKEN?: string;
  API_TOKEN?: string;
  A2A_FEDERATION?: Fetcher;
  A2A_FEDERATION_URL?: string;
  A2A_FEDERATION_TOKEN?: string;
  // Workers AI binding — available when [ai] is declared in wrangler.jsonc
  AI?: Ai;
  // CF AI Gateway — set these to route /infer calls through the gateway route schema
  // instead of env.AI.run() directly. Configure routes in CF Dashboard → AI Gateway.
  CF_ACCOUNT_ID?: string;
  CF_GATEWAY_ID?: string;
  CF_AIG_TOKEN?: string;
}

export interface PipelineRunRequest {
  agent: string;
  task: string;
  cwd?: string;
  task_id?: string;
}

export interface PipelineRunResponse {
  success: boolean;
  response?: string;
  error?: string;
  agent?: string;
  duration_ms?: number;
}

export async function callPipelineRunner(
  env: Env,
  params: PipelineRunRequest,
): Promise<PipelineRunResponse> {
  const base = (env.PIPELINE_RUNNER_URL ?? "").replace(/\/$/, "");

  // No PIPELINE_RUNNER_URL → execute directly via CF AI Gateway (no tunnel needed)
  if (!base) {
    const { handleInfer } = await import("./infer");
    const req = new Request("https://internal/infer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: params.task, agent: params.agent }),
    });
    const resp = await handleInfer(req, env);
    const data = await resp.json<{ success: boolean; content: string; error?: string }>();
    return {
      success: data.success,
      response: data.content,
      error: data.error,
      agent: params.agent,
    };
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (env.PIPELINE_RUNNER_TOKEN) {
    headers.Authorization = `Bearer ${env.PIPELINE_RUNNER_TOKEN}`;
  }

  const res = await fetch(`${base}/run`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agent: params.agent,
      task: params.task,
      cwd: params.cwd,
      task_id: params.task_id,
      a2a_parent_task_id: params.task_id,
    }),
  });

  const text = await res.text();
  try {
    return JSON.parse(text) as PipelineRunResponse;
  } catch {
    return { success: res.ok, response: text, error: res.ok ? undefined : text };
  }
}

export async function getA2ATaskState(
  env: Env,
  taskId: string,
): Promise<string | null> {
  if (!taskId) return null;
  if (!env.A2A_FEDERATION && !(env.A2A_FEDERATION_URL ?? "").replace(/\/$/, "")) return null;

  const headers: Record<string, string> = { Accept: "application/json" };
  const token = env.A2A_FEDERATION_TOKEN ?? env.API_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  const path = `/tasks/${taskId}`;
  const init: RequestInit = { method: "GET", headers };

  try {
    const res = env.A2A_FEDERATION
      ? await env.A2A_FEDERATION.fetch(new Request(`https://a2a.internal${path}`, init))
      : await fetch(`${(env.A2A_FEDERATION_URL ?? "").replace(/\/$/, "")}${path}`, init);

    if (!res.ok) return null;
    const data = await res.json<{ state?: string }>();
    return data.state ?? null;
  } catch {
    return null;
  }
}

export async function completeA2ATask(
  env: Env,
  taskId: string,
  result: PipelineRunResponse,
): Promise<void> {
  if (!taskId) return;
  if (!env.A2A_FEDERATION && !(env.A2A_FEDERATION_URL ?? "").replace(/\/$/, "")) return;

  const path = result.success ? `/tasks/${taskId}/complete` : `/tasks/${taskId}/fail`;
  const body = result.success
    ? { result: result.response ?? "" }
    : { error: result.error ?? "pipeline failed" };

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = env.A2A_FEDERATION_TOKEN ?? env.API_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  const init: RequestInit = { method: "POST", headers, body: JSON.stringify(body) };

  try {
    const res = env.A2A_FEDERATION
      ? await env.A2A_FEDERATION.fetch(new Request(`https://a2a.internal${path}`, init))
      : await fetch(`${(env.A2A_FEDERATION_URL ?? "").replace(/\/$/, "")}${path}`, init);

    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      console.error(`completeA2ATask ${path} → HTTP ${res.status}: ${detail.slice(0, 500)}`);
    }
  } catch (err) {
    console.error(`completeA2ATask ${path} → fetch failed:`, err);
  }
}

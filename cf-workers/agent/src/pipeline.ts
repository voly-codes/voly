export interface Env {
  PIPELINE_RUNNER_URL?: string;
  PIPELINE_RUNNER_TOKEN?: string;
  API_TOKEN?: string;
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
  if (!base) {
    return {
      success: false,
      error: "PIPELINE_RUNNER_URL not configured — run `codeops serve` locally and set tunnel URL",
    };
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (env.PIPELINE_RUNNER_TOKEN) {
    headers.Authorization = `Bearer ${env.PIPELINE_RUNNER_TOKEN}`;
  }

  const res = await fetch(`${base}/run`, {
    method: "POST",
    headers,
    body: JSON.stringify(params),
  });

  const text = await res.text();
  try {
    return JSON.parse(text) as PipelineRunResponse;
  } catch {
    return { success: res.ok, response: text, error: res.ok ? undefined : text };
  }
}

export async function completeA2ATask(
  env: Env,
  taskId: string,
  result: PipelineRunResponse,
): Promise<void> {
  const base = (env.A2A_FEDERATION_URL ?? "").replace(/\/$/, "");
  if (!base || !taskId) return;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = env.A2A_FEDERATION_TOKEN ?? env.API_TOKEN;
  if (token) headers.Authorization = `Bearer ${token}`;

  const path = result.success ? `/tasks/${taskId}/complete` : `/tasks/${taskId}/fail`;
  const body = result.success
    ? { result: result.response ?? "" }
    : { error: result.error ?? "pipeline failed" };

  await fetch(`${base}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
}

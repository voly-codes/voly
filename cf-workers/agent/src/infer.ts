/**
 * Workers AI inference via CF AI Gateway route schema.
 *
 * Instead of calling env.AI.run() directly, this module routes through the
 * CF AI Gateway /compat endpoint using the route schema configured in the
 * CF Dashboard (AI Gateway → {gatewayId} → Routing).
 *
 * Route schema (configured in CF Dashboard):
 *   START → primary-model (anthropic/claude or openai/gpt-4o, timeout 3s, retries 3)
 *         → fallback-model (workers-ai/@cf/moonshotai/kimi-k2.7-code)
 *         → END
 *
 * When called with model="dynamic/ai_route", CF AI Gateway applies the route
 * schema: tries primary first, falls back to workers-ai on timeout/error.
 *
 * The /compat endpoint is OpenAI-compatible — same request/response format.
 *
 * Code-change format the model is instructed to output:
 *
 *   ### FILE: path/relative/to/cwd.ext
 *   ```lang
 *   ...full file content...
 *   ```
 *
 * Python LocalPatchApplier parses these blocks and writes them to disk.
 */

import type { Env } from "./pipeline";

export interface InferRequest {
  task: string;
  /** Pre-gathered local context (file snippets, grep hits). */
  context?: string;
  /** Override model. Default: "dynamic/ai_route" (uses CF route schema). */
  model?: string;
  system?: string;
  max_tokens?: number;
}

export interface InferResponse {
  success: boolean;
  content: string;
  model: string;
  provider?: string;
  error?: string;
  input_tokens?: number;
  output_tokens?: number;
}

// Route name matches CF Dashboard: AI Gateway → {gatewayId} → Routing → route name
const DYNAMIC_ROUTE = "dynamic/ai_route";

const FILE_SYSTEM_PROMPT = `You are a senior software engineer. When asked to create or modify code:

1. Output EVERY file that needs to be created or changed using this exact format:

### FILE: path/relative/to/project/root.ext
\`\`\`language
...complete file content...
\`\`\`

2. Use the relative path from the project root (e.g. src/auth/login.py).
3. Output the COMPLETE file content — never truncate with "..." or "rest of file unchanged".
4. If no files need to change (e.g. the task is a question), answer in plain text without FILE blocks.
5. After the FILE blocks, write a brief summary of what was changed and why.`;


export async function handleInfer(request: Request, env: Env): Promise<Response> {
  let body: InferRequest;
  try {
    body = await request.json<InferRequest>();
  } catch {
    return Response.json({ success: false, error: "invalid JSON body", content: "" }, { status: 400 });
  }
  if (!body.task) {
    return Response.json({ success: false, error: "task is required", content: "" }, { status: 400 });
  }

  const model = body.model ?? DYNAMIC_ROUTE;
  const systemPrompt = body.system ?? FILE_SYSTEM_PROMPT;
  const userContent = body.context ? `${body.task}\n\n${body.context}` : body.task;

  const messages = [
    { role: "system", content: systemPrompt },
    { role: "user",   content: userContent },
  ];

  // Try CF AI Gateway route schema first (uses primary + fallback from CF Dashboard config).
  // Falls back to env.AI direct call if gateway is not configured.
  const gatewayResult = await _callViaGateway(env, model, messages, body.max_tokens ?? 4096);
  if (gatewayResult !== null) return gatewayResult;

  // Fallback: direct env.AI binding (no route schema, single model)
  return _callViaBinding(env, model, messages, body.max_tokens ?? 4096);
}


async function _callViaGateway(
  env: Env,
  model: string,
  messages: { role: string; content: string }[],
  maxTokens: number,
): Promise<Response | null> {
  const accountId = env.CF_ACCOUNT_ID;
  const gatewayId = env.CF_GATEWAY_ID || "default";
  const aigToken   = env.CF_AIG_TOKEN;

  if (!accountId || !aigToken) return null;  // not configured → fall through to binding

  const url = `https://gateway.ai.cloudflare.com/v1/${accountId}/${gatewayId}/compat/chat/completions`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "cf-aig-authorization": `Bearer ${aigToken}`,
    "User-Agent": "CodeOps-Worker/0.1",
  };

  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ model, messages, max_tokens: maxTokens }),
    });

    const data = await res.json() as {
      choices?: { message?: { content?: string } }[];
      model?: string;
      usage?: { prompt_tokens?: number; completion_tokens?: number };
      error?: { message?: string };
    };

    if (!res.ok || data.error) {
      const errMsg = data.error?.message ?? `HTTP ${res.status}`;
      return Response.json(
        { success: false, error: `CF AI Gateway: ${errMsg}`, content: "", model } satisfies InferResponse,
        { status: 502 },
      );
    }

    const content = data.choices?.[0]?.message?.content ?? "";
    return Response.json({
      success: true,
      content,
      model: data.model ?? model,
      provider: "cf-ai-gateway",
      input_tokens:  data.usage?.prompt_tokens,
      output_tokens: data.usage?.completion_tokens,
    } satisfies InferResponse);

  } catch (err) {
    // Network error → fall through to env.AI binding
    console.warn("CF AI Gateway call failed, falling back to env.AI:", err);
    return null;
  }
}


async function _callViaBinding(
  env: Env,
  model: string,
  messages: { role: string; content: string }[],
  maxTokens: number,
): Promise<Response> {
  if (!env.AI) {
    return Response.json(
      {
        success: false,
        error: "No inference available: CF AI Gateway not configured (CF_ACCOUNT_ID/CF_AIG_TOKEN missing) and AI binding not present. Set CF_ACCOUNT_ID + CF_AIG_TOKEN in wrangler.jsonc [vars] or use a specific non-dynamic model.",
        content: "",
        model,
      } satisfies InferResponse,
      { status: 503 },
    );
  }

  // Direct binding doesn't support dynamic routing — use a concrete model
  const bindingModel = model.startsWith("dynamic/")
    ? "@cf/meta/llama-4-scout-17b-16e-instruct"
    : model;

  try {
    const result = await env.AI.run(
      bindingModel as BaseAiTextGenerationModels,
      { messages, max_tokens: maxTokens } as AiTextGenerationInput,
    ) as AiTextGenerationOutput;

    let content = "";
    if (typeof result === "object" && result !== null) {
      if ("response" in result && typeof result.response === "string") {
        content = result.response;
      } else if ("choices" in result && Array.isArray(result.choices)) {
        content = (result.choices[0] as { message?: { content?: string } })?.message?.content ?? "";
      }
    }

    return Response.json({
      success: true,
      content,
      model: bindingModel,
      provider: "workers-ai-binding",
    } satisfies InferResponse);

  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return Response.json(
      { success: false, error: msg, content: "", model: bindingModel } satisfies InferResponse,
      { status: 502 },
    );
  }
}

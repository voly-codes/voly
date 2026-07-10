# AI Gateway — Backend Reference

AI Gateway is the single entry point for all LLM requests. `Pipeline` and DSPy
talk only through `AIGateway.chat()`. Executors may bypass (they launch
subprocesses directly), but WranglerExecutor also goes through CF AI Gateway
(via the route in CF Dashboard).

---

## Middleware stack

```
AIGateway.chat(messages, agent, model)
    ↓
DLP scan → Cache check → Rate limit → Spend limit → Routing → Provider → Empty-content guard
```

1. **DLP** — blocks secrets/PII, returns `{"dlp_blocked": true}`
2. **Cache** — exact/semantic hit → `{"cache_hit": true}`, quota is not spent; the key includes **project-state scope** (see “Cache validity boundaries”)
3. **Rate limit** — rpm guard → `{"rate_limited": true}`
4. **Spend limit** — daily budget → `{"spend_limited": true}`; after the response
   `spend_limit.record()` is called **only on success** (no `error`).
   If `usage` is present, usage-based cost is written; otherwise — the pre-call estimate.
5. **Routing** — CF AI Gateway or direct call, then model fallback
6. **Empty-content guard** — fake success (HTTP 200 with no content) → synthetic error → model fallback

---

## Providers

| Provider | Via CF Gateway | Direct |
|---|---|---|
| `anthropic` | yes | no |
| `openai` | yes | no |
| `google-ai-studio` | yes | no |
| `deepseek` | yes | no |
| `workers-ai` | yes (via `/compat`) | env.AI binding |
| `mimo` | no | yes (CUSTOM) |
| `opencode-zen` | no | yes (CUSTOM) |
| `opencode-go` | no | yes (CUSTOM) |
| `omniroute` | no | yes (CUSTOM, opt-in) |

Switching `GatewayProvider.CLOUDFLARE` vs `CUSTOM` — in `voly/ai_gateway/`.

### OmniRoute (upstream)

`omniroute` is a self-hosted OpenAI-compatible gateway (237+ providers, free tiers,
auto-fallback, compression). VOLY sees it as **one** upstream and delegates all
routing/fallback to OmniRoute itself (`_call_omniroute` → `<base>/v1/chat/completions`).

Two usage modes:

1. **Opt-in provider:** not in the default `_TASK_PROVIDERS` chains; selected
   explicitly (provider `omniroute`) so an unstarted local gateway does not enter fallback.
2. **First-class upstream (layer A delegation):** `ai_gateway.upstream: "omniroute"`
   in `voly.yaml` → all non-CF `chat()` calls go through OmniRoute first
   (`AIGateway._delegated_or_direct`). Model is the caller’s passthrough, or
   `upstream_model: "auto"` (auto-combo). On upstream error/unavailability —
   `metrics.record_fallback()` and automatic fallback to the direct adapter of
   the requested provider (`upstream_fallback_direct: true`, default): a dead
   local gateway does not block the pipeline. Response markers: success via upstream —
   `result["upstream"]="omniroute"`, response after fallback — `result["upstream_fallback"]=true`.
   An explicit call with provider=`omniroute` is not re-wrapped as a second hop. Cache, DLP,
   spend limits, and telemetry are unchanged — they live around the call. Tests:
   `tests/test_ai_gateway.py` (“Upstream delegation”).

- **Model `auto`** triggers OmniRoute auto-combo routing.
- **Cost:** computed from the actual model returned by OmniRoute (`data.model`);
  free-tier routing → $0. There is no separate provider rate in `_COST_RATES`.

Env: `OMNIROUTE_BASE_URL` (default `http://localhost:20128`), `OMNIROUTE_API_KEY`
(optional), `OMNIROUTE_COMBO` (optional → `X-Omni-Combo` header).

---

## CF AI Gateway route schema

Configured in CF Dashboard → AI Gateway → {gateway} → Routing.

Example schema:
```json
[
  {
    "name": "Primary (Anthropic)",
    "type": "model",
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "timeout_ms": 10000,
    "retries": 3
  },
  {
    "name": "Fallback (Workers AI)",
    "type": "model",
    "provider": "workers-ai",
    "model": "@cf/moonshotai/kimi-k2.7-code"
  }
]
```

**For Pipeline / AIGateway.chat():** the schema is applied automatically via CF Gateway.

**For WranglerExecutor / `/infer` endpoint:** `infer.ts` calls:
```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat/chat/completions
model = "dynamic/ai_route"
```
If `CF_ACCOUNT_ID` + `CF_AIG_TOKEN` are not set — fallback to `env.AI.run()` directly.

---

## Env vars for CF AI Gateway

```env
CF_ACCOUNT_ID=073ae0130b7cee5e55a1ac1a335431a8
CF_GATEWAY_ID=default
CF_AIG_TOKEN=<token from CF Dashboard → AI Gateway → Settings>
```

For Workers AI via wrangler dev, set in `cf-workers/agent/wrangler.jsonc` → `[vars]`.

---

## Model fallback in AIGateway

When the primary model returns an error, the Gateway automatically tries the next
in the `fallback_models` list from config. This is separate from the billing fallback chain in
AgentRunner (which switches the whole executor, not just the model).

Terminal-billing text classification (`is_terminal_billing_error`, `"402"`/`"billing"`
signals) is documented in `docs/backend/executors.md` under "Billing fallback chain" —
it requires HTTP-status-style framing or a specific billing phrase, not a bare
substring match, to avoid misclassifying unrelated errors as billing failures.

## Cache validity boundaries (risk R1)

Code generation is sensitive to repository state: the same prompt on a changed
codebase must produce a different answer. Therefore the cache key, in addition to `messages` /
`model` / `provider` / `system`, includes **project-state scope** — a fingerprint of
project state.

- **What provides the scope:** `voly/ai_gateway/project_state.py:project_fingerprint(cwd, files=None)`.
  Repo-level by default: git `HEAD` + signature of the “dirty” working tree
  (`git diff HEAD` + untracked → re-editing the same file
  invalidates the cache without a file list). Non-git directory → identity by path.
  Optional `files=[...]` adds mtime+size+content of specific files
  (file-level precision; hook for the local-context path).
- **How it is wired:** the instance attribute `AIGateway.cache_scope` is set once
  when the gateway is created from `config.default_cwd` (`pipeline/core.py`), so
  all `chat()` calls on that instance inherit the scope without per-call plumbing. Per-call
  parameter `chat(..., cache_scope=...)` overrides the instance value. Empty → scope
  is not used (pre-R1 behavior).
- **What scope prevents:** cross-project collision (same task text on another
  `cwd` → wrong cache hit) and stale hit after repository changes.

**Executor path is outside this cache.** Executor subprocesses (`claude-code`, `zen`,
`cursor`) read and write files directly and **do not** go through `AIGateway.cache`;
`wrangler` goes through a separate `/infer` (CF Worker), not this cache. So
`AIGateway.cache` only serves text-only reasoning (pipeline, sub-agents,
DSPy) — that is exactly where scope is needed. Executor results are not cached anywhere.

## Empty-content guard

A provider may return HTTP 200 with no useful content (`content: ""`) — a “fake success”
that would otherwise reach the user as an empty answer. `AIGateway._empty_content_error`
converts such a response into a synthetic error (`{"empty_content": true, "error": ...}`),
and it goes into normal **model fallback** (in `_gateway_call`, `chat()`-direct, and `_direct_fallback`).

**What is NOT treated as fake success** (passed through without fallback): empty content with a legitimate
terminal stop — `stop_reason` `max_tokens`/`tool_use` (Claude) or `finish_reason`
`length`/`tool_calls` (OpenAI). For this, provider adapters in `providers.py` pass through
`stop_reason` into the normalized result, and detection lives in
`is_empty_content_response` (`voly/ai_gateway/error_classifier.py`).

This is a **model-level** signal: `empty_content` is NOT in `TERMINAL_BILLING_TYPES`, so
it never switches the executor via the billing chain — only the next model.

---

## Pricing / cost

The single source of truth is `_COST_RATES` in `voly/telemetry.py`.
When adding a new provider, update it there as well.

---

## Adding a new provider

1. Add to `voly/ai_gateway/` — adapter for the new LLM API
2. Update `GatewayProvider` and routing in `voly/ai_gateway/`
3. Add `_COST_RATES[provider]` in `voly/telemetry.py`
4. Update `voly.yaml` defaults
5. Update `.env.example`
6. Update this file and `docs/ARCHITECTURE.md`

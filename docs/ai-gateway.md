# AI Gateway

> **Canonical document:** [`docs/backend/ai-gateway.md`](backend/ai-gateway.md)
> This file has baseline information; the full description including CF AI Gateway
> route schema, CF_AIG_TOKEN, WranglerExecutor is in `docs/backend/ai-gateway.md`.

---

## Why the Gateway is needed

AI Gateway is the single entry point for all agent LLM requests. Every call in VOLY goes only through it: `Pipeline` never talks to providers directly.

What the gateway provides:
- **DLP** — blocks secrets and PII in prompts before send
- **Cache** — returns a cached response on repeated requests
- **Rate limiting** — burst protection, rpm limits
- **Spend limits** — daily USD budget, global and per-agent
- **Model fallback** — automatic reserve model chain
- **Metrics** — by provider, model, agent

## Middleware stack

Every `gateway.chat()` call goes through the stack in fixed order:

```
DLP scan → Cache check → Rate limit → Spend limit → [LLM call]
```

1. **DLP** — if secrets/PII are found, returns `{"dlp_blocked": true}`; further layers are not called
2. **Cache** — on hit, returns cache (`{"cache_hit": true}`); quota is not spent
3. **Rate limit** — checks requests-per-minute; on exceed `{"rate_limited": true}`
4. **Spend limit** — checks daily budget; on exceed `{"spend_limited": true}`
5. **Routing** — chooses CF Gateway or direct call, performs the request

## Routing: infrastructure providers vs LLM providers

The gateway distinguishes two levels:

1. **Infrastructure provider** (`GatewayProvider`): `CLOUDFLARE` or `CUSTOM` — which API layer the request goes through.
2. **LLM provider** — the concrete model service: Anthropic, OpenAI, Google, DeepSeek, MiMo, OpenCode Zen/GO.

```python
# voly/ai_gateway/models.py
class GatewayProvider(Enum):
    CLOUDFLARE = "cloudflare"
    CUSTOM = "custom"
```

Routed via Cloudflare AI Gateway: Anthropic, OpenAI, Google AI Studio, DeepSeek.
Direct (CUSTOM): MiMo, OpenCode GO, OpenCode Zen.

```python
_CF_PROVIDERS = frozenset({"anthropic", "openai", "google-ai-studio", "deepseek"})

if cloudflare_enabled and provider_name in _CF_PROVIDERS:
    # → Cloudflare AI Gateway → provider API
else:
    # → direct provider API call
```

`cloudflare_enabled` = True when `enabled=True` AND `account_id` is set.

## Provider table

| Provider | Route | Environment variable | Base URL |
|-----------|---------|---------------------|-------------|
| `anthropic` | CF Gateway | `ANTHROPIC_API_KEY` | via CF |
| `openai` | CF Gateway | `OPENAI_API_KEY` | via CF |
| `google-ai-studio` | CF Gateway | `GOOGLE_API_KEY` | via CF |
| `deepseek` | CF Gateway | `DEEPSEEK_API_KEY` | via CF |
| `mimo` | Direct (OpenAI-compat) | `MIMO_API_KEY` | `MIMO_BASE_URL_OPENAI` |
| `mimo-anthropic` | Direct (Anthropic-compat) | `MIMO_API_KEY` | `MIMO_BASE_URL_ANTHROPIC` |
| `opencode` | Direct → opencode.ai/zen/go | `OPENCODE_API_KEY` | `OPENCODE_BASE_URL` |
| `opencode-zen` | Direct → opencode.ai/zen | `OPENCODE_API_KEY` | `OPENCODE_ZEN_BASE_URL` |

**CF variables:**
```
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_AI_GATEWAY_ID
CLOUDFLARE_API_TOKEN
```

## Configuration in `voly.yaml`

```yaml
ai_gateway:
  enabled: true
  provider: cloudflare
  account_id: "${CLOUDFLARE_ACCOUNT_ID}"
  gateway_id: "${CLOUDFLARE_AI_GATEWAY_ID}"
  api_token: "${CLOUDFLARE_API_TOKEN}"

  caching:
    enabled: true
    ttl_seconds: 3600      # entry TTL
    max_entries: 1000      # max in-memory entries

  rate_limits:
    enabled: true
    requests_per_minute: 60

  spend_limits:
    enabled: true
    daily_budget_usd: 20.0
    per_agent_budget:      # optional per-agent limit
      architect: 5.0
      developer: 10.0

  fallback:
    enabled: true
    retries: 3
    chain:
      - provider: openai
        model: gpt-4o-mini
      - provider: anthropic
        model: claude-haiku-4-5

  dlp:
    enabled: false          # enable if leak protection is needed
    block_secrets: true     # API keys, JWT, SSH keys
    block_pii: true         # email, SSN, card numbers
```

## Fallback chain setup example

Goal: if the primary model is unavailable, try a cheaper alternative.

```yaml
fallback:
  enabled: true
  retries: 3
  chain:
    - provider: openai
      model: gpt-4o-mini
    - provider: deepseek
      model: deepseek-chat
    - provider: opencode-zen
      model: claude-haiku-4-5
```

On each error the gateway moves to the next chain element. The `fallbacks_used` metric increases on every switch.

## Metrics (`voly ai-gateway status`)

```
AI Gateway: cloudflare
Enabled: True
Gateway: voly-gateway

Cache:       {'enabled': True, 'ttl_seconds': 3600, 'max_entries': 1000}
Rate limits: {'requests_per_minute': 60, 'enabled': True}
Spend limits: {'daily_budget_usd': 20.0, 'spent_today': 1.24, 'enabled': True}
Fallback chain: 2 models

Metrics: {
  "total_requests": 143,
  "total_tokens": 284000,
  "total_cost_usd": 1.24,
  "cache_hits": 27,
  "cache_misses": 116,
  "fallbacks_used": 3,
  "dlp_blocks": 0,
  "errors": 2,
  "by_provider": {"anthropic": 89, "deepseek": 54},
  "rpm": 4
}
```

## DLP — detectable patterns

**Secrets:**
- `api_key: sk-...`, `token = "..."`, `password = "..."`
- JWT tokens (`eyJ...`)
- OpenAI keys (`sk-[A-Za-z0-9]{12,}`)
- GitHub PAT (`ghp_...`)
- Slack tokens (`xox[baprs]-...`)
- SSH private keys

**PII:**
- SSN: `123-45-6789`
- Card numbers: 16 digits
- Email addresses

When any pattern is found the request is blocked and returns:
```json
{"dlp_blocked": true, "error": "DLP blocked: [...]", "content": ""}
```

## Programmatic access

```python
from voly.ai_gateway import AIGateway

gw = AIGateway(
    account_id="...",
    gateway_id="voly-gateway",
    api_token="...",
)

# Configure spend limits per-agent
gw.spend_limit.per_agent_budget["architect"] = 5.0

# Configure fallback
gw.fallback.chain = [
    {"provider": "openai", "model": "gpt-4o-mini"},
    {"provider": "deepseek", "model": "deepseek-chat"},
]

# Enable DLP
gw.dlp.enabled = True

# Call
result = gw.chat(
    messages=[{"role": "user", "content": "Explain SOLID"}],
    model="claude-sonnet-4-5-20250929",
    provider_name="anthropic",
    max_tokens=1024,
    agent="developer",   # for per-agent spend tracking
)

print(result["content"])
print(result.get("cache_hit"))    # True if from cache
print(result.get("dlp_blocked"))  # True if blocked by DLP
print(gw.metrics.to_dict())
```

> **Status**: implemented. Cache, DLP, Rate/Spend limits, Fallback work. CF routing requires `CLOUDFLARE_ACCOUNT_ID`. Without it, requests go directly to providers.

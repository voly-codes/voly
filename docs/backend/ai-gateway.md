# AI Gateway — Backend Reference

AI Gateway — единая точка входа для всех LLM-запросов. `Pipeline` и DSPy
обращаются только через `AIGateway.chat()`. Executors могут bypass (они запускают
субпроцессы напрямую), но WranglerExecutor тоже проходит через CF AI Gateway
(через маршрут в CF Dashboard).

---

## Middleware стек

```
AIGateway.chat(messages, agent, model)
    ↓
DLP scan → Cache check → Rate limit → Spend limit → Routing → Provider
```

1. **DLP** — блокирует secrets/PII, возвращает `{"dlp_blocked": true}`
2. **Cache** — exact/semantic hit → `{"cache_hit": true}`, квота не тратится
3. **Rate limit** — rpm guard → `{"rate_limited": true}`
4. **Spend limit** — дневной бюджет → `{"spend_limited": true}`
5. **Routing** — CF AI Gateway или прямой вызов, затем model fallback

---

## Провайдеры

| Provider | Via CF Gateway | Direct |
|---|---|---|
| `anthropic` | yes | no |
| `openai` | yes | no |
| `google-ai-studio` | yes | no |
| `deepseek` | yes | no |
| `workers-ai` | yes (через `/compat`) | env.AI binding |
| `mimo` | no | yes (CUSTOM) |
| `opencode-zen` | no | yes (CUSTOM) |
| `opencode-go` | no | yes (CUSTOM) |
| `omniroute` | no | yes (CUSTOM, opt-in) |

Переключение `GatewayProvider.CLOUDFLARE` vs `CUSTOM` — в `codeops/ai_gateway/`.

### OmniRoute (opt-in upstream)

`omniroute` — self-hosted OpenAI-совместимый gateway (237+ провайдеров, free tiers,
auto-fallback, компрессия). CodeOps видит его как **один** upstream и делегирует всю
маршрутизацию/фолбэк самому OmniRoute (`_call_omniroute` → `<base>/v1/chat/completions`).

- **Opt-in:** не входит в default `_TASK_PROVIDERS`-цепочки; выбирается явно
  (provider `omniroute`), чтобы незапущенный локальный gateway не попадал в fallback.
- **Модель `auto`** запускает auto-combo роутинг OmniRoute.
- **Cost:** считается по фактической модели, которую вернул OmniRoute (`data.model`);
  при free-tier роутинге → $0. Отдельной ставки под провайдер в `_COST_RATES` нет.

Env: `OMNIROUTE_BASE_URL` (default `http://localhost:20128`), `OMNIROUTE_API_KEY`
(опц.), `OMNIROUTE_COMBO` (опц. → заголовок `X-Omni-Combo`).

---

## CF AI Gateway route schema

Настраивается в CF Dashboard → AI Gateway → {gateway} → Routing.

Пример схемы:
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

**Для Pipeline / AIGateway.chat():** схема применяется автоматически через CF Gateway.

**Для WranglerExecutor / `/infer` endpoint:** `infer.ts` вызывает:
```
https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat/chat/completions
model = "dynamic/ai_route"
```
Если `CF_ACCOUNT_ID` + `CF_AIG_TOKEN` не заданы — fallback на `env.AI.run()` напрямую.

---

## Env vars для CF AI Gateway

```env
CF_ACCOUNT_ID=073ae0130b7cee5e55a1ac1a335431a8
CF_GATEWAY_ID=default
CF_AIG_TOKEN=<token from CF Dashboard → AI Gateway → Settings>
```

Для Workers AI через wrangler dev задаются в `cf-workers/agent/wrangler.jsonc` → `[vars]`.

---

## Model fallback в AIGateway

Когда основная модель возвращает ошибку, Gateway автоматически пробует следующую
в списке `fallback_models` из конфига. Это отдельно от billing fallback chain в
AgentRunner (которая переключает целый executor, не только модель).

---

## Pricing / cost

Единственный источник правды — `_COST_RATES` в `codeops/telemetry.py`.
При добавлении нового провайдера обновляй его там же.

---

## Добавить нового провайдера

1. Добавить в `codeops/ai_gateway/` — адаптер для нового LLM API
2. Обновить `GatewayProvider` и роутинг в `codeops/ai_gateway/`
3. Добавить `_COST_RATES[provider]` в `codeops/telemetry.py`
4. Обновить `codeops.yaml` defaults
5. Обновить `.env.example`
6. Обновить этот файл и `docs/ARCHITECTURE.md`

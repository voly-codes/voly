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
DLP scan → Cache check → Rate limit → Spend limit → Routing → Provider → Empty-content guard
```

1. **DLP** — блокирует secrets/PII, возвращает `{"dlp_blocked": true}`
2. **Cache** — exact/semantic hit → `{"cache_hit": true}`, квота не тратится; ключ включает **project-state scope** (см. «Границы валидности кэша»)
3. **Rate limit** — rpm guard → `{"rate_limited": true}`
4. **Spend limit** — дневной бюджет → `{"spend_limited": true}`; после ответа
   `spend_limit.record()` вызывается **только при успехе** (без `error`).
   При наличии `usage` пишется usage-based cost, иначе — pre-call estimate.
5. **Routing** — CF AI Gateway или прямой вызов, затем model fallback
6. **Empty-content guard** — фейк-успех (HTTP 200 без контента) → синтетическая ошибка → model fallback

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

Переключение `GatewayProvider.CLOUDFLARE` vs `CUSTOM` — в `voly/ai_gateway/`.

### OmniRoute (upstream)

`omniroute` — self-hosted OpenAI-совместимый gateway (237+ провайдеров, free tiers,
auto-fallback, компрессия). VOLY видит его как **один** upstream и делегирует всю
маршрутизацию/фолбэк самому OmniRoute (`_call_omniroute` → `<base>/v1/chat/completions`).

Два режима использования:

1. **Opt-in провайдер:** не входит в default `_TASK_PROVIDERS`-цепочки; выбирается
   явно (provider `omniroute`), чтобы незапущенный локальный gateway не попадал в fallback.
2. **Первоклассный upstream (делегирование слоя A):** `ai_gateway.upstream: "omniroute"`
   в `voly.yaml` → все не-CF вызовы `chat()` идут сначала через OmniRoute
   (`AIGateway._delegated_or_direct`). Модель — passthrough вызывающего, либо
   `upstream_model: "auto"` (auto-combo). При ошибке/недоступности upstream —
   `metrics.record_fallback()` и автоматический fallback на прямой адаптер
   запрошенного провайдера (`upstream_fallback_direct: true`, default): мёртвый
   локальный gateway не блокирует pipeline. Маркеры ответа: успех через upstream —
   `result["upstream"]="omniroute"`, ответ после фолбэка — `result["upstream_fallback"]=true`.
   Явный вызов provider=`omniroute` вторым hop-ом не заворачивается. Кэш, DLP,
   spend limits и телеметрия не меняются — живут вокруг вызова. Тесты:
   `tests/test_ai_gateway.py` («Upstream delegation»).

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

## Границы валидности кэша (risk R1)

Код-генерация чувствительна к состоянию репозитория: тот же промпт на изменившейся
кодовой базе должен давать другой ответ. Поэтому ключ кэша, помимо `messages` /
`model` / `provider` / `system`, включает **project-state scope** — отпечаток
состояния проекта.

- **Что даёт scope:** `voly/ai_gateway/project_state.py:project_fingerprint(cwd, files=None)`.
  Repo-level по умолчанию: git `HEAD` + сигнатура «грязного» рабочего дерева
  (`git diff HEAD` + untracked → повторное редактирование того же файла
  инвалидирует кэш без списка файлов). Не-git директория → идентичность по пути.
  Опциональный `files=[...]` добавляет mtime+size+content конкретных файлов
  (file-level precision; hook для local-context пути).
- **Как подключается:** атрибут инстанса `AIGateway.cache_scope` выставляется один
  раз при создании gateway из `config.default_cwd` (`pipeline/core.py`), поэтому
  все `chat()` на этом инстансе наследуют scope без пер-call проводки. Пер-call
  параметр `chat(..., cache_scope=...)` переопределяет инстансный. Пусто → scope
  не участвует (поведение до R1).
- **Что scope предотвращает:** cross-project collision (тот же task-текст на другом
  `cwd` → чужой cache hit) и stale hit после изменения репозитория.

**Executor path вне этого кэша.** Executor-субпроцессы (`claude-code`, `zen`,
`cursor`) читают и пишут файлы напрямую и **не** проходят через `AIGateway.cache`;
`wrangler` идёт через отдельный `/infer` (CF Worker), не через этот кэш. Значит
`AIGateway.cache` обслуживает только text-only reasoning (pipeline, суб-агенты,
DSPy) — именно там scope и нужен. Результаты executor-ов нигде не кэшируются.

## Empty-content guard

Провайдер может вернуть HTTP 200 без полезного контента (`content: ""`) — «фейк-успех»,
который иначе прошёл бы к пользователю пустым ответом. `AIGateway._empty_content_error`
конвертирует такой ответ в синтетическую ошибку (`{"empty_content": true, "error": ...}`),
и он уходит в обычный **model fallback** (в `_gateway_call`, `chat()`-direct и `_direct_fallback`).

**Что НЕ считается фейк-успехом** (пропускается без fallback): пустой контент с легитимным
терминальным стопом — `stop_reason` `max_tokens`/`tool_use` (Claude) или `finish_reason`
`length`/`tool_calls` (OpenAI). Для этого провайдер-адаптеры в `providers.py` пробрасывают
`stop_reason` в нормализованный результат, а детекция живёт в
`is_empty_content_response` (`voly/ai_gateway/error_classifier.py`).

Это **model-level** сигнал: `empty_content` НЕ входит в `TERMINAL_BILLING_TYPES`, поэтому
никогда не переключает executor по billing-цепочке — только следующую модель.

---

## Pricing / cost

Единственный источник правды — `_COST_RATES` в `voly/telemetry.py`.
При добавлении нового провайдера обновляй его там же.

---

## Добавить нового провайдера

1. Добавить в `voly/ai_gateway/` — адаптер для нового LLM API
2. Обновить `GatewayProvider` и роутинг в `voly/ai_gateway/`
3. Добавить `_COST_RATES[provider]` в `voly/telemetry.py`
4. Обновить `voly.yaml` defaults
5. Обновить `.env.example`
6. Обновить этот файл и `docs/ARCHITECTURE.md`

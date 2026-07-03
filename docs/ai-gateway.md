# AI Gateway

> **Актуальный документ:** [`docs/backend/ai-gateway.md`](backend/ai-gateway.md)
> Этот файл содержит базовую информацию; полное описание включая CF AI Gateway
> route schema, CF_AIG_TOKEN, WranglerExecutor — в `docs/backend/ai-gateway.md`.

---

## Зачем нужен Gateway

AI Gateway — единая точка входа для всех LLM-запросов агентов. Все вызовы в VOLY идут только через него: `Pipeline` никогда не обращается к провайдерам напрямую.

Что даёт gateway:
- **DLP** — блокирует secrets и PII в промптах до отправки
- **Cache** — возвращает кэшированный ответ при повторных запросах
- **Rate limiting** — защита от burst, ограничение rpm
- **Spend limits** — дневной бюджет в USD, глобальный и per-agent
- **Model fallback** — автоматическая цепочка резервных моделей
- **Метрики** — по провайдеру, модели, агенту

## Middleware-стек

Каждый вызов `gateway.chat()` проходит через стек в фиксированном порядке:

```
DLP scan → Cache check → Rate limit → Spend limit → [LLM call]
```

1. **DLP** — если нашёл secrets/PII, возвращает `{"dlp_blocked": true}`, дальнейшие слои не вызываются
2. **Cache** — если есть hit, возвращает кэш (`{"cache_hit": true}`), квота не тратится
3. **Rate limit** — проверяет requests-per-minute, при превышении `{"rate_limited": true}`
4. **Spend limit** — проверяет дневной бюджет, при превышении `{"spend_limited": true}`
5. **Routing** — выбирает CF Gateway или прямой вызов, выполняет запрос

## Routing: инфраструктурные провайдеры vs LLM провайдеры

Gateway различает два уровня:

1. **Инфраструктурный провайдер** (`GatewayProvider`): `CLOUDFLARE` или `CUSTOM` — определяет, через какой API-слой идёт запрос.
2. **LLM провайдер** — конкретный сервис моделей: Anthropic, OpenAI, Google, DeepSeek, MiMo, OpenCode Zen/GO.

```python
# codeops/ai_gateway/models.py
class GatewayProvider(Enum):
    CLOUDFLARE = "cloudflare"
    CUSTOM = "custom"
```

Через Cloudflare AI Gateway маршрутизируются: Anthropic, OpenAI, Google AI Studio, DeepSeek.
Напрямую (CUSTOM): MiMo, OpenCode GO, OpenCode Zen.

```python
_CF_PROVIDERS = frozenset({"anthropic", "openai", "google-ai-studio", "deepseek"})

if cloudflare_enabled and provider_name in _CF_PROVIDERS:
    # → Cloudflare AI Gateway → provider API
else:
    # → прямой вызов provider API
```

`cloudflare_enabled` = True когда `enabled=True` И задан `account_id`.

## Таблица провайдеров

| Провайдер | Маршрут | Переменная окружения | Базовый URL |
|-----------|---------|---------------------|-------------|
| `anthropic` | CF Gateway | `ANTHROPIC_API_KEY` | через CF |
| `openai` | CF Gateway | `OPENAI_API_KEY` | через CF |
| `google-ai-studio` | CF Gateway | `GOOGLE_API_KEY` | через CF |
| `deepseek` | CF Gateway | `DEEPSEEK_API_KEY` | через CF |
| `mimo` | Direct (OpenAI-compat) | `MIMO_API_KEY` | `MIMO_BASE_URL_OPENAI` |
| `mimo-anthropic` | Direct (Anthropic-compat) | `MIMO_API_KEY` | `MIMO_BASE_URL_ANTHROPIC` |
| `opencode` | Direct → opencode.ai/zen/go | `OPENCODE_API_KEY` | `OPENCODE_BASE_URL` |
| `opencode-zen` | Direct → opencode.ai/zen | `OPENCODE_API_KEY` | `OPENCODE_ZEN_BASE_URL` |

**Переменные для CF:**
```
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_AI_GATEWAY_ID
CLOUDFLARE_API_TOKEN
```

## Конфигурация в `codeops.yaml`

```yaml
ai_gateway:
  enabled: true
  provider: cloudflare
  account_id: "${CLOUDFLARE_ACCOUNT_ID}"
  gateway_id: "${CLOUDFLARE_AI_GATEWAY_ID}"
  api_token: "${CLOUDFLARE_API_TOKEN}"

  caching:
    enabled: true
    ttl_seconds: 3600      # время жизни записи
    max_entries: 1000      # максимум записей в памяти

  rate_limits:
    enabled: true
    requests_per_minute: 60

  spend_limits:
    enabled: true
    daily_budget_usd: 20.0
    per_agent_budget:      # опциональный лимит per-agent
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
    enabled: false          # включите если нужна защита от утечек
    block_secrets: true     # API-ключи, JWT, SSH-ключи
    block_pii: true         # email, SSN, номера карт
```

## Пример настройки fallback-цепочки

Задача: если основная модель недоступна, попробовать дешёвую альтернативу.

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

При каждой ошибке gateway переходит к следующему элементу цепочки. Метрика `fallbacks_used` увеличивается при каждом переключении.

## Метрики (`codeops ai-gateway status`)

```
AI Gateway: cloudflare
Enabled: True
Gateway: codeops-gateway

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

## DLP — детектируемые паттерны

**Secrets:**
- `api_key: sk-...`, `token = "..."`, `password = "..."`
- JWT-токены (`eyJ...`)
- OpenAI-ключи (`sk-[A-Za-z0-9]{12,}`)
- GitHub PAT (`ghp_...`)
- Slack-токены (`xox[baprs]-...`)
- SSH private keys

**PII:**
- SSN: `123-45-6789`
- Номера карт: 16 цифр
- Email-адреса

При обнаружении любого паттерна запрос блокируется и возвращается:
```json
{"dlp_blocked": true, "error": "DLP blocked: [...]", "content": ""}
```

## Программный доступ

```python
from codeops.ai_gateway import AIGateway

gw = AIGateway(
    account_id="...",
    gateway_id="codeops-gateway",
    api_token="...",
)

# Настройка spend limits per-agent
gw.spend_limit.per_agent_budget["architect"] = 5.0

# Настройка fallback
gw.fallback.chain = [
    {"provider": "openai", "model": "gpt-4o-mini"},
    {"provider": "deepseek", "model": "deepseek-chat"},
]

# Включить DLP
gw.dlp.enabled = True

# Вызов
result = gw.chat(
    messages=[{"role": "user", "content": "Объясни SOLID"}],
    model="claude-sonnet-4-5-20250929",
    provider_name="anthropic",
    max_tokens=1024,
    agent="developer",   # для per-agent spend tracking
)

print(result["content"])
print(result.get("cache_hit"))    # True если из кэша
print(result.get("dlp_blocked"))  # True если заблокировано DLP
print(gw.metrics.to_dict())
```

> **Статус**: реализован. Cache, DLP, Rate/Spend limits, Fallback — работают. CF-routing требует `CLOUDFLARE_ACCOUNT_ID`. Без него запросы идут напрямую к провайдерам.

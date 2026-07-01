# API Routes — Backend Reference

FastAPI сервер: `codeops/web/server.py`. Запуск: `codeops serve` (порт 7860).

---

## POST /api/run

Запуск задачи. Возвращает SSE-поток.

```typescript
// Request
{
  task: string,
  agent?: string,      // "" = auto-route
  model?: string,      // "" = auto
  executor?: string,   // "pipeline" | "claude-code" | "wrangler" | "zen" | ...
  cwd?: string,        // target project path (overrides config.default_cwd)
  max_turns?: number,  // default 30
  a2a_delegate?: bool  // delegate to A2A federation
}

// SSE events
data: {"type": "start", "task": "...", "executor": "claude-code"}
data: {"type": "done", "success": true, "content": "...", "billing_fallback": "zen"}
data: {"type": "error", "error": "..."}
```

**Smart dispatch:** если `executor="pipeline"` и задача требует code gen,
автоматически промоутится в `executor="claude-code"` с `cwd` из `config.default_cwd`
или `CODEOPS_PROJECT_CWD` env var.

Логи: `[DISPATCH] pipeline → claude-code`, `[CHAIN:START]`, `[CHAIN:BILLING_FALLBACK]`

---

## GET /api/tasks

Список задач из `.codeops/events/`. SSE-поток обновлений.

```typescript
// SSE events
data: {"type": "init", "tasks": [...]}
data: {"type": "update", "task": {...}}
```

---

## GET /api/status

Состояние сервера, конфигурация, версии.

---

## GET /api/registry/agents

Список зарегистрированных агентов из `codeops/registry/`.

---

## GET /api/registry/skills

Список скилов из `codeops/catalog/`.

---

## GET /api/models

Список доступных моделей (из конфига + провайдеров).

---

## GET /api/ai-gateway/status

Состояние AI Gateway: провайдеры, spend, rate limits.

---

## GET /api/spend/status

Текущий дневной spend по агентам/провайдерам.

---

## POST /api/telemetry

Запись телеметрии из внешних источников.

---

## CF Worker endpoints (`cf-workers/agent/`)

Отдельный Worker для CF-native задач. Запуск: `wrangler dev`.

| Endpoint | Метод | Назначение |
|---|---|---|
| `/health` | GET | Проверка доступности + AI binding status |
| `/infer` | POST | CF AI Gateway inference → FILE blocks для LocalPatchApplier |
| `/pipeline` | POST | Прокси к CodeOps pipeline runner |
| `/a2a` | POST/GET | A2A federation endpoints |

**`POST /infer`** — основной endpoint для WranglerExecutor:
```typescript
// Request
{ task: string, context?: string, model?: string, system?: string, max_tokens?: number }
// Response
{ success: bool, content: string, model: string, provider: string, input_tokens?, output_tokens? }
```

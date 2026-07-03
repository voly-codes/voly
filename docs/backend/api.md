# API Routes — Backend Reference

FastAPI сервер: `voly/web/server.py`. Запуск: `voly serve` (порт 7860).

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

Список задач из `.voly/events/`. SSE-поток обновлений.

```typescript
// SSE events
data: {"type": "init", "tasks": [...]}
data: {"type": "update", "task": {...}}
```

---

## GET /api/status

Состояние сервера, конфигурация, версии.

```json
{
  "version": "0.1.0",
  "tasks_count": 12,
  "events_dir": "/path/to/.voly/events",
  "default_cwd": "/home/user/project",
  "cf": { ... }
}
```

`default_cwd` — путь из `voly.yaml` (`default_cwd`) или env `CODEOPS_PROJECT_CWD`. Пустая строка если не задан. Используется UI (RunPanel) для авто-заполнения поля cwd при загрузке.

---

## GET /api/registry/agents

Список зарегистрированных агентов из `voly/registry/`.

---

## GET /api/registry/skills

Список скилов из `voly/catalog/`.

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
| `/health` | GET | Проверка доступности + pipeline/A2A callback status |
| `/infer` | POST | CF AI Gateway inference → FILE blocks для LocalPatchApplier |
| `/agents/:name/run` | POST | Запуск задачи + A2A callback (`task_id` optional) |
| `/mcp` | * | MCP tools (`run_task`) |

**A2A callback:** `completeA2ATask()` POST `/tasks/:id/complete` на federation worker через
service binding `A2A_FEDERATION` (HTTP fetch на `*.workers.dev` даёт CF error 1042).

## CF Worker endpoints (`cf-workers/a2a/`)

| Endpoint | Метод | Назначение |
|---|---|---|
| `/health` | GET | Federation + queue status |
| `POST /tasks` | POST | Создать задачу (`async: true` → queue dispatch) |
| `GET /tasks/:id` | GET | Статус задачи |
| `POST /tasks/:id/complete` | POST | Callback от agent worker (Bearer `API_TOKEN`) |
| queue consumer | — | Dispatch через service binding `AGENT_WORKER` |

**`POST /infer`** — основной endpoint для WranglerExecutor:
```typescript
// Request
{ task: string, context?: string, model?: string, system?: string, max_tokens?: number }
// Response
{ success: bool, content: string, model: string, provider: string, input_tokens?, output_tokens? }
```

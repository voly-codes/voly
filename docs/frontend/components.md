# Components — Frontend Reference

---

## RunPanel.svelte

Главная панель запуска задачи. Содержит:
- textarea для task
- `<RunParams>` — выбор executor / agent / model / cwd
- кнопку Run
- `<RunResult>` для вывода

**Executor order** (file-writing first, text-only last):
```
claude-code → wrangler → zen → cursor → opencode → pipeline → deepseek → workers-ai → cloudflare-dynamic
```

**Props:** `config`, `agents`, `models`

**Events:** SSE stream от `POST /api/run` — типы: `start`, `done`, `error`

**Auto-fill cwd:** при монтировании компонента, если поле `cwd` пустое, запрашивает `GET /api/status` и подставляет `default_cwd` (из `voly.yaml` или `VOLY_PROJECT_CWD`).

---

## RunParams.svelte

Параметры запуска. Передаёт `$bindable` значения родителю.

```svelte
let {
  executor = $bindable('pipeline'),
  agent = $bindable(''),
  model = $bindable(''),
  cwd = $bindable(''),
  executors = [],
  running = false
} = $props()
```

**Executor hints** — подсказка под каждым executor:
- `pipeline`: "AI Gateway — cache, DLP, spend control (text only)"
- `claude-code`: "Claude Code CLI — reads/writes files · billing fallback → wrangler → zen"
- `wrangler`: "CF Workers AI via wrangler dev — writes files via LocalPatchApplier"
- `zen`: "OpenCode Zen — free tier, file-capable via opencode CLI"

**Working dir:** всегда виден (не скрыт при pipeline) — smart dispatch нужен cwd даже для pipeline.
Подсказка: `cwd ? 'executor writes here' : 'leave empty for text-only'`

---

## RunResult.svelte

Рендерит результат задачи. Показывает:
- success/error статус
- `content` — вывод агента
- `billing_fallback` — если произошёл fallback (напр. "zen")
- cost_usd, duration_ms, num_turns
- WorkReport (файлы: created/changed/deleted)

---

## PipelineStages.svelte

Визуализация стадий Pipeline для text-only задач:
```
INIT → ROUTE → RTK → SKILL → HEADROOM → DSPY → MODEL → DONE
```
Каждая стадия — цветной badge. Ошибочная стадия подсвечивается красным.

---

## TaskSidebar.svelte

Список предыдущих задач. Данные из `GET /api/tasks` (SSE).
Клик — загружает задачу в RunPanel.

---

## WorkReport.svelte

Показывает `work_report` из ExecutorResult:
- `files_created` — зелёный
- `files_changed` — синий
- `files_deleted` — красный
- `actions` — список выполненных действий
- `summary` — краткое описание

---

## CostPanel.svelte

Показывает cost_usd, input_tokens, output_tokens, automation_score.
Данные из `done` SSE event.

---

## Shared components

| Компонент | Назначение |
|---|---|
| `StatusDot` | цветная точка: green/yellow/red/gray |
| `CopyButton` | копировать текст в clipboard |
| `InfoTooltip` | `?` кнопка с тултипом |
| `Drawer` | боковая панель slide-in |
| `Modal` | диалоговое окно |
| `Toast` | уведомление сверху |
| `Spinner` | loading индикатор |
| `Skeleton` | loading skeleton |

---

## AppHeader.svelte

Топ-навигация: лого, ссылки на Tasks / Agents / Models / Spend.
Активный раздел — `--accent-blue`.

---

## Добавить новый executor в UI

1. `RunPanel.svelte` — добавить в массив executors (file-writing перед text-only)
2. `RunParams.svelte` — добавить `executorHints[id]` с описанием
3. Обновить этот файл

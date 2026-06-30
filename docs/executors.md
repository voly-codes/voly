# CodeOps Executors

Executor — runtime, который **реально работает с файлами** в целевом проекте через `--cwd`. Это отличается от обычного text-only LLM вызова через Pipeline/AI Gateway.

CodeOps остаётся project-agnostic: executor получает задачу и рабочую директорию, но не содержит логики конкретного продукта.

---

## Когда нужен executor

| Сценарий | Используй |
|---|---|
| Изменить несколько файлов | `codeops run ... --executor cursor --cwd /path/to/project` |
| Сделать refactor/migration | executor |
| Запустить agent с Read/Write/Edit/Bash | executor |
| Только спросить/суммаризировать | обычный `codeops run` через Pipeline |
| Review/planning без правок | `zen`, `reviewer`, или обычный pipeline |

---

## Быстрый старт

```bash
cd codeops
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# optional for Cursor executor
pip install -e ".[cursor]"
```

Пример запуска на внешнем проекте:

```bash
codeops run "review the auth module and propose a minimal refactor" \
  --agent reviewer \
  --executor cursor \
  --cwd /path/to/target-project
```

`--cwd` всегда указывает на целевой проект, а не обязательно на репозиторий CodeOps.

---

## Executor overview

| Executor | Инструменты | Требования | Когда использовать |
|---|---|---|---|
| `cursor` | Read/Write/Edit/Bash через Cursor Agent | `CURSOR_API_KEY`, `cursor-sdk` | основной file-capable executor |
| `opencode` | OpenCode Go CLI/API — file-capable agent | opencode CLI или `OPENCODE_API_KEY` | fallback / bulk code tasks |
| `claude-code` | Claude CLI | `ANTHROPIC_API_KEY`, `claude` CLI | Anthropic-native coding flow |
| `deepseek` | text/code generation | `DEEPSEEK_API_KEY` | дешёвые черновики |
| `zen` | OpenCode Zen CLI/API — curated models, file-capable via CLI | `OPENCODE_API_KEY`, opencode CLI | основной для Zen-моделей |
| `mimo` | text/batch tasks | `MIMO_API_KEY` | batch генерация |

---

## Cursor executor

`cursor` — recommended executor для задач, где нужны реальные изменения файлов.

```text
codeops run --executor cursor --cwd /path/to/project
        ↓
CursorExecutor (codeops/executor/cursor.py)
        ↓
cursor-sdk → Agent.prompt(task, local={cwd})
        ↓
Cursor Agent local runtime
        ↓
ExecutorResult { output, duration_ms, metadata }
```

Переменные:

| Переменная | Обязательно | Описание |
|---|---:|---|
| `CURSOR_API_KEY` | да | API key для Cursor Agent |
| `CURSOR_MODEL` | нет | модель агента, если поддерживается runtime |

Примеры:

```bash
# Implementation
codeops run "implement the repository pattern for users" \
  --agent developer --executor cursor --cwd /path/to/project

# Architecture
codeops run "design a migration plan for billing" \
  --agent architect --executor cursor --cwd /path/to/project

# Code review
codeops run "review recent changes for security and regressions" \
  --agent reviewer --executor cursor --cwd /path/to/project
```

---

## OpenCode Zen and GO

| Gateway | Executor | Endpoint | Может менять файлы |
|---|---|---|---|
| OpenCode GO | `opencode` | `OPENCODE_BASE_URL` | да, через CLI/API flow |
| OpenCode Zen | `zen` | `OPENCODE_ZEN_BASE_URL` | да, через CLI (agentic) / нет, через API (text-only) |

Zen-модели (через `opencode-zen` провайдер): `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5`, `deepseek-v4-flash-free`, `mimo-v2.5-free`.
GO-модели (через `opencode` провайдер): `deepseek-v4-flash`, `deepseek-v4-pro`, `kimi-k2.6`, `kimi-k2.7-code`, `qwen3.7-plus`, `qwen3.7-max`, `minimax-m3`, `glm-5.2`.

Один ключ обычно используется через `OPENCODE_API_KEY`.

```bash
codeops catalog sync
codeops catalog list --tier free
codeops catalog match "review database migration risk"
```

См. [catalog-supervisor.md](./catalog-supervisor.md).

---

## Multi-agent orchestration

`MultiAgentOrchestrator` позволяет запускать несколько executor-задач последовательно или параллельно. Он не должен зависеть от конкретного продукта.

```python
from codeops.executor.multi_agent import AgentTask, MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
report = orchestrator.run_parallel([
    AgentTask("cursor", "Refactor auth service", cwd="/path/to/project"),
    AgentTask("zen", "Review auth refactor plan", cwd="/path/to/project", readonly=True),
])
print(report.to_markdown())
```

Каждый шаг должен возвращать `ExecutorResult` и, где возможно, эмитить telemetry.

---

## Relationship with Pipeline and DSPy

Executors и Pipeline решают разные задачи:

| Layer | Purpose |
|---|---|
| Pipeline | маршрутизация, gateway call, telemetry, memory, RTK/Headroom, DSPy |
| Inference Runtime | classic vs optional DSPy response generation |
| Executor | file-capable external/local agent runtime |

DSPy применяется в inference path. Executor-ы могут использовать результаты Pipeline/Router/Catalog, но не должны напрямую обходить cost/telemetry, если это production flow.

---

## Troubleshooting

| Ошибка | Решение |
|---|---|
| `CURSOR_API_KEY is not set` | добавь ключ в локальное окружение |
| `cursor-sdk not installed` | `pip install -e ".[cursor]"` |
| `Working directory not found` | проверь `--cwd` |
| Agent не меняет файлы | убедись, что выбран file-capable executor |
| `opencode` недоступен | проверь CLI/API key и endpoint |
| Нет telemetry | проверь, что executor возвращает `ExecutorResult` и event emission включён |

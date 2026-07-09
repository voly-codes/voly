# VOLY Executors

An executor is a runtime that **actually works with files** in the target project via `--cwd`. This differs from a normal text-only LLM call through the Pipeline/AI Gateway.

VOLY stays project-agnostic: the executor receives a task and a working directory, but contains no product-specific logic.

---

## When you need an executor

| Scenario | Use |
|---|---|
| Change several files | `voly run ... --executor cursor --cwd /path/to/project` |
| Do a refactor/migration | executor |
| Run an agent with Read/Write/Edit/Bash | executor |
| Only ask/summarize | normal `voly run` via Pipeline |
| Review/planning without edits | `zen`, `reviewer`, or normal pipeline |

---

## Quick start

```bash
cd voly
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# optional for Cursor executor
pip install -e ".[cursor]"
```

Example run against an external project:

```bash
voly run "review the auth module and propose a minimal refactor" \
  --agent reviewer \
  --executor cursor \
  --cwd /path/to/target-project
```

`--cwd` always points at the target project, not necessarily the VOLY repository.

---

## Executor overview

| Executor | Tools | Requirements | When to use |
|---|---|---|---|
| `cursor` | Read/Write/Edit/Bash via Cursor Agent | `CURSOR_API_KEY`, `cursor-sdk` | primary file-capable executor |
| `opencode` | OpenCode Go CLI/API — file-capable agent | opencode CLI or `OPENCODE_API_KEY` | fallback / bulk code tasks |
| `claude-code` | Claude CLI | `ANTHROPIC_API_KEY`, `claude` CLI | Anthropic-native coding flow |
| `deepseek` | text/code generation | `DEEPSEEK_API_KEY` | cheap drafts |
| `zen` | OpenCode Zen CLI/API — curated models, file-capable via CLI | `OPENCODE_API_KEY`, opencode CLI | primary for Zen models |
| `mimo` | text/batch tasks | `MIMO_API_KEY` | batch generation |

---

## Cursor executor

`cursor` is the recommended executor for tasks that need real file changes.

```text
voly run --executor cursor --cwd /path/to/project
        ↓
CursorExecutor (voly/executor/cursor.py)
        ↓
cursor-sdk → Agent.prompt(task, local={cwd})
        ↓
Cursor Agent local runtime
        ↓
ExecutorResult { output, duration_ms, metadata }
```

Variables:

| Variable | Required | Description |
|---|---:|---|
| `CURSOR_API_KEY` | yes | API key for Cursor Agent |
| `CURSOR_MODEL` | no | agent model, if supported by the runtime |

Examples:

```bash
# Implementation
voly run "implement the repository pattern for users" \
  --agent developer --executor cursor --cwd /path/to/project

# Architecture
voly run "design a migration plan for billing" \
  --agent architect --executor cursor --cwd /path/to/project

# Code review
voly run "review recent changes for security and regressions" \
  --agent reviewer --executor cursor --cwd /path/to/project
```

---

## OpenCode Zen and GO

| Gateway | Executor | Endpoint | Can change files |
|---|---|---|---|
| OpenCode GO | `opencode` | `OPENCODE_BASE_URL` | yes, via CLI/API flow |
| OpenCode Zen | `zen` | `OPENCODE_ZEN_BASE_URL` | yes via CLI (agentic) / no via API (text-only) |

Zen models (via `opencode-zen` provider): `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5`, `deepseek-v4-flash-free`, `mimo-v2.5-free`.
GO models (via `opencode` provider): `deepseek-v4-flash`, `deepseek-v4-pro`, `kimi-k2.6`, `kimi-k2.7-code`, `qwen3.7-plus`, `qwen3.7-max`, `minimax-m3`, `glm-5.2`.

A single key is usually used via `OPENCODE_API_KEY`.

```bash
voly catalog sync
voly catalog list --tier free
voly catalog match "review database migration risk"
```

See [catalog-supervisor.md](./catalog-supervisor.md).

---

## Multi-agent orchestration

`MultiAgentOrchestrator` lets you run multiple executor tasks sequentially or in parallel. It must not depend on a specific product.

```python
from voly.executor.multi_agent import AgentTask, MultiAgentOrchestrator

orchestrator = MultiAgentOrchestrator()
report = orchestrator.run_parallel([
    AgentTask("cursor", "Refactor auth service", cwd="/path/to/project"),
    AgentTask("zen", "Review auth refactor plan", cwd="/path/to/project", readonly=True),
])
print(report.to_markdown())
```

Each step should return an `ExecutorResult` and, where possible, emit telemetry.

---

## Relationship with Pipeline and DSPy

Executors and Pipeline solve different problems:

| Layer | Purpose |
|---|---|
| Pipeline | routing, gateway call, telemetry, memory, RTK/Headroom, DSPy |
| Inference Runtime | classic vs optional DSPy response generation |
| Executor | file-capable external/local agent runtime |

DSPy is applied on the inference path. Executors may use Pipeline/Router/Catalog results, but must not bypass cost/telemetry when this is a production flow.

---

## Troubleshooting

| Error | Solution |
|---|---|
| `CURSOR_API_KEY is not set` | add the key to the local environment |
| `cursor-sdk not installed` | `pip install -e ".[cursor]"` |
| `Working directory not found` | check `--cwd` |
| Agent does not change files | ensure a file-capable executor is selected |
| `opencode` unavailable | check CLI/API key and endpoint |
| No telemetry | ensure the executor returns `ExecutorResult` and event emission is enabled |

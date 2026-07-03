<p align="center">
  <img src="docs/assets/voly-logo.png" alt="VOLY" width="720">
</p>

<p align="center">
  <a href="https://github.com/voly-org/voly/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/voly-org/voly/ci.yml?branch=main&style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="DSPy" src="https://img.shields.io/badge/DSPy-Optional-22C55E?style=for-the-badge">
  <img alt="Cloudflare AI Gateway" src="https://img.shields.io/badge/Cloudflare-AI_Gateway-F38020?style=for-the-badge&logo=cloudflare&logoColor=white">
  <img alt="A2A" src="https://img.shields.io/badge/A2A-Supported-6366F1?style=for-the-badge">
  <img alt="AG-UI" src="https://img.shields.io/badge/AG--UI-Streaming-0EA5E9?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-orange?style=for-the-badge">
</p>

<p align="center">
  AI Agent Control Plane · DSPy Optimization · FinOps · Context Compression · A2A · AG-UI · Cloudflare AI Gateway
</p>

> **🌐 [Русская версия](README.md)**

# VOLY — FinOps + Automation Control Plane for AI Agents

> **VOLY wraps Claude Code, Cursor, Codex, OpenCode and other AI agents to run them cheaper, safer, and with full measurability.**

VOLY is not yet another AI agent. It is a **control plane** between the developer, CLI/CI, and agents:

- routes tasks across agents, models, and executors;
- controls costs through Cloudflare AI Gateway, spend limits, and cost policy;
- reduces token consumption via RTK, Headroom, cache, and model routing;
- collects telemetry on every run;
- supports DSPy as an optional optimization layer for prompt/program optimization;
- stays project-agnostic: target projects are passed via `--cwd`, never hardcoded in VOLY.

## Value metrics

| Goal | How VOLY helps |
|---|---|
| Cut costs | RTK, Headroom, cache, cheaper model routing, spend limits |
| Automate routine | workflows, predefined agents, executor orchestration |
| Control AI spend | telemetry, cost per task, cost per agent, daily budget |
| Manage risk | DLP, rate limits, fallback, budget stops, approval gates |
| Scale to teams | shared gateway, shared policies, shared metrics |
| Improve response quality | optional DSPy programs with shadow/active rollout |

## Quick start

```bash
git clone https://github.com/voly-org/voly.git
cd voly
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # add API keys if needed
voly init
voly status
```

For DSPy:
```bash
pip install -e ".[dspy,dev]"
voly dspy status
```

For file-capable executors:
```bash
pip install -e ".[cursor]"   # if using Cursor executor
voly run "review this repository" --agent reviewer --executor cursor --cwd /path/to/project
```

## How it works

```text
Developer / CLI / CI / Scheduler
        ↓
VOLY CLI
        ↓
Pipeline
        ↓
Agent Router + Cost Policy
        ↓
Memory → RTK → Headroom
        ↓
Inference Runtime
        ├─ Classic Prompt Runtime
        └─ DSPy Runtime (optional: off | shadow | active)
        ↓
AI Gateway
        ├─ DLP
        ├─ Cache
        ├─ Rate limits
        ├─ Spend limits
        └─ Provider fallback
        ↓
Claude / GPT / Gemini / DeepSeek / MiMo / OpenCode
        ↓
Telemetry → .voly/events/ + optional CF Pipelines / R2
```

`AIGateway.chat()` remains the single exit point to models. Even DSPy goes through the gateway adapter, preserving cache, DLP, spend limits, fallback, and telemetry.

## Core commands

```bash
voly run <task>              # run a task through the pipeline
voly match <task>            # match agent, model, provider, tools
voly compare <task>          # direct API vs VOLY pipeline
voly savings                 # savings report
voly scan                    # scan project
voly status                  # component status
```

## Agents, models, and skills

```bash
voly registry agents         # list agents
voly registry skills         # list skills
voly model list              # models and pricing
voly model route <task>      # model for a task
voly catalog sync            # sync OpenCode Zen models
voly catalog match <task>    # match model/executor by catalog rules
```

## Budget, gateway, and telemetry

```bash
voly ai-gateway status
voly ai-gateway metrics
voly ai-gateway flush-cache
voly spend summary
voly telemetry status
voly telemetry test --dry-run
```

## DSPy optimizer layer

DSPy connects as an optional layer between `HEADROOM_COMPRESS` and `AI Gateway` through the `Inference Runtime`.

Modes:

| Mode | Behavior |
|---|---|
| `off` | DSPy fully disabled |
| `shadow` | DSPy runs for observation, user gets classic runtime response |
| `active` | DSPy result may replace classic response for allowed agents |

Commands:
```bash
voly dspy status
voly dspy dataset build
voly dspy compile --agent reviewer
voly dspy eval --agent reviewer
voly dspy programs
voly dspy promote code-review.v2 --tag production
```

Note: `shadow` may execute both DSPy and classic calls for the same task. Use it as a staged rollout before `active`.

## Executors

An executor is a runtime that can actually work with files in `--cwd`.

| Executor | Purpose | Requirements |
|---|---|---|
| `cursor` | Code implementation, multi-file edits | `CURSOR_API_KEY`, `cursor-sdk` |
| `opencode` | OpenCode CLI/API fallback | opencode / `OPENCODE_API_KEY` |
| `claude-code` | Claude CLI | `ANTHROPIC_API_KEY`, `claude` CLI |
| `deepseek` | Cheap text tasks | `DEEPSEEK_API_KEY` |
| `zen` | Analysis/review/planning via OpenCode Zen | `OPENCODE_API_KEY` |
| `mimo` | Batch/text tasks | `MIMO_API_KEY` |

Example:
```bash
voly run "implement auth refactor" \
  --agent developer \
  --executor cursor \
  --cwd /path/to/target-project
```

## Configuration

Minimal `voly.yaml`:
```yaml
default_model: claude-sonnet
default_agent: claude

ai_gateway:
  enabled: true
  provider: cloudflare
  account_id: "${CLOUDFLARE_ACCOUNT_ID}"
  gateway_id: "${CLOUDFLARE_AI_GATEWAY_ID}"
  api_token: "${CLOUDFLARE_API_TOKEN}"
  caching:
    enabled: true
  spend_limits:
    enabled: true
    daily_budget_usd: 20

dspy:
  enabled: false
  mode: shadow
  agents:
    - reviewer
    - documenter
    - architect
```

Runtime state should not be committed to git:
```text
.voly/events/
.voly/dspy/datasets/
.voly/dspy/programs/
```

## CI

The repository includes a GitHub Actions smoke gate:

- base install on Python 3.*;
- import without DSPy extra;
- DSPy extra smoke test;
- runtime smoke tests.

Full historical test suite can be enabled separately after stabilizing legacy tests.

## Documentation

| File | Purpose |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | current VOLY architecture |
| [CLAUDE.md](CLAUDE.md) | instructions for AI agents in this repo |
| [docs/executors.md](docs/executors.md) | executor runtime guide |
| [docs/catalog-supervisor.md](docs/catalog-supervisor.md) | catalog routing and model planning |
| [docs/dspy.md](docs/dspy.md) | DSPy integration guide |

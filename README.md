<p align="center">
  <img src="docs/assets/voly-logo.png" alt="VOLY" width="720">
</p>

<p align="center">
  <a href="https://github.com/voly-codes/voly/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/voly-codes/voly/ci.yml?branch=main&style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Multi-Agent" src="https://img.shields.io/badge/Multi--Agent-A2A-6366F1?style=for-the-badge">
  <img alt="DSPy" src="https://img.shields.io/badge/DSPy-Optional-22C55E?style=for-the-badge">
  <img alt="Cloudflare AI Gateway" src="https://img.shields.io/badge/Cloudflare-AI_Gateway-F38020?style=for-the-badge&logo=cloudflare&logoColor=white">
  <img alt="AG-UI" src="https://img.shields.io/badge/AG--UI-Streaming-0EA5E9?style=for-the-badge">
  <img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-orange?style=for-the-badge">
</p>

<p align="center">
  <a href="https://www.producthunt.com/products/voly-3?embed=true&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-voly-3" target="_blank" rel="noopener noreferrer"><img alt="VOLY - Routes AI coding agents with cost tracking and fallback | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1198419&theme=light&t=1784293268132"></a>
</p>

<p align="center">
  AI Agent Control Plane · Multi-Agent Orchestration · Billing Fallback Chain · DSPy · FinOps · A2A · AG-UI · Cloudflare AI Gateway
</p>

<p align="center">
  <strong>English</strong> · <a href="README_ru.md">Русский</a>
</p>

# VOLY — Control Plane for AI Agents

> **VOLY wraps Claude Code, Cursor, Codex, Zen and other AI agents so you can run them cheaper, safer, and with full measurability.**

VOLY is not another AI agent. It is a **self-hosted control plane** between the developer and the agents:

- **routes** tasks across executors with an automatic billing fallback chain;
- **decomposes** complex work into sub-agents (architect → developer → tester → reviewer → devops), where a strong lead orchestrator assigns model tiers and skills;
- **guards file writes** — dry-run with diff preview, protected paths, max-files limit, git-based rollback;
- **controls spend** via Cloudflare AI Gateway, spend limits, and cost policy;
- **reduces tokens** with a persistent cache, Headroom, model routing, and determinism;
- **collects telemetry** per run and surfaces metrics in the Web UI;
- supports **DSPy** as an optional optimization layer;
- stays **project-agnostic** — the target project is passed via `--cwd` or `VOLY_PROJECT_CWD`.

## Why VOLY, and not just a single agent?

Claude Code, Cursor, and Codex are excellent **executors**. VOLY is the layer
**above** them — it exists because running agents daily raises questions a
single CLI cannot answer:

| The question | VOLY's answer |
|---|---|
| The agent ran out of credits mid-task | Billing fallback chain `claude-code → wrangler → opencode → zen`, automatic |
| What did this run actually cost? | Per-run `TaskEvent`: cost, tokens, retries, per-role breakdown in the UI |
| A complex task = one giant prompt? | Multi-agent decomposition with a model tier per role; implement roles write files, review stays on chat |
| Is it safe to let an agent write files? | Safety policy: `--dry-run` with diff preview, protected paths (`.env*`, keys), max-files limit, git rollback |
| A premium model for a routine fix? | Cost policy + tier routing: cheap models for cheap roles |
| Provider keys in `.env` on every machine? | BYOK: keys live in Cloudflare Secrets Store, resolved by the gateway per request |

If all you need is "write code from a prompt" — use an agent directly. VOLY
pays off when agents become part of the **daily workflow** and you need
economics, control, and reports.

## 3-minute demo

```bash
voly init                                   # config + hooks
voly run "fix the auth redirect bug" \
    --executor claude-code --cwd ~/my-project
# → the executor writes files; if it hits a billing error the chain
#   falls through to the next executor; cost and touched files land
#   in the run report

voly run "refactor the config loader" \
    --executor claude-code --cwd ~/my-project --dry-run
# → same run, but every file change is rolled back afterwards;
#   the diff preview is kept in the result

voly ui                                     # web dashboard on :7788
```

A complex request ("redesign auth, add tests, review it") goes multi-agent
automatically: the lead model assigns roles and tiers, implement roles write
files through executors, the reviewer stays on chat — the report shows
role / model / cost / files per agent.

### Run report (Web UI)

One screen for the story Product Hunt / demos need: task → executor path →
files touched → cost and tokens.

<p align="center">
  <img src="docs/assets/dashboard_task.png" alt="VOLY Web UI — task run report with cost, tokens, and files touched" width="900">
</p>

## Open core vs Cloud

| | **voly** (this repo, Apache-2.0) | **voly-cloud** (commercial) |
|---|---|---|
| Orchestration, multi-agent, hybrid executors | ✔ full | same core |
| Billing fallback chain, cost policy, telemetry | ✔ full | same core |
| Executor safety policy (dry-run, protected paths) | ✔ full | same core |
| Local Web UI + CLI, self-hosted, single tenant | ✔ | — |
| BYOK in **your** Cloudflare account | ✔ | managed per tenant |
| Auth / SSO / teams / audit | — | ✔ |
| Hosted runs, shared spend dashboards, org limits | — | ✔ |

The open core is complete and self-hosted. The paid tier sells hosting and
team management — not core features.

## How it works

A task from the web UI, CLI, or CI enters a single entry point and takes one of two paths:

```text
Developer / Web UI / CLI / CI
              ↓
       VOLY Entry Point
              ↓
        ROUTE (task analysis)
        ┌─────┴───────────────────────────┐
        │                                 │
   complex,                         simple code
   ≥2 capabilities                  generation (1 flag)
        │                                 │
        ▼                                 ▼
  PIPELINE · MULTI-AGENT            EXECUTOR PATH
  (A2A local)                       (file-capable)
        │                                 │
  Lead orchestrator                 executor.run(task, cwd)
   ├─ tier + skills per role        Billing Fallback Chain:
   ├─ architect → developer         claude-code → wrangler → opencode → zen
   ├─ tester / reviewer / devops          │
   └─ each via AIGateway.chat()           │
        │                                 │
        └────────────┬────────────────────┘
                     ▼
              AIGateway.chat()
DLP → Cache → Rate limit → Spend limit → Provider → Telemetry
```

Non-code-generating text tasks go through a single model call on the same pipeline path.

**`AIGateway.chat()`** is the only exit point to models. Pipeline, sub-agents, DSPy, and runtimes all go through it — cache, DLP, spend limits, fallback, and telemetry stay consistent.

**Smart dispatch** (`POST /api/run`, `executor=pipeline`):

- complex multi-capability task (≥ `a2a.min_flags_for_dispatch` flags from code-gen / review / testing / deployment, or `complexity=high`) → **stays in the pipeline and runs multi-agent**;
- simple code task → promoted to `executor=claude-code` with `cwd` from config / `VOLY_PROJECT_CWD` (so files are actually written);
- text task → single model call.

## Multi-agent orchestration (A2A local)

When a task enters multi-agent mode (`a2a.execution_mode=local`, default):

1. **`TaskDecomposer`** splits the task into roles with dependencies (architect → developer → tester → reviewer → devops).
2. **Lead orchestrator** — a strong (premium) model scores the task and assigns each role a **model tier** (`premium | standard | cheap`) and **skills** from the registry. On lead LLM failure — deterministic fallback.
3. Tier → concrete `(model, provider)` from a **live pool** filtered by `ProviderHealthChecker`:
   - **strong**: `anthropic`, `cloudflare-dynamic`
   - **weak/cheap**: `workers-ai`, `deepseek`, `opencode-zen`, `mimo`, `omniroute`
4. Sub-agents run **in-process** via `AIGateway.chat()` in dependency order; prior role outputs are passed forward.
5. Merge → `TaskEvent` with `a2a_assignments` (role / tier / model / skills / tokens / cost / cache_hit). Visible in the Web UI (“Multi-agents” panel).

**Repeat savings:** sub-agents are deterministic (`temperature=0`), and the gateway cache is **persistent** (on disk) — an identical re-run hits the cache across the whole chain (cost → $0). Skip a provider (e.g. out of credits): `VOLY_A2A_EXCLUDE_PROVIDERS=anthropic`.

## Quick start

```bash
git clone https://github.com/voly-codes/voly.git
cd voly
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ui,dev]"
cp .env.example .env       # add API keys
voly init
voly status
```

Web UI (dev):

```bash
# backend API (FastAPI) — :7788
python3 -m uvicorn voly.web.server:create_app --factory --host 127.0.0.1 --port 7788
# UI dev server (Vite) — :5173, proxies API to :7788
cd ui && npm install && npm run dev
```

Single process (production, serves the built UI on :7788):

```bash
cd ui && npm run build && cd ..
voly ui
```

Pipeline runner for CF agent workers over a tunnel — separate service on `:9202`:

```bash
voly serve
```

DSPy (optional):

```bash
pip install -e ".[dspy,dev]"
voly dspy status
```

### Web UI auth (optional)

By default the API is **open on localhost**. Before exposing the UI/API on a network, enable JWT:

```bash
export VOLY_AUTH_ENABLED=true
export VOLY_JWT_SECRET='long-random-secret-at-least-32-chars'
export VOLY_AUTH_USERS='admin:change-me'
```

See [docs/backend/api.md](docs/backend/api.md) for login and protected routes.

## Billing fallback chain (executor path)

If the current executor runs out of budget, `AgentRunner` walks the chain:

```
claude-code  →  wrangler  →  opencode  →  zen
(Anthropic)    (CF Workers)  (OpenCode)   (free / last resort)
```

`ExecutorResult.billing_error = True` → next executor. All of these can write files under `--cwd`.

## Executors

| Executor | Writes files | Billing | Chain position |
|---|---|---|---|
| `claude-code` | yes — Claude CLI | Anthropic | 1st |
| `wrangler` | yes — LocalPatchApplier | CF Workers AI | 2nd |
| `opencode` | yes — OpenCode CLI | opencode.ai | 3rd |
| `zen` | yes — opencode CLI | free / subscription | 4th (last resort) |
| `cursor` | yes — Cursor Agent | Cursor | standalone |
| `deepseek` / `mimo` | no — text only | API | outside chain |

```bash
voly run "implement auth refactor" --executor claude-code --cwd /path/to/target-project
```

For automatic selection use the Web UI or `voly match`.

## AI Gateway

`AIGateway.chat()` is the single model exit. Middleware: **DLP → Cache → Rate limit → Spend limit → Routing → Provider**.

- **Persistent cache** — responses are stored on disk (`ai_gateway.cache_persist_dir`, default `.voly/gateway_cache`), so repeats hit cache across requests and restarts.
- **Spend on success only** — failed provider calls do not inflate the daily budget.
- **Providers**: `anthropic`, `openai`, `google`, `deepseek`, `workers-ai`, `cloudflare-dynamic`, `opencode-zen`, `mimo`, **`omniroute`** (self-hosted OpenAI-compatible gateway, opt-in).
- **Gateway tab metrics** come from telemetry (real requests / tokens / cost / `by_provider` / `by_model` / `spent_today`), not a fresh empty instance.

The CF Worker (`cf-workers/agent/src/infer.ts`) routes inference through the CF AI Gateway route schema (`CF_ACCOUNT_ID` + `CF_AIG_TOKEN`, `POST /infer`) or `env.AI.run()` fallback.

## Web UI

Svelte 5 SPA with hash routing: `#/tasks`, `#/gateway`, `#/telemetry`, `#/dspy` plus Cloudflare and Skill Marketplace drawers.

| Component | Role |
|---|---|
| `RunPanel` / `RunParams` | Run a task (executor, agent, model, cwd), SSE stream |
| `RunResult` | Result: content, billing chain, **Multi-agents** panel (role / tier / model / skills / cached) |
| `PipelineInspector` | Pipeline stages, token flow, sub-agent assignments, memory, DSPy |
| `GatewayPage` | Cache / rate / spend / fallback / DLP + by-provider / by-model / key health |
| `TelemetryPage` | Spend analytics (daily, by_agent, by_model) |
| `DSPyPage` | DSPy programs and lifecycle |
| `CFPage` / `MarketplacePage` | Cloudflare workers + spend · skill catalog |

## DSPy — optional optimization layer

| Mode | Behavior |
|---|---|
| `off` | DSPy disabled |
| `shadow` | runs in parallel for observation; response stays classic |
| `active` | DSPy result replaces classic for allowed agents |

```bash
voly dspy status
voly dspy dataset build
voly dspy compile --agent reviewer
voly dspy promote code-review.v2 --tag production
```

## Configuration

```yaml
# voly.yaml
default_cwd: ""              # target project path (or VOLY_PROJECT_CWD)

ai_gateway:
  provider: cloudflare
  cache_enabled: true
  cache_persist_dir: .voly/gateway_cache   # disk cache; empty → in-memory only
  spend_limit_usd_per_day: 20.0

a2a:
  enabled: true
  auto_dispatch: true         # auto multi-agent for complex tasks
  min_flags_for_dispatch: 2   # capability-flag threshold
  execution_mode: local       # local (lead + sub-agents) | federation (remote)
  lead_model: ""              # lead model; empty → premium from healthy pool

auth:
  enabled: false              # set true + VOLY_JWT_SECRET before network exposure
  cors_origins:
    - "http://localhost:7788"
    - "http://localhost:5173"

cost_policy:
  max_task_cost_usd: 2.0

dspy:
  enabled: false
  mode: shadow
```

Key env vars:

```env
ANTHROPIC_API_KEY=sk-ant-...              # claude-code / premium tier
OPENCODE_API_KEY=...                      # zen / opencode-zen
CLOUDFLARE_ACCOUNT_ID=...                 # CF AI Gateway + Workers AI
CLOUDFLARE_API_TOKEN=...
CF_AIG_TOKEN=...                          # CF Dashboard → AI Gateway → Settings
VOLY_PROJECT_CWD=/path/to/proj            # default cwd for executor and UI
VOLY_A2A_EXCLUDE_PROVIDERS=               # e.g. "anthropic" — hide from tier pool
VOLY_AUTH_ENABLED=false
VOLY_JWT_SECRET=
VOLY_AUTH_USERS=admin:change-me
OMNIROUTE_BASE_URL=http://localhost:20128 # if using the OmniRoute adapter
```

### BYOK — provider keys in Cloudflare (optional)

With `ai_gateway.byok_enabled: true`, keys for anthropic / openai /
google-ai-studio / deepseek are stored in **CF Secrets Store** and resolved by
the AI Gateway per request — no provider keys in `.env`, only `CF_AIG_TOKEN`.
See `docs/backend/ai-gateway.md` § BYOK (Store Keys).

### Hosted catalog & marketplace (optional, opt-in)

You can use the official hosted skill catalog / marketplace instead of
deploying your own workers from `cf-workers/`:

```env
CF_WORKER_CATALOG_URL=https://catalog.voly.codes
CF_WORKER_MARKETPLACE_URL=https://marketplace.voly.codes
```

`voly setup` offers to write these for you. Privacy note: catalog/skill
queries then go to those workers; nothing is sent unless you opt in.

## Core commands

```bash
voly run <task>                        # pipeline (→ multi-agent when complex)
voly run <task> --executor claude-code --cwd /path/to/project
voly match <task>                      # pick agent / executor / model
voly status                            # component health
voly savings                           # savings report
voly ui                                # web dashboard (FastAPI + Svelte) :7788
voly serve                             # pipeline HTTP runner :9202

voly registry agents | skills          # agent / skill registry
voly model list                        # models and pricing
voly ai-gateway status                 # AI Gateway status
voly spend status                      # current daily spend
voly dspy status                       # DSPy programs + mode
voly cloud login --url https://cloud.voly.codes   # browser + Clerk; shared run history
voly cloud sync                                 # upload past local runs after link
```

## CI and tests

```bash
pytest tests/test_dspy_runtime_smoke.py     # required after changes
pytest tests/test_multiagent_smoke.py       # multi-agent (mock gateway)
pytest tests/test_web_auth.py               # JWT auth baseline
pytest tests/ -q                            # full suite
```

GitHub Actions: base install (Python 3.10–3.14), import smoke without/with DSPy, runtime smoke tests.

## Do not commit

```
.voly/events/  .voly/dspy/  .voly/reports/  .voly/gateway_cache/
.venv/  ui/node_modules/  voly/web/static/
```

## Documentation

| File | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | High-level map: pipeline, executor, gateway, A2A |
| [docs/backend/pipeline.md](docs/backend/pipeline.md) | Stages, AgentRouter, auto multi-agent, smart dispatch |
| [docs/backend/executors.md](docs/backend/executors.md) | Executors, billing fallback chain, WranglerExecutor |
| [docs/backend/ai-gateway.md](docs/backend/ai-gateway.md) | AIGateway, providers, OmniRoute, persistent cache |
| [docs/backend/dspy.md](docs/backend/dspy.md) | DSPy programs, TaskPlanner, adapter, datasets |
| [docs/backend/config.md](docs/backend/config.md) | voly.yaml, env vars, VOLYConfig |
| [docs/backend/api.md](docs/backend/api.md) | FastAPI endpoints, SSE, JWT auth, CF Worker /infer |
| [docs/frontend/overview.md](docs/frontend/overview.md) | Svelte 5 stack, ui/ layout, dev/build |
| [CLAUDE.md](CLAUDE.md) | Instructions for AI agents in this repo |
| [README_ru.md](README_ru.md) | Russian version of this README |

## Contributing & License

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) (DCO, rules, open-core boundaries). Licensed under [Apache 2.0](LICENSE).

# VOLY — Agent Instructions

> **Project:** VOLY — AI control plane for running agents, managing cost, routing tasks, and orchestration.

OpenWiki: start at [openwiki/quickstart.md](openwiki/quickstart.md), then follow its links.

## Project goal

VOLY routes a developer's tasks to the right AI agent, manages the billing fallback chain, collects telemetry, and provides a web UI + REST API.

**Key components:**
- **Billing fallback chain:** `claude-code → cursor → deepseek → wrangler → opencode → zen` — on executor `billing_error`
- **Smart dispatch:** Web UI with `executor=pipeline` + code task → auto-promotes to `claude-code`
- **DSPy TaskPlanner:** refines the task before the executor, collects (task, result) examples for optimization
- **CF AI Gateway route schema:** `/infer` endpoint in the CF Worker routes via the CF Dashboard route schema
- **Local context:** before the executor, gathers relevant project files via grep

VOLY is project-agnostic — no product-specific logic in `voly/`.

---

## Strategic architecture — read FIRST

VOLY = two layers with different value:

- **Layer A — model gateway / routing / fallback across model providers.** Competes with OmniRoute / LiteLLM / OpenRouter — a mature, crowded niche. **Stabilize minimally and delegate to an external gateway** (VOLY already supports OmniRoute as an upstream). NOT the source of revenue or uniqueness — do not chase provider breadth.
- **Layer B — orchestration over file-capable CLI agents.** Executor chain (agents write files into the project), billing fallback between CLIs, multi-agent decomposition (model tier per role), project-agnostic executor path, task cost telemetry. **This is product uniqueness + the foundation of monetization — put all development focus here.**

**Invariant #1:** `AIGateway.chat()` is the only path out to models. Pipeline, DSPy, sub-agents, and runtimes all go through it — so cache, DLP, spend limits, fallback, and telemetry come free to every component. Never call a provider around the gateway (except executors — that is a separate path).

**Do not do without an explicit request:** a custom workflow engine, Temporal (if needed — DBOS/Restate), early marketplace, growing periphery before Layer B core is stable.

---

## Skills — read BEFORE starting work

| Skill | When to use |
|---|---|
| `/voly-plan` | Create a task plan, choose agents (zen vs claude-code), launch |
| `/voly-backend` | Work on the Python backend: pipeline, executors, gateway, DSPy, API |
| `/voly-frontend` | Work on the Svelte UI: components, API client |
| `/voly-report` | Create a report after finishing a task |

---

## Documentation — read before making changes

```
docs/
  backend/
    pipeline.md      ← Pipeline stages, AgentRouter, smart dispatch, hybrid A2A
    a2a.md           ← A2A modules, auto-dispatch, federation, context handoff
    plan.md          ← Plan gates, verify, tester_command scoping
    reuse.md         ← voly reuse: GitHub search → pack → pick → apply
    executors.md     ← All executors, billing fallback chain, WranglerExecutor
    ai-gateway.md    ← AIGateway, CF route schema, providers, env vars
    dspy.md          ← DSPy programs, TaskPlanner, shadow/active, adapter
    config.md        ← voly.yaml, env vars, VOLYConfig fields
    api.md           ← FastAPI endpoints, SSE events, CF Worker /infer
  frontend/
    overview.md      ← Svelte 5 stack, ui/ structure, dev/build
    components.md    ← All components, their props/events
    api-client.md    ← SSE calls, event format, fallback handling
  ARCHITECTURE.md    ← High-level diagram + stage/executor tables
```

---

## Documentation rule (MANDATORY)

**Any change in code behavior = update the corresponding doc file.**

| What you changed | Update |
|---|---|
| Executor (added/changed) | `docs/backend/executors.md` |
| Pipeline stage / PipelineResult | `docs/backend/pipeline.md` + `docs/ARCHITECTURE.md` |
| Multi-agent / hybrid / cascade | `docs/backend/pipeline.md` + `docs/backend/a2a.md` |
| Plan gates / verify | `docs/backend/plan.md` |
| AI Gateway / provider | `docs/backend/ai-gateway.md` |
| DSPy program / config | `docs/backend/dspy.md` |
| Config / env var | `docs/backend/config.md` |
| Code reuse (`voly reuse`) | `docs/backend/reuse.md` + `docs/backend/config.md` |
| API endpoint | `docs/backend/api.md` |
| Svelte component | `docs/frontend/components.md` |
| API call from UI | `docs/frontend/api-client.md` |

### Fix log and local checklist (MANDATORY)

- `docs/problems-checklist.md` is a local working document. Never stage, commit,
  or push changes to it.
- After every functional fix commit, append an English entry to `fix.md` with
  the exact short commit hash and a concise description of what was fixed.
  The follow-up `fix.md` update may be included in the next documentation or
  batch commit; verify that all functional fix commits are listed before push.
- Run integration and end-to-end test tasks only in
  `/home/lanies/git/codeops/TEST_VOLY_JOB_MA/`, never in this repository.

---

## Choosing an agent for a task

| Task | Agent | Why |
|---|---|---|
| Update documentation | `zen` | simple task, free |
| Add a label/hint in the UI | `zen` | 1–2 files |
| Fix a typo/rename | `zen` | minimal risk |
| New executor / DSPy program | `claude-code` | complex architecture |
| New pipeline stage | `claude-code` | multiple files + docs |
| Provider integration | `claude-code` | gateway + config + docs |
| Refactor 3+ files | `claude-code` | needs context |

```bash
# Run via VOLY runner (this repository: /home/lanies/git/codeops/voly)
voly run "<task>" --executor zen --cwd /home/lanies/git/codeops/voly
voly run "<task>" --executor claude-code --cwd /home/lanies/git/codeops/voly
```

---

## Scope rules

| Rule | Meaning |
|---|---|
| Project-agnostic core | No hardcoded paths/product logic in `voly/` |
| Target project via `--cwd` | Executors work on external repos via `--cwd` |
| Generated state not source | Do not commit `.voly/events/`, DSPy datasets, compiled programs |
| Gateway first | Model calls go through `AIGateway.chat()` — except executors |
| Docs move with code | Docs are updated with the code, in the same commit |

---

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
pip install -e ".[dev]"
voly status
```

Optional: `pip install -e ".[dspy,dev]"` or `pip install -e ".[cursor,dev]"`

Smoke checks:
```bash
python -c "import voly.pipeline, voly.inference; from voly.config import VOLYConfig; assert VOLYConfig().dspy.enabled is False"
pytest tests/test_dspy_runtime_smoke.py
```

---

## Repository structure

```
voly/
  cli/              pipeline/       inference/     dspy/
  ai_gateway/       executor/       catalog/       registry/
  memory/           rtk/            headroom/      telemetry.py
  a2a/              agui/           web/           reuse/
  runner/           router.py
ui/                 cf-workers/     docs/          tests/
CLAUDE.md           voly.yaml    README.md
```

---

## CLI commands

```
voly run <task>    voly match <task>    voly compare <task>
voly savings       voly status          voly scan
voly registry agents        voly registry skills       voly skill list
voly model list             voly ai-gateway status     voly catalog sync
voly dspy status            voly memory search <query>  voly runs list
voly serve                  voly ui
voly a2a                    voly agui                 voly rtk
voly headroom               voly mcp                  voly runner
voly telemetry              voly balance              voly init
voly setup                  voly config               voly tunnel
voly spend status           voly cloud login
voly reuse search|pack|pick|apply|run
```

When removing a command: remove it from `cli/main.py`, `cli/commands/__init__.py`, tests, README, docs.

---

## Testing

CI: smoke gate — base install, import without DSPy, import with DSPy, runtime smoke tests.

```bash
pytest tests/test_dspy_runtime_smoke.py   # required after any changes
pytest tests/ -q                          # full run
```

---

## Do not commit

`.env`, `.voly/events/`, `.voly/dspy/datasets/`, `.voly/dspy/programs/`,
`.voly/reports/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`,
`ui/node_modules/`, `voly/web/static/assets/`

---

## Troubleshooting

| Problem | First check |
|---|---|
| `DSPy is not installed` | `pip install -e ".[dspy]"` or `dspy.enabled: false` |
| Base install imports DSPy | Check for top-level `import dspy` outside lazy paths |
| Pipeline bypasses gateway | Ensure the runtime uses `AIGateway.chat()` |
| Executor does not write files | Check `--cwd` and executor credentials |
| Billing fallback does not trigger | Detection in `voly/ai_gateway/error_classifier.py` (`_is_billing_error` delegates there); rate-limit 429 is NOT treated as billing — only quota-exhausted/account |
| Smart dispatch does not trigger | Set `VOLY_PROJECT_CWD` or `default_cwd` in `voly.yaml` |
| Wrangler executor unavailable | Run `cd cf-workers/agent && wrangler dev` |
| CI fails with test collection | Check `pyproject.toml` pytest config |
| Plan gate `command: exit 4` on pytest | Prefer `.venv/bin/pytest` — auto-fill when `.venv/bin/pytest` exists; or set `plan.tester_command`. Verify scopes bare pytest to touched `test_*.py` |
| Multi-agent only developer+tester | ≥2 capability flags auto-set `requires_review` (3 roles). Deploy/architecture keywords still needed for devops/architect |
| Hybrid roles stay chat / no files | Pass `--cwd` (or `VOLY_PROJECT_CWD`). Defaults: developer/tester/devops = executor |
| Anthropic burns every role first | `VOLY_A2A_EXCLUDE_PROVIDERS=anthropic` (pre-marked unhealthy) or wait for credit/billing mark_unhealthy |
| Provider hang / slow fallback | `request_timeout_seconds` (15 stall) + `request_total_timeout_seconds` (60 full response); plan gates use `plan.command_timeout_seconds: 60` |

<!-- OPENWIKI:START -->

## OpenWiki

This repository uses OpenWiki for recurring code documentation. Start with `openwiki/quickstart.md`, then follow its links to architecture, workflows, domain concepts, operations, integrations, testing guidance, and source maps.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->

# CodeOps — Agent Instructions

> **Project:** CodeOps control plane for AI agents.
> **Goal:** Keep CodeOps project-agnostic while improving orchestration, cost control, telemetry, executors, gateway safety and optional DSPy optimization.

## Scope

CodeOps is its own Python package and must not contain product-specific logic from downstream projects.

| Rule | Meaning |
|---|---|
| Project-agnostic core | No hardcoded customer/project paths, missions or product prompts in `codeops/` |
| Target project via `--cwd` | Executors operate on external repos through `--cwd /path/to/project` |
| Generated state is not source | Do not commit `.codeops/events/`, DSPy datasets or compiled programs |
| Gateway first | Model calls go through `AIGateway.chat()` unless a module is explicitly an executor |
| Docs move with code | Architecture/docs must be updated when runtime, gateway, executor or config changes |

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
codeops status
```

Optional extras: `pip install -e ".[dspy,dev]"` or `pip install -e ".[cursor,dev]"`

Smoke checks:
```bash
python -c "import codeops.pipeline, codeops.inference; from codeops.config import CodeOpsConfig; assert CodeOpsConfig().dspy.enabled is False"
pytest tests/test_dspy_runtime_smoke.py
```

## Repository structure

```text
codeops/
  cli/              pipeline.py    inference/     dspy/
  ai_gateway/       executor/      catalog/       registry/
  memory/           rtk/           headroom/      telemetry.py
  workflow/         a2a/           agui/
docs/               README.md   CLAUDE.md
```

## Core architecture

### Pipeline

`Pipeline.run()` flow: `INIT → AGUI_START → A2A_DISCOVER → A2A_DELEGATE → ROUTE → MEMORY_RETRIEVE → RTK_FILTER → HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL → MEMORY_STORE → AGUI_DONE → DONE → emit TaskEvent`

`run()` delegates to named stage methods (`_stage_agui_start`, `_stage_a2a`, `_stage_route`, etc.) — see `docs/ARCHITECTURE.md` for the full table.

When changing: keep stage hooks meaningful, preserve `PipelineResult`, emit telemetry, avoid product logic, document in `docs/ARCHITECTURE.md`.

### Inference Runtime

`codeops/inference/runtime.py` picks between `ClassicRuntime` (gateway call) and `DSPyRuntime` (optional). Falls back to classic when DSPy is unavailable. Do not import DSPy at module level.

### DSPy

Optimization layer only. Rules:
- `AIGateway.chat()` is the only model exit
- `shadow` mode must not change user-visible output
- `active` mode must have classic fallback
- Compiled programs/datasets are runtime artifacts unless promoted
- `codeops dspy status` clarifies rollout/cost

### AI Gateway

Preserve: DLP, cache, rate limits, spend limits, fallback, metrics. When adding providers update: config defaults, provider routing, `_COST_RATES` in `codeops/telemetry.py` (single source of truth for pricing), docs.

### Executors

Inherit from `Executor`, return `ExecutorResult`, record cost/tokens/duration, avoid assumptions about target project layout, fail clearly when keys are missing.

## CLI commands

```
codeops run <task>    codeops match <task>    codeops compare <task>
codeops savings       codeops status          codeops registry agents
codeops registry skills    codeops model list     codeops ai-gateway status
codeops catalog sync       codeops dspy status    codeops workflow list
codeops memory search <query>
```

When removing: remove from `cli/main.py`, remove from `cli/commands/__init__.py`, remove tests, update README and docs.

## Testing

CI is a smoke gate: base install on supported Python, import without DSPy extra, DSPy extra install/import, runtime smoke tests. Use `pytest tests/test_dspy_runtime_smoke.py`.

## Documentation requirements

| Change | Required docs |
|---|---|
| Pipeline stage/result | `docs/ARCHITECTURE.md`, `README.md` if user-facing |
| DSPy behavior/config | `docs/dspy.md`, `docs/ARCHITECTURE.md` |
| Executor behavior | `docs/executors.md`, `README.md` |
| Catalog/routing | `docs/catalog-supervisor.md`, `docs/ARCHITECTURE.md` |
| CLI command | `README.md`, command-specific docs |
| Config/env | `README.md`, `codeops.yaml`, `.env.example` if needed |

## Do not commit

`.env`, `.codeops/events/`, `.codeops/dspy/datasets/`, `.codeops/dspy/programs/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`

## Troubleshooting

| Problem | First check |
|---|---|
| `DSPy is not installed` | `pip install -e ".[dspy]"` or keep `dspy.enabled: false` |
| Base install imports DSPy | Check for top-level `import dspy` outside lazy paths |
| Pipeline bypasses gateway | Ensure runtime uses `AIGateway.chat()` |
| CI fails with test collection | Check `pyproject.toml` pytest config and smoke test scope |
| Executor cannot modify files | Verify `--cwd` and executor credentials |
| Runtime files appear in git | Update `.gitignore` and remove from index |

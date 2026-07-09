# DSPy Integration

> **Canonical document:** [`docs/backend/dspy.md`](backend/dspy.md)
> This file has baseline information; the full description including TaskPlannerProgram
> and executor path integration is in `docs/backend/dspy.md`.

---

DSPy is an optional optimizer layer for VOLY. It improves structured LLM behavior by compiling programs against datasets and metrics, but it does not replace the VOLY pipeline.

## Position in the architecture

```text
Pipeline
  ↓
Memory / RTK / Headroom
  ↓
InferenceManager
  ├─ ClassicRuntime
  └─ DSPyRuntime
       ↓
     DSPyRunner
       ↓
     VOLYDSPyLM
       ↓
AIGateway.chat()
  ↓
Provider
```

Important rule: **DSPy must go through `AIGateway.chat()`** via `VOLYDSPyLM`. This preserves:

- DLP;
- cache;
- rate limits;
- spend limits;
- fallback;
- telemetry.

## Installation

Base VOLY does not require DSPy.

```bash
pip install -e ".[dev]"
```

DSPy-enabled install:

```bash
pip install -e ".[dspy,dev]"
```

Smoke check:

```bash
voly dspy status
pytest tests/test_dspy_runtime_smoke.py
```

## Configuration

```yaml
dspy:
  enabled: false
  mode: shadow              # off | shadow | active
  programs_dir: ".voly/dspy/programs"
  datasets_dir: ".voly/dspy/datasets"
  optimizer: bootstrap_fewshot
  min_examples: 20
  compile_budget: small     # small | medium | large
  routing_mode: shadow
  agents:
    - reviewer
    - documenter
    - architect
  active_tag: production
  shadow_tag: candidate
  program_overrides: {}
```

Environment overrides:

```bash
export DSPY_ENABLED=true
export DSPY_MODE=shadow
```

## Modes

| Mode | Behavior |
|---|---|
| `off` | DSPy is disabled; classic runtime only |
| `shadow` | DSPy runs for observation, but classic response is returned |
| `active` | DSPy response can replace classic response for eligible agents |

Shadow mode may run both DSPy and classic LLM calls for a single task. Use it intentionally for evaluation and rollout.

## CLI

```bash
voly dspy status
voly dspy dataset build
voly dspy compile --agent reviewer
voly dspy eval --agent reviewer
voly dspy programs
voly dspy promote code-review.v2 --tag production
```

## Program lifecycle

```text
telemetry events
  ↓
dataset build
  ↓
compile program
  ↓
tag as candidate
  ↓
shadow rollout
  ↓
evaluate score / shadow delta
  ↓
promote production
  ↓
active rollout for selected agents
```

## Package layout

| File | Purpose |
|---|---|
| `voly/dspy/adapter.py` | DSPy LM adapter over `AIGateway.chat()` |
| `voly/dspy/runner.py` | Runtime entry point used by `DSPyRuntime` |
| `voly/dspy/signatures.py` | DSPy signatures |
| `voly/dspy/modules.py` | DSPy modules (forward/optimize methods) |
| `voly/dspy/programs/` | Program definitions and registry |
| `voly/dspy/compiler.py` | Dataset loading and compile pipeline |
| `voly/dspy/store.py` | Versioned compiled program storage |
| `voly/dspy/versioning.py` | Tags and metadata |
| `voly/dspy/metrics.py` | Optimizer metrics |

## Telemetry fields

DSPy metadata is attached to `TaskEvent` and `PipelineResult`:

| Field | Meaning |
|---|---|
| `dspy_enabled` | Config enabled at runtime |
| `dspy_mode` | off / shadow / active |
| `dspy_program_id` | Program used for the agent/task |
| `dspy_program_version` | Compiled program version |
| `dspy_program_tag` | candidate / production / custom tag |
| `dspy_optimizer` | Optimizer name |
| `dspy_dataset` | Dataset id |
| `dspy_compile_id` | Compile identifier |
| `dspy_score` | Evaluation score when available |
| `dspy_shadow_delta` | Shadow-vs-classic delta when available |

## Rollout recommendations

1. Keep `enabled: false` by default.
2. Enable `shadow` for low-risk agents such as `documenter` and `reviewer`.
3. Build datasets from successful telemetry only.
4. Compile and tag candidate programs.
5. Run shadow until enough examples and evaluation data exist.
6. Promote to `production` only after evaluation.
7. Enable `active` for a small agent allowlist.
8. Keep classic fallback available.

## Development rules

- Do not import DSPy at top-level in base runtime paths.
- Keep base install working without `voly[dspy]`.
- Do not commit generated datasets or compiled programs by default.
- Any new DSPy program should have a metric and a documented input/output contract.
- Any user-visible behavior change must be represented in telemetry.

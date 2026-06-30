# DSPy Integration

DSPy is an optional optimizer layer for CodeOps. It improves structured LLM behavior by compiling programs against datasets and metrics, but it does not replace the CodeOps pipeline.

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
     CodeOpsDSPyLM
       ↓
AIGateway.chat()
  ↓
Provider
```

Important rule: **DSPy must go through `AIGateway.chat()`** via `CodeOpsDSPyLM`. This preserves:

- DLP;
- cache;
- rate limits;
- spend limits;
- fallback;
- telemetry.

## Installation

Base CodeOps does not require DSPy.

```bash
pip install -e ".[dev]"
```

DSPy-enabled install:

```bash
pip install -e ".[dspy,dev]"
```

Smoke check:

```bash
codeops dspy status
pytest tests/test_dspy_runtime_smoke.py
```

## Configuration

```yaml
dspy:
  enabled: false
  mode: shadow              # off | shadow | active
  programs_dir: ".codeops/dspy/programs"
  datasets_dir: ".codeops/dspy/datasets"
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
codeops dspy status
codeops dspy dataset build
codeops dspy compile --agent reviewer
codeops dspy eval --agent reviewer
codeops dspy programs
codeops dspy promote code-review.v2 --tag production
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
| `codeops/dspy/adapter.py` | DSPy LM adapter over `AIGateway.chat()` |
| `codeops/dspy/runner.py` | Runtime entry point used by `DSPyRuntime` |
| `codeops/dspy/signatures.py` | DSPy signatures |
| `codeops/dspy/modules.py` | DSPy modules (forward/optimize methods) |
| `codeops/dspy/programs/` | Program definitions and registry |
| `codeops/dspy/compiler.py` | Dataset loading and compile pipeline |
| `codeops/dspy/store.py` | Versioned compiled program storage |
| `codeops/dspy/versioning.py` | Tags and metadata |
| `codeops/dspy/metrics.py` | Optimizer metrics |

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
- Keep base install working without `codeops[dspy]`.
- Do not commit generated datasets or compiled programs by default.
- Any new DSPy program should have a metric and a documented input/output contract.
- Any user-visible behavior change must be represented in telemetry.

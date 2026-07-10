# DSPy — Backend Reference

DSPy is an optional optimization layer. It can replace or improve prompts
via teleprompters (BootstrapFewShot, MIPROv2). All DSPy traffic goes through
`AIGateway.chat()` — no direct model access.

If `dspy` is not installed, everything continues to work via ClassicRuntime.

---

## Modes

| Mode | Behavior |
|---|---|
| `off` | DSPy is not used |
| `shadow` | DSPy runs in parallel; result is logged but not returned to the user |
| `active` | DSPy result replaces the classic path for agents in `config.dspy.agents` |

Check status: `voly dspy status`

---

## Two DSPy integration points

### 1. Pipeline path (inference)

```
HEADROOM_COMPRESS → DSPY_PROGRAM_CALL → MODEL_CALL
```

`voly/inference/runtime.py` calls `DSPyRunner.run()` before the final
`AIGateway.chat()` call. Used for text-only tasks through Pipeline.

Programs: `reviewer`, `architect`, `bugfixer`, `documenter`, `router`.

### 2. Executor path (AgentRunner)

```
task → _dspy_plan_task() → refined_task → executor.run() → result
                                                          ↓
                                              _dspy_store_example()
                                              → datasets_dir/task_planner/
```

`voly/runner/agent_runner.py` calls `TaskPlannerProgram` before starting
any executor. Active only when `dspy.enabled=true`.

After execution it stores an example `(task, refined_task, result)` in JSONL for
later optimization.

---

## TaskPlannerProgram (`voly/dspy/programs/task_planner.py`)

**Signature:**
- Input: `task` (original task), `project_context` (brief project context)
- Output: `refined_task` (rephrased task), `success_criteria`, `estimated_complexity`

**Strategy:** `ChainOfThought` — the model reasons step by step before answering.

**Usage:** before the executor. If DSPy is unavailable or fails, the executor
receives the original `task` (graceful fallback).

**Optimization metric:** `task_quality_metric` — rewards specificity
(refined_task length vs original) and completeness (number of acceptance criteria).

---

## Other programs

| Program ID | Agents | Signature |
|---|---|---|
| `task_planner` | developer, architect, bugfixer, tester, devops | task → refined_task + criteria |
| `code-review` | reviewer | task + diff → summary + risks + bugs + patch |
| `architecture-analysis` | architect | task + files → diagnosis + proposed_design + plan |
| `generate-docs` | documenter | task + source → title + overview + usage |
| `bug-analysis` | bugfixer | task + code + stacktrace → root_cause + patch |
| `task-routing` | router | task → agent + complexity + confidence |

---

## DSPy adapter (`voly/dspy/adapter.py`)

`VOLYDSPyLM` — adapter between DSPy and VOLY AIGateway. Implements the DSPy `BaseLM`
interface. All DSPy calls go through `gateway.chat()` — cache, DLP,
rate limits, and spend limits are preserved.

```python
lm = VOLYDSPyLM(gateway=gateway, model="claude-sonnet-4-6", provider="anthropic")
dspy.configure(lm=lm)
```

---

## Datasets and compilation

Saved examples (`datasets_dir/task_planner/*.jsonl`) can be used for
optimization via teleprompters. Each example is one file, named
`{unix_seconds}-{8 hex chars}.jsonl` — the random suffix guarantees
uniqueness even when two examples are produced within the same second
(possible with the concurrent `/api/run` thread pool), which a
timestamp-only filename would silently overwrite (mode `"w"`).

```python
from voly.dspy.compiler import DSPyCompiler
compiler = DSPyCompiler(config)
compiler.compile("task_planner", optimizer="bootstrap", tag="v1")
```

Compiled programs live in `programs_dir/` — these are **runtime artifacts**, not source.
Do not commit them to git. Promote to production: `voly dspy status` → promote.

---

## Config

```yaml
# voly.yaml
dspy:
  enabled: false          # true to enable
  mode: shadow            # off | shadow | active
  model: llama-scout      # model for DSPy inference (from models: section)
  provider: workers-ai    # provider for DSPy; empty string = from model config
  agents: []              # empty = all agents (in active mode)
  programs_dir: .voly/dspy/programs
  datasets_dir: .voly/dspy/datasets
  active_tag: production
  shadow_tag: candidate
```

`model` / `provider` — which model DSPy uses for inference, **independent** of the task’s routing model. Prefer a cheap/free model (e.g. `llama-scout` via `workers-ai`) so DSPy does not compete with main executors for budget.

Model selection logic in `DSPyRunner._get_lm()`:
1. `config.dspy.model` → `config.dspy.provider` if both are set
2. `config.dspy.model` → provider from `get_model_config(model)` if provider is empty
3. Route model / provider as fallback (if `dspy.model` is not set)

---

## Telemetry — `dspy_used`

In `TaskEvent.dspy_used`:
- `True` — DSPy completed successfully (in `shadow` mode the result is not returned to the user, but DSPy did run)
- `False` — DSPy was not started or failed with an error

In `shadow` mode, `dspy_used=True` means “DSPy ran”, not “result was used”. The `mode="shadow"` field shows that output did not affect the response.

---

## Rules

- `AIGateway.chat()` is the only path to models
- `shadow` mode does NOT change user-facing output
- `active` mode must fall back to classic
- Compiled programs/datasets are runtime artifacts — do not commit
- Do not import `dspy` at module level — only in lazy paths

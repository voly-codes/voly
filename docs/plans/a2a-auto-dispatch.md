# Plan: Automatic A2A Dispatch for Complex Tasks

**Status:** ready-to-implement  
**Date:** 2026-07-01  
**Executor:** cursor

---

## Problem

`pipeline.run()` accepts `delegate_to_a2a=True` but it is never set automatically.
Every task — no matter how complex — runs as a single-agent call.
`TaskAnalysis` already detects `requires_code_gen`, `requires_review`, `requires_testing`,
`requires_deployment` and `complexity`, but nothing acts on them for multi-agent routing.

---

## Goal

When `codeops run` receives a task that requires **2+ distinct capabilities** (e.g. implement +
test + review), the pipeline should automatically decompose it into subtasks, dispatch each to a
specialized A2A agent, collect results, and merge them into a single `PipelineResult`.

User experience: `codeops run "implement feature X, write tests, and do code review"` should
produce output from 3 agents without any extra flags.

---

## Architecture

```
pipeline.run(task)
      │
      ▼
_stage_route()          ← TaskAnalysis already runs here
      │
      ▼
[NEW] _should_dispatch_a2a(analysis) → bool
      │  True when: complexity=high OR 2+ capability flags
      │
      ├── False → existing single-agent path (unchanged)
      │
      └── True ─→ [NEW] _stage_a2a_auto(task, analysis)
                        │
                        ▼
                  TaskDecomposer.decompose(task, analysis)
                        → list[Subtask(description, agent)]
                        │
                        ▼
                  A2AOrchestrator.dispatch_parallel(subtasks)
                        → list[A2ATask]  (run concurrently)
                        │
                        ▼
                  ResultMerger.merge(subtasks_results)
                        → PipelineResult (combined content)
```

---

## Files to create / modify

### 1. `codeops/a2a/decomposer.py`  ← NEW

```python
@dataclass
class Subtask:
    description: str
    agent: str          # "developer" | "reviewer" | "tester" | "architect" | "devops"
    depends_on: list[int] = field(default_factory=list)  # indices into subtask list

class TaskDecomposer:
    def decompose(self, task: str, analysis: TaskAnalysis) -> list[Subtask]:
        """
        Rule-based decomposition based on TaskAnalysis capability flags.
        No LLM call — fast and deterministic.

        Examples:
          requires_code_gen + requires_testing →
            [Subtask("implement...", "developer"), Subtask("write tests...", "tester", depends_on=[0])]

          requires_code_gen + requires_review + requires_testing →
            [developer, tester(dep=0), reviewer(dep=0)]

          requires_deployment (only) → [devops]

          complexity=high, requires_code_gen →
            [architect(design), developer(dep=0)]
        """
```

Logic matrix (all combinations of flags → subtasks):

| Flags | Subtasks |
|---|---|
| `code_gen` only | single-agent (no dispatch) |
| `code_gen + review` | developer → reviewer |
| `code_gen + testing` | developer → tester |
| `code_gen + review + testing` | developer → tester + reviewer (parallel) |
| `code_gen + deployment` | developer → devops |
| `complexity=high + code_gen` | architect → developer |
| `complexity=high + code_gen + review` | architect → developer → reviewer |
| all flags | architect → developer → tester + reviewer → devops |

No decomposition (fall through to single agent) when:
- only 1 flag is True
- complexity != "high" and only `code_gen=True`

---

### 2. `codeops/a2a/merger.py`  ← NEW

```python
class ResultMerger:
    def merge(self, task: str, subtasks: list[A2ATask]) -> str:
        """
        Concatenates agent outputs with clear section headers.

        Output format:
          ## [Developer] Implementation
          <content>

          ## [Reviewer] Code Review
          <content>

          ## [Tester] Test Suite
          <content>
        """
```

---

### 3. `codeops/a2a/__init__.py`  ← MODIFY

Add `dispatch_parallel(subtasks: list[Subtask]) -> list[A2ATask]` to
`A2AOrchestrator`:
- Uses `threading.Thread` per subtask (already in the module)
- Respects `depends_on`: subtasks with deps run after their dependency completes
- Timeout: `config.a2a.task_timeout_seconds` (default 120)
- On individual subtask failure: mark as failed, continue others, include error in merged output

---

### 4. `codeops/pipeline/stages.py`  ← MODIFY

Add `_should_dispatch_a2a(analysis) -> bool` and `_stage_a2a_auto()`:

```python
def _should_dispatch_a2a(self, analysis: TaskAnalysis) -> bool:
    if not self.config.a2a.enabled:
        return False
    flags = sum([
        analysis.requires_code_gen,
        analysis.requires_review,
        analysis.requires_testing,
        analysis.requires_deployment,
    ])
    return flags >= 2 or analysis.complexity == "high"

def _stage_a2a_auto(
    self, task: str, analysis: TaskAnalysis,
    agui_session_id: str | None, started: float
) -> PipelineResult | None:
    from codeops.a2a.decomposer import TaskDecomposer
    from codeops.a2a.merger import ResultMerger

    decomposer = TaskDecomposer()
    subtasks = decomposer.decompose(task, analysis)
    if len(subtasks) < 2:
        return None   # not worth dispatching, fall through to single agent

    self._fire(PipelineStage.A2A_DISCOVER, subtasks=subtasks)
    a2a_tasks = self.a2a.dispatch_parallel(subtasks)
    self._fire(PipelineStage.A2A_DELEGATE, a2a_tasks=a2a_tasks)

    merged_content = ResultMerger().merge(task, a2a_tasks)
    return PipelineResult(
        success=True,
        stage=PipelineStage.DONE,
        response=...,        # wrap merged_content in InferenceResponse
        a2a_tasks=a2a_tasks,
        agui_session_id=agui_session_id or "",
        duration_ms=(time.monotonic() - started) * 1000,
    )
```

---

### 5. `codeops/pipeline/core.py`  ← MODIFY

In `pipeline.run()`, after `_stage_route()`, add auto-dispatch check:

```python
route, analysis, task_type = self._stage_route(...)

# Auto A2A dispatch for complex multi-capability tasks
if self.config.a2a.enabled and not delegate_to_a2a:
    a2a_result = self._stage_a2a_auto(task, analysis, agui_session_id, started)
    if a2a_result is not None:
        return a2a_result

# existing single-agent path continues...
```

---

### 6. `codeops/config/_types.py`  ← MODIFY

Add to `A2AConfig`:
```python
auto_dispatch: bool = True          # enable automatic dispatch for complex tasks
min_flags_for_dispatch: int = 2     # how many capability flags trigger dispatch
task_timeout_seconds: float = 120.0 # per-subtask timeout
```

---

### 7. `codeops/telemetry.py`  ← MODIFY

Add to `TaskEvent`:
```python
a2a_dispatched: bool = False         # True when auto A2A dispatch ran
a2a_subtask_count: int = 0           # how many subtasks were dispatched
a2a_agents_used: list[str] = field(default_factory=list)
```

---

### 8. `docs/backend/pipeline.md`  ← UPDATE
### 9. `docs/ARCHITECTURE.md`  ← UPDATE

Document new `A2A_AUTO` stage in pipeline table.

---

## A2AConfig extension (codeops.yaml)

```yaml
a2a:
  enabled: true
  auto_dispatch: true       # ← new
  min_flags_for_dispatch: 2 # ← new
  task_timeout_seconds: 120 # ← new
  port: 9100
  federation_url: "${CF_WORKER_A2A_URL}"
```

---

## Tests to write

```
tests/test_a2a_decomposer.py
  - test_single_flag_no_dispatch()
  - test_code_gen_plus_review_decomposes_to_2()
  - test_all_flags_decomposes_to_ordered_subtasks()
  - test_high_complexity_triggers_architect()

tests/test_a2a_auto_dispatch.py
  - test_pipeline_dispatches_on_complex_task()   (mock A2A)
  - test_pipeline_single_agent_on_simple_task()
  - test_auto_dispatch_disabled_by_config()
```

---

## Execution order for cursor agents

Run in this order (each depends on the previous):

1. `codeops/a2a/decomposer.py` — no deps, pure logic
2. `codeops/a2a/merger.py` — no deps, pure logic
3. `codeops/a2a/__init__.py` — add `dispatch_parallel` (uses decomposer types)
4. `codeops/config/_types.py` — add A2AConfig fields
5. `codeops/config/_parser.py` — parse new fields from YAML
6. `codeops/pipeline/stages.py` — `_should_dispatch_a2a` + `_stage_a2a_auto`
7. `codeops/pipeline/core.py` — wire auto-dispatch into `run()`
8. `codeops/telemetry.py` — add `a2a_*` fields to TaskEvent
9. `tests/test_a2a_decomposer.py` + `tests/test_a2a_auto_dispatch.py`
10. `docs/backend/pipeline.md` + `docs/ARCHITECTURE.md`

---

## Execution Report (обязательно)

После каждого запуска с A2A dispatch pipeline **обязан** создавать отчёт:

### Что включает отчёт

```json
{
  "task_id": "...",
  "timestamp": "2026-07-01T12:00:00Z",
  "task": "implement auth module, write tests...",
  "a2a_dispatched": true,
  "subtasks": [
    { "agent": "architect", "status": "completed", "duration_ms": 4200, "content": "..." },
    { "agent": "developer", "status": "completed", "duration_ms": 11300, "content": "..." },
    { "agent": "tester",    "status": "completed", "duration_ms": 6100, "content": "..." }
  ],
  "merged_result": "## [Architect] Design\n...\n## [Developer] Implementation\n...",
  "total_duration_ms": 14800,
  "total_cost_usd": 0.0,
  "agents_used": ["architect", "developer", "tester"]
}
```

### Куда пишется

- **Локально:** `.codeops/reports/a2a/<task_id>.json` (автоматически)
- **Telemetry event:** поле `report` в `TaskEvent` (уже существует как `dict | None`)
- **CLI вывод:** после результата выводить краткую сводку:
  ```
  ── A2A Dispatch Report ──────────────────────
  Subtasks: 3  (architect + developer + tester)
  Duration: 14.8s  |  Cost: $0.00
  Report:   .codeops/reports/a2a/<task_id>.json
  ```

### Реализация

**Новый файл:** `codeops/a2a/report.py`

```python
@dataclass
class A2AReport:
    task_id: str
    task: str
    timestamp: str
    subtasks: list[dict]       # {agent, status, duration_ms, content, error}
    merged_result: str
    total_duration_ms: float
    total_cost_usd: float
    agents_used: list[str]

    def save(self, reports_dir: Path) -> Path:
        path = reports_dir / "a2a" / f"{self.task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2))
        return path
```

`_stage_a2a_auto()` создаёт `A2AReport`, сохраняет через `report.save()`, добавляет в `TaskEvent.report`.

Добавить в список файлов для реализации: **`codeops/a2a/report.py`** (шаг 2.5, между merger и dispatch_parallel).

---

## Definition of done

```bash
# smoke: import passes
python -c "from codeops.a2a.decomposer import TaskDecomposer; print('ok')"

# simple task → no dispatch
codeops run "fix the typo in README"
# → single agent, no A2A stage in stage_log

# complex task → auto dispatch
codeops run "implement auth module, write pytest tests, and do security review"
# → stage_log contains A2A_DISCOVER + A2A_DELEGATE
# → result contains sections from developer + tester + security agents
# → telemetry: a2a_dispatched=True, a2a_subtask_count=3

# tests pass
pytest tests/test_a2a_decomposer.py tests/test_a2a_auto_dispatch.py -v
pytest tests/test_a2a_p0.py tests/test_dspy_runtime_smoke.py -q
```

---

## P0 fixes (2026-07-01) — implemented

| Fix | Status |
|---|---|
| Recursion guard (`CODEOPS_A2A_NESTED`, `a2a_parent_task_id`) | done |
| Agent role via `force_agent` + CF infer prompt | done |
| Context handoff between dependency waves | done |
| Idempotent complete + queue/agent re-execute guards | done |
| `docs/backend/a2a.md` | done |

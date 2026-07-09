# Pipeline — Backend Reference

`voly/pipeline/core.py:Pipeline` — orchestrator for **text-only** tasks (inference via AIGateway).
For tasks that write files — use `AgentRunner` + executor.

---

## When Pipeline, when AgentRunner

| Scenario | What to use |
|---|---|
| Question / summarization / review without edits | Pipeline → AIGateway.chat() |
| Write/change files in a project | AgentRunner → executor (claude-code / wrangler / zen) |
| Web UI task with code | smart dispatch: pipeline → claude-code automatically |
| CLI `voly run --executor cursor` | AgentRunner directly |

---

## Pipeline stages

```
INIT
  ↓ AGUI_START       — notify AG-UI of task start (SSE events)
  ↓ A2A_DISCOVER     — find external agents (A2A federation)
  ↓ A2A_DELEGATE     — delegate subtasks if needed
  ↓ ROUTE            — AgentRouter.analyze_task() + route()
  ↓ MEMORY_RETRIEVE  — MemoryStore.search() — relevant context
  ↓ RTK_FILTER       — RTK token filtering of context
  ↓ SKILL_INJECT     — inject system prompt from Catalog Skills
  ↓ HEADROOM_COMPRESS — Headroom: compress messages if > token limit
  ↓ DSPY_PROGRAM_CALL — optional: DSPyRunner.run() (shadow or active)
  ↓ MODEL_CALL        — AIGateway.chat() → response
  ↓ MEMORY_STORE      — save (task, response) to memory
  ↓ AGUI_DONE         — close AG-UI stream
  ↓ DONE / ERROR
  ↓ emit TaskEvent → telemetry
```

---

## Auto multi-agent (A2A)

After `ROUTE`, the pipeline checks `_should_dispatch_a2a(analysis)`. If A2A is enabled
and the task is complex/multi-component (≥ `a2a.min_flags_for_dispatch` flags from
`requires_code_gen/review/testing/deployment`, or `complexity == "high"`), the task
goes to the multi-agent path `_stage_a2a_auto` instead of a single `MODEL_CALL`.

**`a2a.execution_mode` (default `"local"`):**

- **`local`** — `_run_multiagent_local`:
  1. `TaskDecomposer` splits the task into roles (architect → developer → tester →
     reviewer → devops) with dependencies.
  2. **Lead orchestrator** (`a2a/multiagent.py::LeadOrchestrator`) — a strong model
     (premium tier or `a2a.lead_model`) evaluates the task and assigns each role a
     **model tier** (`premium|standard|cheap`) and **skills** (from the registry). On LLM-lead
     failure — deterministic fallback (`_ROLE_TIER` + top skills for the role).
  3. Tier → concrete (model, provider) via `resolve_tier_model()`: real pool
     `_PROVIDER_MODELS`, filtered by `ProviderHealthChecker`
     (strong = anthropic/cloudflare-dynamic, weak = workers-ai/deepseek/opencode-zen/
     mimo/omniroute).
  4. `run_local` executes sub-agents **in-process** via `AIGateway.chat()` in
     dependency order, passing results from previous roles. Each agent has its
     own model, persona, and skills.
  5. Merge → `TaskEvent` with `a2a_dispatched=True`, `a2a_agents_used`,
     `a2a_assignments` (role/tier/model/skills/tokens/cost).

- **`federation`** — sub-tasks go to remote agents (`a2a.federation_url`)
  via `dispatch_parallel` (legacy path).

**Web promote:** `/api/run` with `executor=pipeline` for a complex task is no longer
promoted to `claude-code` — `_would_dispatch_a2a()` keeps it in the pipeline.
Simple code tasks (1 flag) still go to the `claude-code` executor.

### Hybrid multi-agent (implement roles → files) — PR1 skeleton

Design: [`docs/proposals/hybrid-multiagent-executor.md`](../proposals/hybrid-multiagent-executor.md).

When `a2a.hybrid_code_gen` is true **and** a project `cwd` is available
(`default_cwd` / `VOLY_PROJECT_CWD`), each sub-agent role resolves to
`mode=chat` or `mode=executor` via `voly/a2a/hybrid.py`:

| Role | Default mode |
|---|---|
| architect, reviewer, devops | `chat` → `AIGateway.chat()` |
| developer, bugfixer, tester | `executor` → AgentRunner (PR2); PR1 falls back to chat if no runner |

Config (`voly.yaml` → `a2a`):

| Field | Default | Meaning |
|---|---|---|
| `hybrid_code_gen` | `true` | Master switch (`VOLY_A2A_HYBRID` env override) |
| `hybrid_require_cwd` | `true` | Without cwd, all roles stay chat |
| `executor_default` | `claude-code` | First executor for implement roles |
| `executor_roles` | developer, bugfixer, tester | Roles that prefer executor mode |

**PR1 status:** mode map + `run_local` branch + injectable `executor_runner` for tests.
Real `AgentRunner` wiring is **PR2**. Until then, executor-mode roles log
`chat_fallback_no_runner` and still use `AIGateway.chat()`.

---

## Multi-agent resilience (Rung A: heartbeat + watchdog)

`TaskEvent` is emitted only at the **end** of a run, so a hung/crashed
multi-agent chain leaves no trace and the watchdog cannot see it. Rung A
(`voly/runtime/runs.py`) adds a lightweight in-flight record:

- `run_local` writes a `RunRecord` to `telemetry.runs_dir` (`.voly/runs/<task_id>.json`)
  at start and updates the **heartbeat after each sub-agent** (`current_role`,
  `done_roles`, `heartbeat_at`). At the end — `status = completed | failed`.
- `Watchdog` treats a run as **stale** if the heartbeat is older than
  `watchdog_stale_factor × a2a.task_timeout_seconds` (default 2 × 120s).
  A crashed process leaves a `running` record with a stale heartbeat → the
  watchdog picks it up.
- Tracking is **best-effort**: any write errors are swallowed and do not break the run
  (like telemetry). Writes are atomic (`tempfile` + `os.replace`).

CLI:

```bash
voly runs list                 # all runs (status/progress/age/role)
voly runs show <task_id>       # details of one run
voly runs reap [--yes]         # find (and mark) runs without heartbeat
```

The records also provide empirical data for roadmap §6 — real chain lengths and hang
frequency — to decide whether more expensive rungs (checkpoint/resume) are needed.

---

## PipelineResult

```python
@dataclass
class PipelineResult:
    success: bool
    stage: PipelineStage
    duration_ms: float
    response: GatewayResponse | None
    route: RouteDecision | None
    error: str | None
    injected_skills: list[str]
    tokens_saved_by_rtk: int
    tokens_saved_by_headroom: int
    dspy_used: bool
    dspy_mode: str
    a2a_tasks: list[A2ATask]
```

---

## Agent Router

`voly/router.py:AgentRouter`

```python
analysis = router.analyze_task(task)
# analysis.requires_code_gen — True if the task requires file changes
# analysis.task_type         — "code_generation" | "review" | "question" | ...

route = router.route(analysis)
# route.agent    — "developer" | "reviewer" | "architect" | ...
# route.model    — concrete model
# route.provider — "anthropic" | "openai" | ...
```

`requires_code_gen = True` when the task contains keywords: implement, create, build,
add, write, fix, refactor, migrate, напиши, создай, добавь, реализуй, исправь, ...

This is used in `web/routes/run.py` for smart dispatch.

---

## Changing the Pipeline

Rules:
- Preserve the `PipelineResult` structure
- Each stage is a named `_stage_*` method
- Always `emit TaskEvent` to telemetry
- No product-specific logic in `voly/`
- When changing — update `docs/ARCHITECTURE.md` and this file

# Proposal: Hybrid multi-agent → file writes

**Status:** draft — **PR1 + PR2 landed** (role map, `run_local` branch, AgentRunner wiring)  
**Layer:** B (orchestration over file-capable CLI agents)  
**Author context:** post-analysis roadmap item C  
**Related:** `docs/backend/pipeline.md`, `docs/ARCHITECTURE.md`, `voly/a2a/multiagent.py`, `voly/a2a/hybrid.py`, `voly/runner/agent_runner.py`, `voly/executor/multi_agent.py`

---

## Summary

Complex tasks that enter the **local A2A multi-agent path** today only call
`AIGateway.chat()`. They produce text reports and **do not modify** the target
repository. Simple code tasks already promote to `claude-code` and write files.

This proposal adds a **hybrid** mode: planning/review roles stay on chat;
implement roles run through the existing **executor + billing fallback chain**
with a real `cwd`.

---

## Problem

| Path | When | Files written? |
|---|---|---|
| Simple code + `executor=pipeline` | ~1 capability flag | Yes — promote → `claude-code` |
| Complex + A2A local | ≥ `min_flags_for_dispatch` or `complexity=high` | **No** — `run_local` → chat only |
| `voly/executor/multi_agent.py` | combat / explicit orchestration | Yes — not wired to pipeline A2A |

User expectation for tasks like “redesign auth, add tests, review” is a **diff under
`--cwd`**, not only a multi-agent narrative.

Relevant code today:

- Web promote: `voly/web/routes/run.py` (`_would_dispatch_a2a`, smart dispatch)
- Local multi-agent: `voly/pipeline/stages.py` → `voly/a2a/multiagent.py::run_local`
- File-capable chain: `voly/runner/agent_runner.py` (`BILLING_FALLBACK_CHAIN`)

---

## Goals

1. When hybrid is on, `cwd` is set, and the task requires code generation, **implement
   roles write files** via executors.
2. Preserve Layer A invariant: text LLM traffic still goes through `AIGateway.chat()`.
3. Reuse **AgentRunner** billing fallback (`claude-code → wrangler → opencode → zen`).
4. Stay **project-agnostic** (only `cwd` / `default_cwd`).
5. Keep federation A2A and combat `MultiAgentOrchestrator` out of v1 scope (document only).

## Non-goals (v1)

- OIDC / multi-tenant auth
- Parallel writers on the same `cwd`
- Replacing federation mode
- Auto-commit / auto-PR
- Perfect test-generation quality
- Full UI redesign (optional light telemetry fields only)

---

## Target behavior

```text
Task (complex + requires_code_gen + cwd)
        │
        ▼
   Lead orchestrator (existing)
   roles + tiers + skills + depends_on
        │
        ▼
   Per-role runner (HYBRID)
   ┌──────────────────┬─────────────────────┐
   │ plan / review    │ implement / fix     │
   │ architect,       │ developer, bugfix │
   │ reviewer, …      │ (+ tester if codegen)│
   │ → AIGateway.chat │ → AgentRunner       │
   │   (text only)    │   (cwd + billing    │
   │                  │    fallback chain)  │
   └──────────────────┴─────────────────────┘
        │
        ▼
   Merge + TaskEvent
   (assignments: mode, executor, files_touched, cost)
```

### Invariants

1. **No `cwd`** → all roles stay chat-only; emit a clear warning
   (`hybrid_skipped_no_cwd`), never invent a project path.
2. **Text roles** never get Write/Bash tools.
3. **Implement roles** use the existing executor path, not a new subprocess API.
4. **`AIGateway.chat()`** remains the only text model exit (plan/review).
5. **Sequential** implement roles on a shared `cwd` (no parallel file writers in v1).

---

## Design options

| Option | Idea | Pros | Cons |
|---|---|---|---|
| **A. Role → mode map** | Fixed map: developer/bugfixer = executor; architect/reviewer = chat | Predictable, testable | Tester/devops edge cases |
| **B. Lead decides mode** | Lead JSON field `execution: chat\|executor` | Flexible | Needs schema + fallback when lead fails |
| **C. Plan then single apply** | Multi-agent plans only; one final `claude-code` | Fewer races | Weaker multi-writer story |
| **D. Wire combat orchestrator** | Pipeline A2A → `executor/multi_agent.py` | Reuse parallel executor API | Different API; parallel cwd races |

### Recommendation (v1)

**A + light B:**

- Default **role → mode map** (A).
- Lead **may** set `execution` per role if the value is valid.
- Invalid / missing → fall back to map A.
- Implement roles run **sequentially** when sharing `cwd`.

---

## Role policy (v1)

| Role | Default mode | Notes |
|---|---|---|
| `architect` | `chat` | Design only |
| `developer` | `executor` | Primary writer |
| `bugfixer` | `executor` | |
| `tester` | `executor` if `requires_code_gen` else `chat` | Writes tests on code paths |
| `reviewer` | `chat` | Narrative review; future: readonly tools |
| `devops` | `chat` | Text artifacts in v1; v1.2 may promote when files requested |
| unknown | `chat` | Safe default |

**Default executor:** `claude-code`, then the same `BILLING_FALLBACK_CHAIN` as AgentRunner.

---

## Context handoff

Today: prior role **text** is injected into the next sub-task description.

Hybrid:

```text
architect (chat)  → markdown plan
        ↓ inject into developer prompt
developer (executor) → cwd + plan; may touch files
        ↓ inject truncated summary (+ optional files_touched)
tester (executor) → tests based on prior summary
reviewer (chat)   → review narrative
```

### Data shape

```python
@dataclass
class RoleOutcome:
    role: str
    mode: Literal["chat", "executor"]
    ok: bool
    content: str                 # text or executor output (truncated for handoff)
    cost_usd: float = 0.0
    executor: str | None = None  # e.g. "claude-code", "zen"
    files_touched: list[str] = field(default_factory=list)  # best-effort
    error: str | None = None
```

Prior context for the next role = existing-style injection over truncated
`RoleOutcome` content (mark prior output as untrusted context).

---

## Configuration

```yaml
# voly.yaml
a2a:
  execution_mode: local           # local | federation (unchanged)
  hybrid_code_gen: true           # NEW: enable hybrid when code-gen + cwd
  hybrid_require_cwd: true        # NEW: without cwd force chat-only
  executor_default: claude-code   # NEW
  executor_roles:                 # NEW: override default implement set
    - developer
    - bugfixer
    - tester
```

| Field | Default | Meaning |
|---|---|---|
| `hybrid_code_gen` | `true` | Master switch for hybrid behavior |
| `hybrid_require_cwd` | `true` | If no cwd, skip executors (chat only) |
| `executor_default` | `claude-code` | First executor for implement roles |
| `executor_roles` | see table | Roles that default to executor mode |

Optional env: `VOLY_A2A_HYBRID=1|0` overrides `hybrid_code_gen`.

### Recommended default semantics

- `hybrid_code_gen: true`
- Effective hybrid only when **`cwd` is present** and task analysis
  `requires_code_gen` (or role is in `executor_roles` and lead requested executor)
- Otherwise: identical to today’s chat multi-agent (no surprise writes)

---

## Code touch map

| Area | File(s) | Change |
|---|---|---|
| Multi-agent run | `voly/a2a/multiagent.py` | Branch chat vs executor; `RoleOutcome`; sequential implement |
| Decomposer / assignment | `voly/a2a/decomposer.py` (and lead types) | Optional `execution` field |
| Pipeline stage | `voly/pipeline/stages.py` | Pass `cwd`, config into local multi-agent |
| Config | `voly/config/_types.py`, `_parser.py`, `_template.py` | New `a2a.*` fields |
| Web run | `voly/web/routes/run.py` | SSE hints: hybrid / per-role mode |
| Telemetry | `voly/telemetry.py` / assignment payloads | `mode`, `executor`, `files_touched` |
| Tests | `tests/test_multiagent_smoke.py`, new `tests/test_hybrid_a2a.py` | Mock chat + fake executor |
| Docs | this file; `docs/backend/pipeline.md`; OpenWiki pipeline page | Ship with implementation |

**Out of v1 code changes:** federation worker, CF agent worker, combat
`MultiAgentOrchestrator` unification (follow-up).

---

## Failure, spend, billing

| Case | Behavior |
|---|---|
| Executor `billing_error` | Walk billing chain **for that role** (reuse AgentRunner) |
| Executor hard failure | Mark role failed; **skip dependents** by default |
| Mid-chain `spend_limited` | Same as today: stop remaining roles without further calls |
| No `cwd` + hybrid on | All chat + warning `hybrid_skipped_no_cwd` |
| Role timeout | Existing per-role / run timeout controls |
| Lead invalid `execution` | Fall back to role map |

Spend on chat roles: existing gateway rules (record **only on success**).

---

## Phased delivery

### PR1 — Skeleton

- Config flags + parser/template/docs stub
- Role → mode map helper (unit-tested)
- `run_local` structure with executor branch **mocked**
- Chat path behavior unchanged when hybrid off or no cwd

### PR2 — Wire AgentRunner

- Real `AgentRunner.run(...)` for implement roles
- Prior-context injection into executor task text
- Telemetry assignment fields
- Integration-style tests with fake executors (no live API)

### PR3 — Product polish

- SSE events: role start with `mode` / `executor`
- Docs + OpenWiki update
- Demo fixture: “add endpoint + unit tests” under temp `cwd`
- Optional: multi-agent UI panel shows mode/executor if fields already render

### Later

- Parallel **chat** roles only
- Reviewer readonly tool mode
- `a2a.hybrid_strategy: per_role | final_apply` (option C)
- Unify with combat `MultiAgentOrchestrator` behind one façade

---

## Acceptance criteria

1. Task roughly: “add REST endpoint X + unit tests” **with `cwd`** → files appear under `cwd`.
2. Same task **without `cwd`** → text only, no crash, warning visible (SSE/logs).
3. Architect/review-only wording without code-gen → no executor / no accidental writes.
4. Simulated primary executor billing failure → fallback still runs for implement role.
5. Full test suite green; new tests mock-based (no live LLM/API).
6. Behavior documented in `docs/backend/pipeline.md` in the same change set.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two writers corrupt the same files | Sequential implement roles only on shared `cwd` |
| Cost explosion (N executors) | Spend checks; optional max executor roles; existing daily budget |
| Prompt injection via prior role text | Truncate; label as untrusted prior context |
| Double-counting telemetry | Single `TaskEvent`; nest per-role details in assignments |
| API drift vs combat multi_agent | Document two entrypoints; unify later |
| Surprising writes on localhost | Require `cwd`; hybrid no-op without it; log mode per role |

---

## Open decisions (resolved for draft)

| Question | Draft decision |
|---|---|
| Default `hybrid_code_gen`? | **`true`**, but effective only with `cwd` + code-gen signal |
| Is `tester` an executor? | **Yes** when `requires_code_gen` |
| Failed developer → tester? | **Skip** dependents by default |

Revisit before PR1 if product wants opt-in-only (`hybrid_code_gen: false` default).

---

## Alternatives considered

1. **Always promote complex code tasks to a single `claude-code` run** — loses structured multi-role planning and tiered cost control.
2. **Chat-only multi-agent + human applies patch** — keeps current gap; not a product fix.
3. **Only combat orchestrator** — leaves Web UI / pipeline path broken for the common case.

---

## References

- `docs/ARCHITECTURE.md` — Layer A / Layer B
- `docs/backend/pipeline.md` — stages, A2A local, smart dispatch
- `docs/backend/executors.md` — billing fallback chain
- `docs/backend/ai-gateway.md` — spend-on-success, chat() stack
- `openwiki/backend/pipeline-and-a2a.md` — wiki summary
- `voly/a2a/multiagent.py` — `run_local`, lead orchestrator
- `voly/runner/agent_runner.py` — `BILLING_FALLBACK_CHAIN`
- `voly/executor/multi_agent.py` — parallel executor orchestrator (combat)
- `voly/web/routes/run.py` — smart dispatch / A2A keep-in-pipeline

---

## Changelog

| Date | Note |
|---|---|
| 2026-07-09 | Initial draft from control-plane analysis follow-up |
| 2026-07-09 | PR1: `A2AConfig` hybrid fields, `voly/a2a/hybrid.py`, `run_local` executor branch + mock runner, tests |
| 2026-07-09 | PR2: `make_agent_runner_executor`, `AgentRunner.run(emit_event=…)`, pipeline wires real executor path |

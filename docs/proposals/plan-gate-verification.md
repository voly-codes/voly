# Proposal: Plan state machine + verification gates

**Status:** draft — **PR1–PR3 landed** (FSM + verifiers + PlanRunner/CLI)  
**Layer:** B (orchestration over file-capable CLI agents)  
**Author context:** gap analysis — «ИИ не следует плану»; Voly softens but does not enforce  
**Related:** `voly/runtime/runs.py` (Rung A), `voly/a2a/multiagent.py`, `voly/runner/agent_runner.py`, `voly/executor/base.py` (`WorkReport`), `voly/dspy/programs/task_planner.py`, `voly/catalog/supervisor.py`, `docs/proposals/hybrid-multiagent-executor.md`

---

## Summary

Voly is a **control plane**: multi-agent orchestration, routing, FinOps, telemetry.
It already **structures** work (roles, order, heartbeats) and produces **evidence**
(`WorkReport` / git porcelain, `Assignment.ok`, `TaskEvent`).

It does **not** fully solve «agent ignores the plan»:

| Gap | Today | Needed |
|---|---|---|
| Step status | Process status (`done_roles`, `ok`, pipeline stage) | **Enforced** plan-step status with explicit transitions |
| Done correctly? | Self-report + optional file list | **Automatic acceptance checks** after each step |
| Next step | Runs when previous role returns | **Gate**: next step only if previous is `verified` |

This proposal adds a thin **plan + verify + gate** layer on top of existing runner /
A2A / WorkReport — **not** a general workflow engine (Temporal/DBOS out of scope;
see `CLAUDE.md`).

---

## Problem

```text
User plan (good)     →  AI freestyles inside executor
Checklist mental     →  no machine-checked transitions
"I did step 3"       →  no test / diff / script proof
```

What Voly has today (foundation, keep):

1. **Runner** — `AgentRunner` + billing fallback chain  
2. **Events** — `TaskEvent`, stage log, chain timelog  
3. **Multi-agent** — decompose → lead tiers → `run_local` by `depends_on`  
4. **Rung A** — `RunRecord` heartbeat / watchdog (process liveness only)  
5. **WorkReport** — files created/changed/deleted after executor  
6. **DSPy TaskPlanner** — emits `success_criteria` text (not validated)  
7. **Supervisor / MissionPlan** — routing enrichment (executor/model/skills), no runtime FSM  

What is missing:

1. Plan as **state machine** (per-step states + legal transitions)  
2. **Verify** hooks after each step (tests, git assertions, scripts)  
3. **Hard gate** — no advance without `verified`  

---

## Goals

1. Represent an executable plan with per-step states and enforced transitions.  
2. After each step, run **project-agnostic** verifiers that return pass/fail + evidence.  
3. Block the next step until the previous is `verified` (or policy allows skip/retry).  
4. Reuse AgentRunner, hybrid A2A, WorkReport, RunRecord, TaskEvent — no parallel stack.  
5. Stay **project-agnostic**: verifiers operate on `cwd` + declared checks, not product logic.  
6. Ship in small PRs with tests and docs updates.

## Non-goals (v1)

- Full workflow product (Temporal, durable sagas, human-in-the-loop UI designer)  
- Guaranteeing semantic quality of arbitrary AI code (only **declared** checks)  
- Parallel writers on one `cwd` (same as hybrid non-goal)  
- Auto-commit / auto-PR  
- Replacing federation A2A  
- Making DSPy `success_criteria` free-text into perfect oracles (map to structured checks)  
- Requiring verification for pure text/chat tasks without `cwd`

---

## Design principles

1. **Evidence over self-report.** Agent output is input to verify, not the verdict.  
2. **Fail closed by default.** Gate blocks unless verify returns `passed`.  
3. **Opt-in then default-on for multi-step code paths.** Config flag; shadow mode first.  
4. **Cheap verifiers first.** Git/path/command before LLM-as-judge.  
5. **No product-specific logic in `voly/`.** Checks are data (plan YAML/JSON) + generic runners.  
6. **Rung progression:** A (heartbeat) → **B (step FSM + verify gate)** → C (checkpoint/resume, later).

---

## Target model

### Plan document (runtime artifact)

```yaml
# Conceptual schema — stored under .voly/plans/<plan_id>.json (runtime)
# or loaded from project path via API/CLI
schema_version: 1
plan_id: "auth-refactor-001"
task_id: "…"                    # links to RunRecord / TaskEvent
cwd: "/path/to/project"
status: running                 # pending | running | completed | failed | aborted
steps:
  - id: design
    role: architect
    mode: chat                  # chat | executor
    status: verified            # see state machine
    depends_on: []
    acceptance:
      - type: output_nonempty
  - id: implement
    role: developer
    mode: executor
    status: pending
    depends_on: [design]
    acceptance:
      - type: files_exist
        paths: ["src/auth.py"]
      - type: git_diff_nonempty
      - type: command
        run: "pytest tests/test_auth.py -q"
        expect_exit: 0
```

### Step state machine

```text
                    ┌──────────┐
         create  →  │ pending  │
                    └────┬─────┘
                         │ claim (deps all verified)
                         ▼
                    ┌──────────┐
                    │ running  │  ← executor / chat in progress
                    └────┬─────┘
              ┌──────────┼──────────┐
              ▼          ▼          ▼
         ┌────────┐ ┌─────────┐ ┌────────┐
         │ failed │ │  done   │ │skipped │  (policy)
         └───┬────┘ └────┬────┘ └────────┘
             │           │ verify()
             │           ▼
             │      ┌──────────┐
             │      │verifying │
             │      └────┬─────┘
             │     ┌─────┴─────┐
             │     ▼           ▼
             │ ┌────────┐ ┌──────────┐
             └►│ failed │ │ verified │ ──► unlock dependents
               └────────┘ └──────────┘
                    │ retry (cap N)
                    └──► pending | running
```

**Legal transitions (enforced in code, not by prompt):**

| From | To | Condition |
|---|---|---|
| `pending` | `running` | all `depends_on` are `verified` (or empty) |
| `running` | `done` | executor/chat returned without hard crash |
| `running` | `failed` | executor error / timeout / billing exhausted |
| `done` | `verifying` | acceptance list non-empty; else auto → `verified` |
| `verifying` | `verified` | all checks passed |
| `verifying` | `failed` | any check failed |
| `failed` | `running` | retry under cap |
| `*` | `skipped` | explicit policy only (v1: config, not free agent choice) |

Gate rule: **step B cannot enter `running` unless every step in `depends_on` is `verified`.**

### Acceptance check types (v1)

| `type` | Inputs | Pass when |
|---|---|---|
| `command` | `run`, `expect_exit`, optional `cwd` | exit code matches |
| `files_exist` | `paths[]` | all paths exist under plan `cwd` |
| `files_missing` | `paths[]` | none of the paths exist |
| `git_diff_nonempty` | optional `paths[]` | porcelain / diff vs step start is non-empty |
| `git_diff_contains` | `paths[]` or `pattern` | changed files match |
| `output_nonempty` | — | agent/chat output length > 0 |
| `output_regex` | `pattern` | output matches (careful: soft) |

**v1.1 (optional):** `pytest_nodeid`, `eslint_paths` as thin wrappers over `command`.  
**Out of v1:** free-form LLM judge as sole gate (may run as **advisory** soft check later).

### Execution loop

```text
load/create Plan
persist PlanState (.voly/plans/)
for step in topo_order(steps):
    wait until deps verified          # GATE
    step → running
    run role (chat via AIGateway | executor via AgentRunner)   # existing
    collect WorkReport + output
    step → done
    if acceptance:
        step → verifying
        for check in acceptance:
            result = VerifyRunner.run(check, cwd, evidence)
            append to step.verify_log
            if not result.ok → step → failed; policy: stop | retry
        step → verified
    else:
        step → verified               # explicit empty acceptance = auto-pass
    heartbeat / RunRecord update (extend Rung A)
emit TaskEvent with plan summary
```

---

## Where it plugs into Voly

| Existing piece | Role in this design |
|---|---|
| `AgentRunner` | Execute `mode=executor` steps |
| `AIGateway.chat` / hybrid | Execute `mode=chat` steps |
| `run_local` / `Assignment` | Seed plan steps from multi-agent decomposition **or** run under plan engine |
| `WorkReport` + git porcelain | Evidence for git/file checks |
| `RunRecord` | Extend with `plan_id`, `current_step_id`, `step_statuses[]` |
| `TaskEvent` | Add `plan_id`, `plan_status`, `steps_verified`, `verify_failures` (schema bump) |
| DSPy `success_criteria` | Optional **compiler**: free text → suggested `acceptance[]` (human/agent review; not auto-trusted) |
| Catalog `MissionPlan` | Optional source of step routing (executor/model); not the FSM itself |
| Web UI PipelineInspector | Show step chips: pending / running / verified / failed |

**Integration strategy (recommended):**

- New package: `voly/plan/` (types, store, engine, verifiers) — keeps core free of product missions.  
- Multi-agent path: when `a2a.plan_gates` (name TBD) is on, wrap `run_local` with PlanEngine instead of only `depends_on` + `ok`.  
- Explicit CLI: `voly plan run path/to/plan.yaml` for hand-authored plans.  
- Combat / supervisor missions later map into the same engine.

---

## Config

```yaml
# voly.yaml
plan:
  enabled: false              # master switch
  mode: shadow                # off | shadow | active
  # shadow: run verifiers + log transitions, do NOT block next step
  # active: hard gate
  store_dir: .voly/plans
  max_step_retries: 1
  default_on_verify_fail: stop   # stop | retry | continue (continue only if mode=shadow or explicit)
  command_timeout_seconds: 120
  allow_skip: false
```

Env overrides: `VOLY_PLAN_ENABLED`, `VOLY_PLAN_MODE`.

---

## Phased delivery (PR plan)

### Phase 0 — Spec + contracts (PR0, docs + types only)

- This proposal as canonical design.  
- Dataclasses / JSON schema sketch: `Plan`, `PlanStep`, `AcceptanceCheck`, `VerifyResult`, `PlanStatus`.  
- Contract test placeholders (schema_version).  
- **No runtime behavior change.**

**Done when:** types importable; docs linked from ARCHITECTURE; CI green.

---

### Phase 1 — Plan store + state machine (PR1)

**Scope:** pure engine, no agent I/O.

| Deliverable | Detail |
|---|---|
| `voly/plan/types.py` | states, transitions, validation |
| `voly/plan/store.py` | atomic JSON under `.voly/plans/` (same pattern as `RunTracker`) |
| `voly/plan/engine.py` | `can_start(step)`, `transition()`, `topo_order()`, reject illegal moves |
| Unit tests | all transitions; gate blocks if dep not verified |

**Done when:** engine tests cover happy path + illegal transitions; no pipeline wiring yet.

---

### Phase 2 — Verifiers (PR2)

| Deliverable | Detail |
|---|---|
| `voly/plan/verify.py` | dispatch by `type` |
| Built-ins | `command`, `files_exist`, `files_missing`, `git_diff_nonempty`, `git_diff_contains`, `output_nonempty`, `output_regex` |
| Safety | command timeout; no shell unless explicit; cwd jail under plan `cwd` |
| Tests | temp dirs + fake git porcelain fixtures |

**Done when:** each check type has unit tests; fail closed on unknown type.

---

### Phase 3 — Wire executor path + CLI (PR3)

| Deliverable | Detail |
|---|---|
| `voly plan run <file>` | load YAML/JSON plan, execute steps with gates |
| Step runner | chat → gateway; executor → `AgentRunner` (reuse hybrid mapping) |
| Evidence | attach `WorkReport` + verify_log to each step |
| Config | `plan.enabled` / `mode` |
| Telemetry | extend `TaskEvent` (bump `schema_version` if needed) or nested `plan` dict |
| CLI | `voly plan status <id>`, `voly plan show <id>` |

**Done when:** smoke test runs a 2-step plan (write file → `files_exist` → gate → second step); failure stops chain in `active` mode.

---

### Phase 4 — Multi-agent integration (PR4)

| Deliverable | Detail |
|---|---|
| Bridge | `TaskDecomposer` / lead assignments → `Plan` steps (role, depends_on, mode from hybrid) |
| Acceptance defaults | implement roles: `git_diff_nonempty` (opt-in) or empty; tester: prefer `command` if `has_tests` from scanner |
| Shadow mode default | log verify results next to assignments without blocking |
| UI | step status badges on multi-agent panel (minimal) |
| RunRecord | `plan_id`, per-step status snapshot |

**Done when:** complex A2A task with `plan.mode=active` cannot start developer before architect `verified`; verify failure surfaces in UI/CLI.

---

### Phase 5 — Criteria compiler + DX (PR5, optional)

| Deliverable | Detail |
|---|---|
| DSPy / heuristic | `success_criteria` text → draft `acceptance[]` (always reviewable) |
| Project scanner hooks | suggest `pytest` / `npm test` command from `ProjectProfile` |
| Docs | user guide: authoring plans, check types, shadow vs active |
| Landing (voly_web) | one sentence on gated multi-step plans (only after active is real) |

---

### Later (Rung C — not in this proposal’s MVP)

- Checkpoint/resume mid-plan after process crash  
- Human approve gates  
- Soft LLM-as-judge checks  
- Federation: remote agent must return verify evidence  

---

## Acceptance criteria (proposal-level)

1. **Enforced step-status:** illegal transition raises / is rejected; only engine mutates status.  
2. **Automatic acceptance checks:** at least the v1 table above works without LLM.  
3. **Gate:** step with unmet deps never enters `running` in `active` mode.  
4. **Shadow mode:** same pipeline, no block, metrics on would-block rate.  
5. **Reuse:** no second executor stack; AgentRunner + AIGateway remain sole file/text exits.  
6. **Project-agnostic:** sample plan in `tests/` only; no product missions in core.  
7. **Observability:** plan id + per-step status visible via CLI and TaskEvent.  
8. **Docs:** ARCHITECTURE + pipeline + this proposal kept in sync with each PR.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Overbuilding a workflow engine | Cap scope: linear/DAG steps, local JSON store, no durable queues |
| Flaky `command` checks | Timeouts, clear fail messages, retries capped; document non-flake rules |
| Agents game soft checks | Prefer filesystem/tests; discourage sole use of `output_regex` |
| Empty acceptance = auto-pass | Log warning; recommend scanners to suggest checks; metrics on auto-pass rate |
| Schema churn on TaskEvent | Nested `plan` blob first; version field; contract tests |
| Cost of re-runs on fail | Retry only failed step; don’t re-run verified prefix |

---

## Alternatives considered

| Option | Why not for v1 |
|---|---|
| **Prompt-only “mark TODO done”** | Self-report; doesn’t solve the gap |
| **LLM judge as only gate** | Expensive, non-deterministic, still not evidence |
| **External Temporal/DBOS** | CLAUDE.md: no custom workflow engine without explicit ask; overkill for local agent runs |
| **Only extend Assignment.ok** | Still process-complete, not acceptance-complete |
| **Git hooks only** | No multi-step plan model; no chat-role steps |

---

## Success metrics (after Phase 4)

- **Gate effectiveness:** share of multi-step runs where a later step was blocked by failed verify (shadow → active).  
- **False stop rate:** verifies that fail but human marks OK (manual tag or issue).  
- **Plan completion rate:** `verified` terminal vs `failed` mid-plan.  
- **Cost of retries:** extra $ from failed-then-retry steps (TaskEvent).  

---

## Implementation checklist (engineering)

```text
[x] PR0  docs/proposals/plan-gate-verification.md + ARCHITECTURE pointer
[x] PR1  voly/plan/{types,store,engine}.py + unit tests
[x] PR2  voly/plan/verify.py + built-in checks + tests
[x] PR3  CLI voly plan * + AgentRunner/gateway step runner + config
[ ] PR4  A2A bridge + shadow/active + RunRecord/TaskEvent/UI chips
[ ] PR5  criteria compiler + scanner suggestions + user docs (+ optional landing)
```

---

## One-line pitch (for chats / README)

> Voly already orchestrates agents and records evidence; this work adds a **plan state machine**, **automatic acceptance checks**, and a **hard gate** so the next step starts only after the previous step is **verified** — not merely “the model said it was done.”

---

## Changelog

| Date | Note |
|---|---|
| 2026-07-09 | Initial draft from plan-following / verification gap analysis |
| 2026-07-09 | PR1: `voly/plan/{types,store,engine}.py` + `tests/test_plan_engine.py` |
| 2026-07-09 | PR2: `voly/plan/verify.py` + `tests/test_plan_verify.py` |
| 2026-07-09 | PR3: `PlanRunner`, `voly plan` CLI, `PlanConfig`, tests |

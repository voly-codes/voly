# Plan gates — authoring guide (Rung B)

Plan gates make multi-step agent work **stateful and verifiable**: each step has a
status, dependents wait for **verified** priors, and acceptance checks prove work
with evidence (files, git, commands) — not model self-report.

Design: [`docs/proposals/plan-gate-verification.md`](../proposals/plan-gate-verification.md).

---

## When to use

| Mode | Behavior |
|---|---|
| `off` | Plan subsystem not attached to multi-agent (CLI `voly plan run` still works) |
| `shadow` | Verifiers run and log; failed checks **soft-verify** so the chain continues |
| `active` | Hard gate: failed acceptance → step `failed`; dependents do not start |

Config (`voly.yaml`):

```yaml
plan:
  enabled: true
  mode: shadow          # start here; switch to active when checks are solid
  store_dir: .voly/plans
  a2a_attach: true      # multi-agent uses the same gates
  chat_require_output: true
  executor_require_git_diff: false
  executor_file_line_limit: 300
  architect_approved_file_line_limit: 500
  command_timeout_seconds: 120  # pip install -e . + pytest on greenfield projects can exceed 60s
  file_line_limit_exclude_patterns: []  # extra basenames/prefixes on top of built-in exclusions
  tester_command: ""    # or "pytest -q" / filled from scanner when empty
```

Bare `pytest -q` / `.venv/bin/pytest -q` is **scoped at verify time** to
`test_*.py` / `*_test.py` paths from the role's (or prior executor)
`files_touched` when present — so greenfield scaffolds do not wait on the
entire suite before `.venv` is ready. In **shadow** mode, a failed verify still
force-opens the gate; the warning log includes the scoped `argv` when present.

Env: `VOLY_PLAN_ENABLED`, `VOLY_PLAN_MODE`.

---

## Author a plan file

```yaml
# plan.yaml
schema_version: 1
plan_id: auth-refactor
cwd: /path/to/project
task: "Add JWT auth"
steps:
  - id: design
    role: architect
    mode: chat
    task: "Design JWT auth modules and risks"
    # empty acceptance → auto-verified after successful run
    # or:
    # success_criteria: |
    #   - short architecture summary
    # → compiler drafts output_nonempty (always review)

  - id: implement
    role: developer
    mode: executor
    depends_on: [design]
    task: "Implement JWT auth in src/auth.py"
    acceptance:
      - type: files_exist
        paths: [src/auth.py]
      - type: git_diff_nonempty

  - id: test
    role: tester
    mode: executor
    depends_on: [implement]
    task: "Add and run tests"
    acceptance:
      - type: command
        run: pytest -q
        expect_exit: 0
```

Load & run:

```bash
voly plan validate plan.yaml
voly plan run plan.yaml --mode active --cwd /path/to/project
voly plan status auth-refactor
voly plan show auth-refactor
```

---

## Step execution attribution and dependency handoff

`PlanStep.cost_usd`/`duration_ms` are populated by `PlanRunner`'s default
`_exec_chat`/`_exec_executor` (from the `AIGateway.chat()` response's token
usage, and from `ExecutorResult.cost_usd`/`duration_ms` respectively) — not
by an injected `chat_fn`/`executor_fn` test double, which owns its own
return shape and leaves both at `0.0`. `voly plan show` and any Plan-level
aggregation (e.g. `WorkflowResult.cost_usd` — see `docs/backend/sdk.md`) can
sum these across steps.

A step's instruction never templates or interpolates a prior step's output —
`PlanStep`/`AcceptanceCheck` carry no such syntax. Instead, `PlanRunner`
prepends each `depends_on` entry's stored `output` as a `### <dep_id>`
context block (capped at 4000 chars per dependency) before the step's own
`task`, so a step that depends on a prior one is never run blind to what
that prior step actually produced. Only declared dependencies are included —
unrelated sibling steps' output never leaks in.

---

## Parallel chat waves, resume, cancellation and stale recovery

Config: `workflow_sdk.*` (`voly.yaml`, `VOLY_WORKFLOW_SDK_*`) — see
`docs/backend/config.md`. This is a `PlanRunner` capability, not something
`Workflow` (`docs/backend/sdk.md`) implements itself, so any Plan benefits —
hand-authored `plan.yaml`, A2A-bridged, or SDK-built.

**Waves.** Each iteration of `run()`'s loop looks at every currently
runnable step (`PlanEngine.runnable_steps()` — by construction, steps that
are simultaneously runnable never depend on each other). If two or more are
`mode: chat`, up to `workflow_sdk.max_parallel_nodes` of them run
concurrently in a `ThreadPoolExecutor`; `mode: executor` steps always run
one at a time regardless — they share the Plan's single `cwd`, so two must
never write concurrently. Chat steps never touch the filesystem, so mixing
one executor step's turn with a chat wave is unnecessary to reason about:
the scheduler simply never puts more than one executor step in flight.

Only the network call phase runs in a worker thread (`_run_chat_step_body`,
mutating only that step's own `output`/`cost_usd`/`duration_ms`); every
`Plan`-level mutation (`engine.transition`, `_verify`) happens back in the
calling thread, one step at a time, once every worker in the wave has
returned — mirroring the split-phase pattern `voly.a2a.multiagent_run`
already uses for the same reason (a worker thread must never touch shared
Plan/PlanStep state that another thread could be mutating at the same time).
`node_results`/wave-member processing order is always the wave's declared
order, never completion order.

**Resume.** `PlanRunner.resume(plan_id)` reloads the persisted Plan and
calls `run()` again — no separate "paused" state exists to restore. Before
resuming, `run()` recovers any step stuck in `running` for longer than
`workflow_sdk.stale_running_seconds` (transitioned to `failed`, so the
normal `default_on_verify_fail` policy decides what happens to it) — that
only happens if the process that started it crashed mid-step, since a live
`run()` never revisits a step already `running`.

**Cancellation.** `PlanRunner.cancel(plan_id)` loads the Plan, calls
`PlanEngine.abort()`, and saves — safe to call from another thread or
process while a `run()` for the same `plan_id` is in flight. The run loop
re-reads the persisted status before it would otherwise overwrite it with
its own progress (after every step/wave, and after a retry attempt) and
adopts an external abort it finds there; this closes the window where the
runner's own next save would otherwise silently clobber a `cancel()` that
landed while a step was mid-flight. It does not interrupt a network/executor
call already in progress — cancellation is cooperative, checked between
steps/waves, not preemptive.

**Workflow-level timeout.** `run(..., timeout_seconds=...)` bounds the whole
call's wall-clock time. On expiry the Plan is left **resumable**, not
failed or aborted: whatever completed stays `verified`, and anything
mid-flight is picked up by stale-running recovery on the next
`run()`/`resume()` once `stale_running_seconds` elapses.

---

## Acceptance check types

| `type` | Pass when |
|---|---|
| `command` | `run` exits with `expect_exit` (`shell=False`, timeout, cwd-jailed) |
| `files_exist` | all `paths` exist under plan `cwd` |
| `files_missing` | none of `paths` exist |
| `git_diff_nonempty` | dirty porcelain / before-after change (optional path filter) |
| `git_diff_contains` | changed paths match `paths` or `pattern` |
| `file_line_limit` | every changed text file is within `max_lines`; binary and generated/lock files are skipped (plus `exclude_patterns`) |
| `output_nonempty` | agent output non-empty |
| `output_regex` | agent output matches `pattern` |
| `human_review` | never passes/fails through this dispatch — resolved out-of-band (see below) |
| `action_succeeded` | never passes/fails through this dispatch — resolved out-of-band (see below) |

Unknown types **fail closed**.

### General approval gates (any Plan)

A step whose acceptance includes `human_review` is a pause point, not a
synchronous check — `voly/plan/approval.py::decide(store, plan_id, step_id,
decision, *, comment="")` is the generic primitive that resolves it, on any
Plan (not only business Decisions): idempotent on a repeated identical
decision, fails closed (`ApprovalConflictError`) on a conflicting one or on a
step that hasn't reached `verifying` yet.

`PlanRunner` cooperates specifically so this stays a pause instead of a
failure:

- `_verify()` special-cases `human_review`/`action_succeeded` — it never
  routes them through `complete_verification()` (which would fail the step),
  and critically **`mode: shadow`'s soft-open never applies to them either**:
  shadow mode force-verifies an ordinary failed quality check, but a
  human/action gate is not a quality signal to wave through. The step stays
  parked in `verifying` either way.
- `run()`'s "nothing runnable" branch distinguishes a step legitimately
  parked in `running`/`done`/`verifying` (pause — `plan.status` stays
  `running`) from an actual dependency deadlock (`pending` steps with no
  in-flight work anywhere — real failure, `plan.status = failed`).
- `resume(plan_id)` reloads the Plan from `PlanStore` and calls `run()`
  again — no separate "paused" state to restore; once `approval.decide()`
  moves the step to `verified`, its dependents are runnable on the next call.

A step pre-seeded at `status: verifying` (an approval gate has no task of its
own to execute — the same convention `DecisionService` uses for
`approve-option`) is never picked up by `runnable_steps()` at all, so it hits
the "nothing runnable" pause path immediately rather than `_verify()`; both
paths are covered in `tests/test_plan_approval.py`.

### Business Decision plans

Active business sensing reuses this FSM as a two-step Plan (`mode: business`).
`approve-option` waits in `verifying` for explicit human feedback; its
dependent `execute-action` stays `pending` and cannot start. Approval performs
the legal `verifying → verified` transition. Rejection performs
`verifying → failed` and keeps the action blocked. Identical repeated feedback
is idempotent and a conflicting decision fails closed.

`human_review` and `action_succeeded` are registered `KNOWN_CHECK_TYPES` (so a
generic caller of `run_check`/`verify_step` gets a clear message instead of
"unknown check type" — see the general section above for why the generic
dispatch always reports `ok=False` for both). Business Decisions resolve them
via `voly.decisions.DecisionService` specifically, not the generic
`voly.plan.approval` primitive: `decide()` transitions `approve-option`
directly from an explicit `POST /api/decisions/{plan_id}/feedback`, and
`execute()` transitions `execute-action` directly from a real business
Executor's result. Business Plans never run through `PlanRunner` at all —
`PlanRunner.run()` refuses `mode: business` steps outright (fails the step
immediately, runs neither chat nor executor) rather than misinterpreting one
as a chat prompt or generic executor task.

CLI: `voly decide list|approve|reject|execute`.

Command checks are platform-neutral, but the command itself must name an
executable available on the target OS. Tests and generated examples should use
the active Python interpreter rather than Unix-only utilities such as `true`,
`false`, or `sleep`. Captured command output is decoded explicitly as UTF-8 with
replacement, matching executor subprocess handling. The verifier also sets
`PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8:replace` in the child environment so
Python checks emit the same encoding on Windows instead of the local code page.

Verifier modules (`voly/plan/`; public import remains `voly.plan.verify`):

| Module | Contents |
|---|---|
| `verify_types.py` | `VerifyResult` / `VerifyContext`, check-type constants |
| `verify_git.py` | `safe_join`, `ensure_git_repo`, porcelain helpers |
| `verify_checks.py` | built-in handlers, `run_check` / `run_acceptance` |
| `verify.py` | `verify_step` / `complete_verification` + re-exports |

### Executor file-size policy

Attached A2A plans add `file_line_limit` to every executor role by default.
The verifier checks `files_touched`, falling back to the git before/after
porcelain delta. A file over 300 physical lines fails verification.

**Generated/lock files are always excluded** from `file_line_limit`
(`voly/plan/verify_checks.py`): basenames in `_GENERATED_BASENAMES`
(`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`,
`Pipfile.lock`, `Cargo.lock`, `go.sum`, `composer.lock`, `.coverage`) and paths
under `_GENERATED_PREFIXES` (`node_modules/`, `.venv/`, `venv/`, `__pycache__/`,
`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`). Executor agents
cannot control the size of these files — `npm install` / `pip install -e .` /
`cargo build` generate them as side effects, and flagging them would hide real
violations. Skipped paths are reported in the check detail as
`skipped_generated`. Project-specific extras come from
`plan.file_line_limit_exclude_patterns` in `voly.yaml` (wired through
`AcceptanceCheck.exclude_patterns` by `voly/plan/bridge.py`); a pattern matches
either an exact basename or a path prefix.

An architect dependency may raise the limit to the configured cap (500) only
with both exact plan markers:

```text
FILE_LINE_LIMIT: 500
FILE_LINE_LIMIT_REASON: cohesive parser requires one module to preserve its invariant
```

The reason must contain at least 10 non-whitespace characters. Missing or
malformed markers leave the 300-line limit in force. In `active` mode the failed
check blocks dependents; in `shadow` mode it is recorded in `verify_log`.

---

## Draft from free-text criteria (PR5)

Never auto-trust — always review drafts before `mode: active`.

```bash
voly plan criteria "- create src/auth.py
- tests pass
- output contains DONE" --yaml
```

Or put free text on a step:

```yaml
steps:
  - id: impl
    mode: executor
    task: "..."
    success_criteria: |
      - create src/auth.py
      - tests pass
    # acceptance:  # optional override; if omitted, criteria are compiled to a draft
```

Programmatic:

```python
from voly.plan import compile_success_criteria
draft = compile_success_criteria(text)
assert draft.review_required
checks = draft.checks  # list[AcceptanceCheck]
```

---

## Scanner suggestions (PR5)

```bash
voly plan suggest --cwd /path/to/project
# tester_command: .venv/bin/pytest -q   # when .venv/bin/pytest exists
# languages: python
```

When multi-agent runs with `plan.enabled` and empty `tester_command`, VOLY may
fill it once from `ProjectScanner` for that run only (does not rewrite `voly.yaml`).
If the scan picks `pytest` and `{cwd}/.venv/bin/pytest` exists, the auto-fill
prefers `.venv/bin/pytest -q` so the plan gate uses the project's dependencies.

---

## Multi-agent (A2A)

With `plan.enabled` + `a2a_attach` + `mode` shadow|active, `run_local` mirrors each
role as a plan step (`0:architect`, `1:developer`, …). UI shows `plan_status`
badges; `voly runs show <task_id>` shows `plan_id` and step snapshots.

Defaults:

- chat roles → `output_nonempty` if `chat_require_output`
- executor → `git_diff_nonempty` only if `executor_require_git_diff`
- executor → `file_line_limit` (300 by default; 500 with strict architect approval)
- tester → `command` if `tester_command` set

---

## CLI cheat sheet

| Command | Purpose |
|---|---|
| `voly plan validate FILE` | structure + topo order |
| `voly plan run FILE` | execute with gates |
| `voly plan list` / `show` / `status` | store under `.voly/plans` |
| `voly plan criteria TEXT` | draft checks from free text |
| `voly plan suggest --cwd PATH` | draft from scanner |

---

## Recommended rollout

1. Author plans or enable multi-agent with **`mode: shadow`**.
2. Fix flaky checks (`command`, paths).
3. Switch to **`mode: active`** for CI / production agent runs.
4. Keep LLM-generated criteria as **drafts** until a human or policy promotes them.

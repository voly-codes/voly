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
  command_timeout_seconds: 60   # full project pytest; hung command fails before 60s
  tester_command: ""    # or "pytest -q" / filled from scanner when empty
```

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

## Acceptance check types

| `type` | Pass when |
|---|---|
| `command` | `run` exits with `expect_exit` (`shell=False`, timeout, cwd-jailed) |
| `files_exist` | all `paths` exist under plan `cwd` |
| `files_missing` | none of `paths` exist |
| `git_diff_nonempty` | dirty porcelain / before-after change (optional path filter) |
| `git_diff_contains` | changed paths match `paths` or `pattern` |
| `file_line_limit` | every changed text file is within `max_lines`; binary files are skipped |
| `output_nonempty` | agent output non-empty |
| `output_regex` | agent output matches `pattern` |

Unknown types **fail closed**.

### Executor file-size policy

Attached A2A plans add `file_line_limit` to every executor role by default.
The verifier checks `files_touched`, falling back to the git before/after
porcelain delta. A file over 300 physical lines fails verification.

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

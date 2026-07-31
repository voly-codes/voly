# Lifecycle hooks

Phase 7 defines harness-neutral lifecycle events and a constrained adapter.
Hooks are disabled by default and are not Python imports or arbitrary shell
callbacks. Only built-in allowlisted handlers can run.

## Contract

`HookEvent` schema version 1 carries an event type, event/run/project IDs,
project cwd, timestamp, and structured payload. Supported events:

- `run_started`, `task_observed`, `files_changed`;
- `before_verify`, `after_verify`;
- `budget_threshold`, `run_finished`.

Every `HookManifest` must declare:

- hook ID and allowlisted handler;
- subscribed events;
- complete permission set;
- timeout in `(0, 300]` seconds;
- an idempotency strategy;
- `fail_open` or `fail_closed`.

Imported manifests are always stored with `enabled: false`, regardless of their
source value. `voly hooks approve <id>` is a separate explicit operation.

## Built-in constrained handlers

| Handler | Required permissions | Behavior |
|---|---|---|
| `observe` | `observe` | Records event type and payload keys |
| `scoped_tests` | `execute_tests` | Runs explicit argv with `shell=False`, project cwd, captured output and timeout; executable must be an allowlisted test tool |
| `secret_scan` | `read_project`, `scan_secrets` | Scans only declared changed files under cwd |
| `docs_check` | `read_project`, `read_docs` | Rejects backend code changes without docs/OpenWiki changes |
| `budget_notify` | `notify_budget` | Records threshold and spend notification |

Unknown handlers and incomplete permissions are blocked. File paths are
resolved below the project root, large files are skipped, and hook output is
bounded.

## Failure and audit semantics

The adapter returns `HookResult`; it never mutates executor/run state.
`fail_open` failures allow the harness to continue. `fail_closed` produces
`proceed: false`, leaving the caller to stop at its normal transaction boundary.
One failing hook does not stop remaining audit hooks.

Each attempted automatic hook writes the same result to separate local evidence
and telemetry JSONL logs. Duplicate idempotency keys are recorded as
`duplicate` but the handler is not rerun.

```yaml
hooks:
  enabled: false
  registry_path: .voly/hooks/manifests.json
  state_path: .voly/hooks/idempotency.json
  evidence_log: .voly/hooks/evidence.jsonl
  telemetry_log: .voly/hooks/telemetry.jsonl
```

Workflow:

```bash
voly hooks import hook.json --cwd .
voly hooks approve docs-check --cwd .
voly hooks dispatch files_changed run-123 \
  --project-id project-a --payload event.json --cwd .
```

The dispatcher refuses to run while `hooks.enabled` is false. Runtime hook
state is ignored under `.voly/hooks/`.

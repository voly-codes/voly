# Executors — Backend Reference

Executor — runtime that **actually works with files** in the target project.
Pipeline/AIGateway — text-only inference only. Executor = tool for writing to disk.

All executors inherit from `voly/executor/base.py:Executor` and return `ExecutorResult`.

---

## Billing fallback chain

When a paid executor returns a billing error, `AgentRunner` automatically walks:

```
claude-code  →  cursor  →  deepseek  →  wrangler  →  opencode  →  zen
```

- `claude-code` — Anthropic account runs out of credits
- `cursor` — Cursor API (`CURSOR_API_KEY`)
  (`CursorExecutor` patches `cursor-sdk` auth-token generators so tokens never
  start with `-`; otherwise `cursor-sdk-bridge` rejects them as
  `Missing value for --tool-callback-auth-token` and retries once.
  `cursor-sdk` reports no token usage, so `ExecutorResult` tokens/cost are
  char-based estimates — ~4 chars/token priced via the telemetry cost table;
  `metadata.usage_estimated: true` marks them)
- `deepseek` — DeepSeek API file-writing executor (`DEEPSEEK_API_KEY`)
- `wrangler` — CF Workers AI via local wrangler dev (separate CF billing)
- `opencode` — OpenCode Go (free models first, then user's own provider keys)
- `zen` — opencode.ai Zen models (free tier / subscription)

Detection: `ExecutorResult.billing_error = True` — `_is_billing_error` in
`voly/executor/base.py` delegates to the semantic classifier
(`voly/ai_gateway/error_classifier.py`): fires only for terminal quota/account
states; a transient rate-limit 429 is NOT billing. The `"402"` and `"billing"`
text signals require HTTP-status-style framing (`"error 402"`, `"402: payment
required"`) or a specific billing phrase (`"billing issue"`, `"billing
error"`, …) — a bare `"402"` inside an unrelated number (port, PID) or a
passing mention of the word "billing" does not trigger a false positive.

Only file-writing executors are in the chain.

### Capability-aware fallback

When capability routing is enabled (`capability.enabled: true` in `voly.yaml`, or
`VOLY_CAPABILITY_ENABLED=1`), `AgentRunner` replaces the static
`BILLING_FALLBACK_CHAIN` order with a capability-scored chain from
`voly/capability/fallback.py` (`build_fallback_chain()`).

Scoring uses the same weighted formula as executor matching — see
[capability.md](./capability.md) (`routing_score()` weights table).

**Degraded mode:** if no executor passes hard gates, or the top routing score is
below **0.30**, the static chain is used unchanged and a warning is logged
(`capability fallback degraded`). This also applies when capability is enabled
but no materialized profiles exist under `.voly/capability/profiles/` yet.

**Verify locally:**

```bash
voly capability match backend --executors claude-code --executors cursor --executors zen
```

Materialize seed profiles first (`voly capability show claude-code` writes the
seed copy), then enable `VOLY_CAPABILITY_ENABLED=1` and trigger a billing fallback
run — `[CHAIN:BILLING_FALLBACK]` should follow capability rank, not static order.

---

## Executor table

| Executor | File writes | Billing | Fallback position |
|---|---|---|---|
| `claude-code` | yes — Claude CLI | Anthropic | 1st in chain |
| `cursor` | yes — Cursor Agent SDK (`cursor-sdk`) | Cursor | 2nd in chain |
| `deepseek` | yes — DeepSeek file executor | DeepSeek API | 3rd in chain |
| `wrangler` | yes — LocalPatchApplier | Cloudflare Workers AI | 4th in chain |
| `opencode` | yes — OpenCode CLI | opencode.ai | 5th in chain |
| `zen` | yes — opencode CLI | free / opencode subscription | 6th (last resort) |
| `cf-containers` | remote — CF Container / Sandbox | Cloudflare Containers | standalone (PoC) |
| `mimo` | no — text only | MiMo API | NOT in chain |

---

## ClaudeCodeExecutor (`voly/executor/claude_code.py`)

Runs `claude` CLI as a subprocess. Detects billing errors in stdout/stderr.

```python
result = executor.run(task, cwd="/path/to/project", max_turns=30, timeout=300)
# result.billing_error = True → triggers fallback to wrangler
```

Env: `ANTHROPIC_API_KEY`

### pxpipe sidecar

`ClaudeCodeExecutor` can optionally route only the `claude` subprocess through
`pxpipe`, a local token-saving Anthropic-compatible proxy. This does not affect
Pipeline/AIGateway text inference; it is executor-only and therefore stays on
the Layer B file-capable path.

```bash
voly pxpipe start
VOLY_PXPIPE_ENABLED=true voly run --executor claude-code "fix tests" --cwd /repo
```

When enabled and reachable, VOLY injects:

```env
ANTHROPIC_BASE_URL=http://127.0.0.1:47821
PXPIPE_MODELS=claude-fable-5,gpt-5.6
```

Only the subprocess env is changed. If `pxpipe` is not running and
`VOLY_PXPIPE_AUTO_START=false`, the executor runs normally. If an
`ANTHROPIC_BASE_URL` is already set, VOLY keeps it unless
`VOLY_PXPIPE_OVERRIDE_BASE_URL=true`.

Rendered prompt PNGs are saved locally when the sidecar is started through VOLY:

```bash
voly pxpipe start
# PNG inbox: .voly/pxpipe/images/_inbox
```

`AgentRunner` moves new PNGs from the inbox into
`.voly/pxpipe/images/<task_id>/`, adds them to `TaskEvent.artifacts`, and the UI
serves them through `/api/tasks/<task_id>/artifacts/<name>`.

---

## WranglerExecutor (`voly/executor/wrangler.py`)

Calls CF Workers AI through a local `wrangler dev` Worker, then applies the response
to local files using `LocalPatchApplier`.

**How it works:**
1. `is_available()` — GET `http://127.0.0.1:8787/health` with 2s timeout
2. Gather local code context via `_gather_context()` (grep relevant files)
3. POST `/infer` → CF Worker calls AI model → returns FILE blocks
4. `LocalPatchApplier(cwd).apply(response)` — writes files to disk

```bash
# Start the worker before using wrangler executor:
cd cf-workers/agent && wrangler dev
```

Env: `WRANGLER_DEV_URL` (default `http://127.0.0.1:8787`), `WRANGLER_AI_MODEL`, `WRANGLER_DEV_TOKEN`

The CF Worker (`cf-workers/agent/src/infer.ts`) routes inference through:
1. CF AI Gateway `/compat` endpoint (if `CF_ACCOUNT_ID` + `CF_AIG_TOKEN` set) — uses route schema from CF Dashboard
2. `env.AI.run()` direct binding — fallback when gateway not configured

Default model: `@cf/moonshotai/kimi-k2.7-code`

---

## CfContainersExecutor (`voly/executor/cf_containers.py`) — PoC

Cloud-native path: runs the task inside a **Cloudflare Container** via the
sandbox-spike Worker (`voly-cloud/cf-workers/sandbox-spike`), which uses the
Sandbox SDK (`@cloudflare/sandbox` → Containers).

**How it works:**
1. `is_available()` — GET `{base}/health` (2s timeout)
2. POST `{base}/runs` with Bearer JWT + `{task, mode, repo?}`
3. Map Worker JSON → `ExecutorResult` (`not_available` when Worker down)

**Modes** (`VOLY_CF_CONTAINERS_MODE`):
| Mode | Behavior |
|---|---|
| `probe` (default) | Container smoke: uname / python / writeFile |
| `claude-code` | Claude Code CLI inside the container (needs Worker secrets) |

```bash
# 1) Start Worker (Docker + Workers Paid for real containers; FORCE_STUB=1 for JWT-only stub)
cd voly-cloud/cf-workers/sandbox-spike
npx wrangler dev --ip 127.0.0.1 --port 8791 --local

# 2) Mint JWT (same secret as Worker JWT_SECRET)
export VOLY_CF_CONTAINERS_URL=http://127.0.0.1:8791
export VOLY_CF_CONTAINERS_TOKEN=<tenant-jwt>

# 3) Run
voly run --executor cf-containers "probe sandbox"
```

Env:
- `VOLY_CF_CONTAINERS_URL` (default `http://127.0.0.1:8791`)
- `VOLY_CF_CONTAINERS_TOKEN` (required — tenant JWT)
- `VOLY_CF_CONTAINERS_MODE` (`probe` \| `claude-code`)
- `VOLY_CF_CONTAINERS_REPO` (optional git URL for claude-code mode)

**PoC limits (document for product):**
- Not in `BILLING_FALLBACK_CHAIN` yet — opt-in only (`--executor cf-containers`)
- Local `cwd` is not synced into the container (remote workspace / optional `repo`)
- Cold start latency can be seconds–minutes on first image build
- Requires Workers Paid + Docker for real Containers; stub mode proves JWT path only
- Auth is JWT to the Worker, not the user's local Claude/Cursor credentials

**Selection plan:** keep as explicit executor until smoke tests pass in CI; later
candidate for hosted-only default when `VOLY_CF_CONTAINERS_URL` is set.

---

## LocalPatchApplier (`voly/executor/patch.py`)

Parses LLM response and writes files to disk. Supports two formats:

**FILE blocks** (primary format):
```
### FILE: path/relative/to/cwd.ext
```lang
...complete file content...
```
```

**Unified diffs** (secondary):
```
--- a/path.py
+++ b/path.py
@@ -10,4 +10,6 @@
```

Security: path traversal check — `full_path.startswith(cwd + os.sep)` required
(`_resolve_safe_path`). Applied to **both** reads and writes: the unified-diff
path reads the target file before computing the patched content, so a
model-supplied `+++ b/../../etc/passwd` diff header is rejected before the
read happens, not just before the (separately guarded) write.

Returns `PatchResult` with `.applied` list and `.summary()` method.

---

## ZenExecutor (`voly/executor/zen.py`)

Uses opencode CLI with Zen models (free tier). File-capable via CLI.
Used as the final fallback in the billing chain — always available without paid credits.

Env: `OPENCODE_API_KEY` (optional for free Zen tier)

**Project cwd:** both `ZenExecutor` and `OpenCodeExecutor` pass `opencode run --dir <abs_cwd>`
(via `_build_opencode_run_cmd` in `executor/base.py`) in addition to subprocess `cwd=`.
Subprocess cwd alone is not enough — OpenCode can resolve a different project root
(e.g. git root) and write outside the intended sandbox.

---

## Timeouts (total deadline)

All subprocess executors accept `timeout` (seconds) and kill the subprocess on
expiry (`subprocess.run(timeout=...)` + handled `TimeoutExpired`).
HTTP executors (`wrangler`, `mimo`, `deepseek`) pass it into the request timeout.

**`timeout` is the overall call deadline, not per-attempt.** Internal model-retry
loops (`zen._run_cli`, `opencode._run_cli` — up to ~9 models on billing errors)
share the deadline: each attempt gets the **remaining** time; if less than
`_MIN_ATTEMPT_SECONDS` (10s, `executor/base.py`) remains, the loop stops and the
result sets `metadata["deadline_exhausted"]=true` (on billing error,
`billing_error` is preserved so the chain can continue). Without this, a “300s”
call could silently stretch to 8×300s ≈ 40 minutes.

Timeout results are marked `metadata["timeout"]=true` (for telemetry and the
future stage-2 watchdog).

**Propagation:** `voly run --executor X --timeout N` (default 300) and
`voly runner --timeout N` → `AgentRunner.run(timeout=...)` → each executor,
including the fallback chain. Web: `timeout` field in `POST /api/run` (default 300).
`--model` / `-m` is passed through on both `voly run --executor` and `voly runner`
to `_build_executor(name, model=...)`. Default free model for `opencode`/`zen` is
`mimo-v2.5-free` (fallback sequence still includes deprecated models last).

**Failure messages:** `format_executor_failure()` / `executor_failure_details()` in
`executor/base.py` turn raw `ExecutorResult.error` into a prefixed message plus
optional `Hint:` next step (auth login, start Cursor IDE, install opencode, pick a
supported model). Used in `voly run`, `voly runner` CLI output, `POST /api/run`
SSE `done` payload (`error_message`, `error_class`, `error_hint`), and telemetry
(`TaskEvent.error` stores the formatted message; `chain_timelog` rows include
`error_message` / `error_hint`).
Note: the billing fallback chain gives each executor its **own** full timeout
(visible via `chain_timelog`) — multiplication only at the visible chain level,
not inside a single executor.

---

## AgentRunner billing fallback (`voly/runner/`)

Chain constants and `_build_executor` live in `executor_factory.py`;
`AgentRunner.run()` (in `agent_runner.py`) walks the chain.

```python
BILLING_FALLBACK_CHAIN = ["claude-code", "cursor", "deepseek", "wrangler", "opencode", "zen"]

# In AgentRunner.run():
if result.billing_error and executor_name in BILLING_FALLBACK_CHAIN:
    for fallback_name in chain[start_idx:]:
        # try next executor
        # logs: [CHAIN:BILLING_FALLBACK] claude-code → cursor  reason=...
        if not result.billing_error:
            break
```

### Retry-aware cost

Task cost stays accurate across retries — two folding levels, no double-counting:

1. **Executor-level** (`zen`/`opencode`): model-retry loops fold spend from
   abandoned attempts into the returned `ExecutorResult`
   (`_fold_retry_costs` in `executor/base.py`): `cost_usd`/tokens are totals;
   `metadata.retry_count` / `metadata.retry_cost_usd` isolate the retry share.
2. **Chain-level** (`AgentRunner`): spend from abandoned chain attempts goes into
   `TaskEvent` totals (`cost_usd`, `tokens`) and the
   `retry_count` / `retry_cost_usd` fields; the budget check (`budget_status`) uses
   the total. Each `chain_timelog` entry carries its own `cost_usd` /
   `input_tokens` / `output_tokens`.

Reading rule: `cost_usd` is always the full total (summing events does not
double-count); `retry_cost_usd` is the subset spent on failed attempts.

### Error classes and unrecognized-error metric (risk R4)

Billing detection is signature-based — if upstream rephrases an error, fallback
can silently stop firing. Two lines of defense:

1. **Contract tests** `tests/test_cli_contracts.py`: fixtures captured from
   real CLIs (claude 2.1.170 `--output-format json`, opencode 1.17.13
   NDJSON) — a format change fails the test, not production. Contract 2.1.x:
   `modelUsage` keys are camelCase (`inputTokens`/`outputTokens`); the parser
   accepts both styles.
2. **`error_class` metric**: `classify_failure()` (`executor/base.py`)
   classifies the final failure — `billing` / `not_available` / `timeout`
   (executor markers take priority) / `ErrorType.*` from the semantic
   classifier / **`unrecognized`**. Written to `TaskEvent.error_class` and every
   `chain_timelog` entry. Summary: `voly telemetry errors` — share of
   `unrecognized` among failed; growth means CLI format drift; update
   signature tables in `error_classifier.py` and contract fixtures.

Chain logs (see `logging.getLogger("voly.chain")`):
- `[CHAIN:START]` — first executor attempt
- `[CHAIN:RESULT]` — result + billing_error status
- `[CHAIN:BILLING_FALLBACK]` — billing error detected, switching
- `[CHAIN:FALLBACK_RESULT]` — fallback result
- `[CHAIN:DSPY_PLAN]` — DSPy refined the task before execution

---

## DSPy + executor path

When `dspy.enabled = true` and `dspy.mode != "off"`, `AgentRunner` runs the
`task_planner` DSPy program **before** the executor:

```
task → DSPy TaskPlanner (ChainOfThought) → refined_task + success_criteria
     → executor.run(refined_task, cwd=...)
     → result stored as example in dspy.datasets_dir/task_planner/
```

This creates (task, result) pairs for later `dspy.BootstrapFewShot` optimization.
See `docs/backend/dspy.md` for details.

---

## Smart dispatch (web UI)

`voly/web/routes/run.py` auto-promotes `executor="pipeline"` to `executor="claude-code"`
when the task requires code generation:

```
POST /api/run  executor=pipeline
   ↓ _needs_executor() → requires_code_gen = True
   ↓
executor=claude-code, cwd = req.cwd || config.default_cwd || VOLY_PROJECT_CWD
   ↓ AgentRunner → billing fallback chain if needed
```

Set `VOLY_PROJECT_CWD=/path/to/project` or `default_cwd` in `voly.yaml` so
the web UI knows where to write files.

---

## Adding a new executor

1. Create `voly/executor/my_exec.py` — inherit `Executor`, return `ExecutorResult`
2. Set `billing_error=True` when error indicates billing failure
3. Add to `EXECUTOR_NAMES` and `_build_executor()` factory in `executor_factory.py`
4. If file-capable and has its own billing: add to `BILLING_FALLBACK_CHAIN` in correct order
5. Update this doc and `docs/ARCHITECTURE.md`

---

## Safety policy (`voly/executor/safety.py`)

Guardrails enforced in `AgentRunner.run` **after** the executor finishes,
git-based (a pre-run `git stash create` snapshot lets rollback restore the
exact pre-run content, including files that were already dirty). Only files
whose `git status` changed during the run are ever touched; without a git
repo in `cwd` the policy degrades to a no-op with a warning.

| Policy (`executor_safety` in voly.yaml) | Trigger | Effect |
|---|---|---|
| `dry_run: true` (or `voly run --dry-run` / `RunRequest.dry_run`) | always | run executes normally, then **all** file changes are rolled back; `metadata.dry_run=true`, `metadata.dry_run_diff` keeps a truncated preview; `WorkReport` still lists the files; `success` unchanged |
| `protected_paths` (fnmatch; empty = defaults `.env*`, `*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`, `*.p12`, `.git/**`) | protected file touched | only the protected files are rolled back; `success=false`, `error="safety: protected path(s) modified…"`, `metadata.safety_violation`; the billing chain is NOT triggered |
| `max_files_touched` (0 = unlimited) | run touched more files | runaway change — the **whole** run is rolled back; `success=false` |

Log marker: `[CHAIN:SAFETY]`. Rolled-back paths land in
`metadata.safety_rolled_back`; `/api/run` responses surface `dry_run`,
`dry_run_diff`, `safety_violation`, `safety_rolled_back` when present.

Touched files are detected by **content** (`git diff --name-only` against the
pre-run snapshot), not porcelain status alone — a file that was already dirty
before the run and modified again by the executor is caught and restored to
its pre-run (dirty) content. Note: `WorkReport` file lists still come from
the porcelain delta, so such files may be missing from the report display —
report-side follow-up.

# Executors — Backend Reference

Executor — runtime, который **реально работает с файлами** в целевом проекте.
Pipeline/AIGateway — только text-only inference. Executor = инструмент записи в диск.

All executors inherit from `voly/executor/base.py:Executor` and return `ExecutorResult`.

---

## Billing fallback chain

When a paid executor returns a billing error, `AgentRunner` automatically walks:

```
claude-code  →  wrangler  →  zen
```

- `claude-code` — Anthropic account runs out of credits
- `wrangler` — CF Workers AI via local wrangler dev (separate CF billing)
- `zen` — opencode.ai Zen models (free tier / subscription)

Detection: `ExecutorResult.billing_error = True` — set when error text matches:
`"credit balance is too low"`, `"insufficient credits"`, `"402"`, etc.
(`_BILLING_PATTERNS` in `voly/executor/base.py`)

Only file-writing executors are in the chain. `deepseek`/`workers-ai` are text-only and cannot apply file changes — they must NOT appear here.

---

## Executor table

| Executor | File writes | Billing | Fallback position |
|---|---|---|---|
| `claude-code` | yes — Claude CLI | Anthropic | 1st in chain |
| `wrangler` | yes — LocalPatchApplier | Cloudflare Workers AI | 2nd in chain |
| `zen` | yes — opencode CLI | free / opencode subscription | 3rd (last resort) |
| `cursor` | yes — Cursor Agent IDE | Cursor | standalone |
| `opencode` | yes — OpenCode CLI | opencode.ai | standalone |
| `deepseek` | no — text only | DeepSeek API | NOT in chain |
| `mimo` | no — text only | MiMo API | NOT in chain |

---

## ClaudeCodeExecutor (`voly/executor/claude_code.py`)

Runs `claude` CLI as a subprocess. Detects billing errors in stdout/stderr.

```python
result = executor.run(task, cwd="/path/to/project", max_turns=30, timeout=300)
# result.billing_error = True → triggers fallback to wrangler
```

Env: `ANTHROPIC_API_KEY`

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

Security: path traversal check — `full_path.startswith(cwd + os.sep)` required.

Returns `PatchResult` with `.applied` list and `.summary()` method.

---

## ZenExecutor (`voly/executor/zen.py`)

Uses opencode CLI with Zen models (free tier). File-capable via CLI.
Used as the final fallback in the billing chain — always available without paid credits.

Env: `OPENCODE_API_KEY` (optional for free Zen tier)

---

## Timeouts (total deadline)

Все subprocess-executor-ы принимают `timeout` (секунды) и убивают подпроцесс по
истечении (`subprocess.run(timeout=...)` + обработанный `TimeoutExpired`).
HTTP-executor-ы (`wrangler`, `mimo`, `deepseek`) передают его в таймаут запроса.

**`timeout` — общий deadline вызова, не per-attempt.** Внутренние циклы перебора
моделей (`zen._run_cli`, `opencode._run_cli` — до ~9 моделей при billing-ошибках)
делят deadline: каждая попытка получает **оставшееся** время; при остатке меньше
`_MIN_ATTEMPT_SECONDS` (10s, `executor/base.py`) перебор останавливается, у
результата выставляется `metadata["deadline_exhausted"]=true` (при billing-ошибке
`billing_error` сохраняется — цепочка может продолжить). Без этого вызов «300s»
молча растягивался бы до 8×300s ≈ 40 минут.

Таймаут-результаты помечаются `metadata["timeout"]=true` (для телеметрии и
будущего watchdog этапа 2).

**Проброс:** `voly run --executor X --timeout N` (default 300) и
`voly runner --timeout N` → `AgentRunner.run(timeout=...)` → каждый executor,
включая fallback-цепочку. Web: поле `timeout` в `POST /api/run` (default 300).
Замечание: billing fallback-цепочка даёт каждому executor-у **свой** полный
timeout (прозрачно через `chain_timelog`) — умножение только на видимом уровне
цепочки, не внутри одного executor-а.

---

## AgentRunner billing fallback (`voly/runner/agent_runner.py`)

```python
BILLING_FALLBACK_CHAIN = ["claude-code", "wrangler", "zen"]

# In AgentRunner.run():
if result.billing_error and executor_name in BILLING_FALLBACK_CHAIN:
    for fallback_name in chain[start_idx:]:
        # try next executor
        # logs: [CHAIN:BILLING_FALLBACK] claude-code → wrangler  reason=...
        if not result.billing_error:
            break
```

### Retry-aware cost

Стоимость задачи достоверна при перезапусках — два уровня сворачивания, без двойного счёта:

1. **Executor-level** (`zen`/`opencode`): циклы перебора моделей сворачивают
   потраченное брошенными попытками в возвращаемый `ExecutorResult`
   (`_fold_retry_costs` в `executor/base.py`): `cost_usd`/токены — тоталы,
   `metadata.retry_count` / `metadata.retry_cost_usd` изолируют долю ретраев.
2. **Chain-level** (`AgentRunner`): потраченное брошенными попытками цепочки
   попадает в тоталы `TaskEvent` (`cost_usd`, `tokens`) и в поля
   `retry_count` / `retry_cost_usd`; бюджет-чек (`budget_status`) считает по
   тоталу. Каждая запись `chain_timelog` несёт свои `cost_usd` /
   `input_tokens` / `output_tokens`.

Правило чтения: `cost_usd` — всегда полный тотал (суммирование по событиям не
задваивает); `retry_cost_usd` — подмножество, потраченное на неудачные попытки.

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
3. Add to `EXECUTOR_NAMES` and `_build_executor()` factory in `agent_runner.py`
4. If file-capable and has its own billing: add to `BILLING_FALLBACK_CHAIN` in correct order
5. Update this doc and `docs/ARCHITECTURE.md`

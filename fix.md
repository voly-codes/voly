# Fix Log

Functional fixes are recorded here after commit. Entries use the exact short
commit hash and an English description.

- `8debfb8` — Fixed a real cross-thread/cross-process race found while
  building `PlanRunner.cancel()` (PR3 of the agent-workflow-sdk proposal):
  the run loop's own post-step `self.store.save(plan)` calls could silently
  clobber an external `cancel()`/`PLAN_ABORTED` that landed on disk while a
  step or wave was mid-flight, because the in-memory `Plan` object had no
  way to know about it until the next check. `run()` now re-checks the
  persisted status immediately before every such save
  (`_external_abort_requested`) and adopts an external abort instead of
  overwriting it — caught by
  `tests/test_plan_concurrency.py::test_cancel_stops_a_run_in_flight_from_another_thread`,
  which failed reliably before the fix.
- `13f270d` — Fixed three gaps found while adding the `Workflow` SDK builder
  (PR2 of the agent-workflow-sdk proposal): (1) neither `Plan` nor
  `PlanStep` tracked per-step cost/duration at all, so any aggregate-cost
  reporting over a Plan would have silently always read `0.0` — added
  `cost_usd`/`duration_ms` to `PlanStep`, populated only by
  `PlanRunner._exec_chat`/`_exec_executor`'s default (non-injected)
  implementations, so existing `chat_fn`/`executor_fn` test doubles are
  unaffected; (2) a dependent step's instruction never referenced its
  dependency's output — `PlanRunner` now prepends each `depends_on` step's
  stored output as context before running a step, so every Plan benefits,
  not only `Workflow`-built ones; (3) `Agent._run_executor` never folded
  `self.instructions` into the task the way `_run_chat` folds it into the
  system prompt — `Agent(instructions=..., mode="executor")` was silently
  dropping it.
- `a0e4eff` — Resolved the npm-reachable GitHub Dependabot alerts (44
  high/76 medium/14 low) across `cf-workers/*`, `ui/`, `headroom/*`. Bumped
  `@cloudflare/workers-types` v4→v5 with the `wrangler` version that now
  requires it in all 8 Workers, fixing the resulting real type errors
  (renamed Workers AI binding types in `agent`/`memory`; moved the
  `SqlStorage` generic from `.toArray<T>()`/`.one<T>()` to `.exec<T>()` in
  `spend`, query semantics unchanged) rather than suppressing them; each
  worker re-verified via `tsc --noEmit` and `wrangler check startup`.
  Removed the unused `@clerk/clerk-js` dependency from `ui/` (zero
  references in `ui/src`, source of 16 of its 18 alerts via a Solana
  wallet-adapter chain) — drops 486 unused packages. `npm audit fix` for
  `headroom/docs`/`sdk/typescript`/`plugins/openclaw`. Left open: 1 low
  Windows-only `esbuild` advisory in two `headroom` TS packages (not yet
  fixable upstream even with `--force`), and 6 Rust/cargo advisories in
  `headroom/Cargo.lock` — `cargo` isn't available in this environment, and
  `pyo3`'s 0.24→0.29 bump guards Python↔Rust FFI bindings, too risky to
  edit unverified.
- `b20bf40` — Fixed `PlanRunner._exec_chat`'s no-`chat_fn` fallback calling
  `AIGateway(self.config)` directly: `AIGateway.__init__` takes bare
  constructor args, not a `VOLYConfig`, so the config landed in the unrelated
  `provider` slot and every DLP/spend/cache/fallback setting silently stayed
  at `AIGateway`'s bare defaults regardless of what the caller configured.
  Extracted the governed wiring `Pipeline.gateway` already used into
  `voly.ai_gateway.gateway_from_config()` and pointed `PlanRunner` at it.
  Also fixed `PlanRunner`'s `human_review`/`action_succeeded` acceptance
  handling: a step with either check used to be routed through
  `complete_verification()`, which would fail it outright, and `mode: shadow`
  would then force-verify it via the normal soft-open — silently bypassing a
  human-approval/action gate the same way shadow mode bypasses an ordinary
  failed quality check. `_verify()` now parks such a step in `verifying`
  instead, exempt from shadow's soft-open either way; added
  `voly/plan/approval.py` (a generic, `DecisionService`-independent
  approve/reject primitive) and `PlanRunner.resume()` so a paused Plan can
  actually be unblocked and continued.
- `2a65598` — Closed a DNS-rebinding SSRF gap in `HttpActionExecutor`: the IP
  validated as public was checked once, then urllib re-resolved the hostname
  independently at connect time, so a rebinding attacker could answer public
  on the check and private on the real connect. The validated IP is now
  pinned to the actual TCP connect (`_PinnedHTTPSConnection`/
  `_PinnedHTTPSHandler`) while TLS SNI/cert verification still targets the
  original hostname; `NotifyExecutor` inherits the fix since it delegates to
  `HttpActionExecutor`. Also registered `human_review`/`action_succeeded` as
  known (fail-closed, `DecisionService`-owned) acceptance-check types in
  `voly/plan/verify_checks.py` so a generic `run_check`/`PlanRunner` caller no
  longer hits "unknown check type", and hardened `PlanRunner.run()` to refuse
  `mode: business` steps outright instead of silently running them as a chat
  step. Wired business-executor selection (`voly.decisions.
  _build_business_executor`) through `ExecutorMatcher` capability scoring
  when `capability.enabled`, replacing a hardcoded `if/else`, with fallback to
  the prior static choice when capability routing is disabled or unusable.

- `535e969` — Fix a real data gap in the A2A live graph: a role's own
  per-attempt billing fallback (`ExecutorResult.metadata["chain_timelog"]`,
  already produced by `agent_runner.py` for every executor call) was
  computed but never threaded past the `executor_runner` dict boundary in
  `voly/a2a/hybrid.py`, so `Assignment`/`graph_node()` never carried it and
  a role that had to retry on a different executor was invisible on
  `LiveAgentGraph`/`AgentAtlas` — only the flat task-level billing chain
  (`InspectorBillingChain`) showed it, and only when the fallback happened
  to also occur at the top level. Added `Assignment.chain_timelog`,
  populated it in `multiagent_roles.run_executor()`, and exposed it on
  `graph_node()`/`to_event_dict()`.

- `722ca063` — Fix a live-task flash and a deep-link reselect race in Agent Atlas: `syncLiveRuns()` now lets `refresh()` atomically swap a finished task's `_live` placeholder for the real final entry instead of filtering it out first (which briefly emptied it from the sidebar); `router.navigate()` sets state synchronously instead of waiting for the next-tick `hashchange` event, closing a gap where a live-run poll could read the previous task's id; and the deep-link reselect in `_mergeNew()`/`refresh()` now uses `.startsWith()` instead of `!==` against the full `task_id`, since `router.taskId` is always an 8-char prefix (the old comparison was always true, so it ran on every update).

- `054346d8` — Clear the remaining 61 SonarQube HIGH-impact findings across 24 files: extracted module-level constants for 34 duplicated string literals (S1192), documented `responses={...}` for 17 HTTPException status codes on FastAPI routes in web/routes/{marketplace,tasks,providers,runs}.py — tracing through helper functions to the real route-level codes (S8415), and switched 5 `logger.error` calls in except blocks to `logger.exception` for automatic traceback capture (S8572). Left `voly/environment.py:73` (S8495) as-is after review — its `tuple[str, ...]` return is intentionally variadic and no caller unpacks it, so there's no real bug. 456 relevant tests pass. Originally attempted via `voly run --executor opencode --model deepseek-v4-pro`; the model produced a text plan (no tool calls, not even after fixing the `--auto` bug in 891af9fc) instead of applying edits at this batch size, so this batch was done directly.

- `891af9fc` — Add `--auto` to the `opencode run` command built by `_build_opencode_run_cmd` (shared by OpenCodeExecutor and ZenExecutor). Without it, headless runs (no TTY) had no way to satisfy OpenCode's interactive permission prompt for file writes, so tasks silently returned a text-only plan (success=True, num_turns=1, zero files touched) instead of applying changes. Caught when a `voly run --executor opencode` task assigned to fix a SonarQube batch came back with a full text plan and no diff.

- `3f18a8e3` — Fix a mypy type error in `parse_readme_text` (dedup loop variable `m` reused a name already bound to a regex `Match` earlier in the same function), extract a `_CREDIT_CARD_LABEL` constant to remove a triplicated string literal (S1192), and extract `_enrich_provider_from_row`/`_find_legacy_id`/`_merge_model` to bring `_parse_permanent_free` and `merge_with_catalog` back under the cognitive-complexity limit (S3776, were 17 and 20 of 15 allowed). Confirmed clean via a fresh SonarQube rescan.
- `2a53b4a0` — Fix CORS middleware order (BLOCKER: was inner to CorrelationMiddleware, could miss CORS headers on responses generated outside it), drop the world-writable `/tmp/cloudflared` from the trusted binary search path (CRITICAL: local attacker could plant a binary there for `find_cloudflared()` to execute), replace deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)` in a2a/report.py and cloudflare/r2.py, remove a dead `or True` that made `voly config --show` a no-op, and two smaller SonarQube CRITICAL cleanups (regex-only-literal `re.sub`, undocumented empty method override).
- `16e8d071` — Fix `OrchestrationReport.to_markdown` returning an identical empty status string for both success and failure (both ternary branches were the same literal), and re-raise `asyncio.CancelledError` in the tasks SSE generator instead of swallowing it, per SonarQube findings on the newly connected local Sonar server.
- `6cceefa` — Show the assigned executor name (from roles[0]/current_role) instead of a placeholder dash for single-role live tasks in Agent Atlas, since RunRecord has no agent/executor/model fields until the final TaskEvent.
- `ac96e0c` — Auto-reap stale "running" task records in the web server; strip filename tokens from router keyword matching; align SkillScout's relevance gate with the shared skill-injection stopword list; fix PipelineInspector's Atlas/Report tab snapping back during live polling; detect file creation outside a git repo via a shallow dir-snapshot fallback; add `allow_provider_reroute` so AIGateway's tier-unaware health swap can't hijack A2A's own provider fallback; explicit UTF-8 across subprocess captures, config I/O, and CLI stdio (Windows cp1251 was corrupting/crashing on Cyrillic).
- `255012f` — Report multi-agent runs as partial when implementation roles fail instead of incorrectly marking them completed.
- `94d64cc` — Recover `files_touched` from the git working-tree delta when an executor fails or times out.
- `425966f` — Keep architect output plan-only, enforce the 300-line file policy, and reduce duplicated implementation context.
- `0d105a1` — Preserve downstream role errors in merged reports and raise the result cap so failures remain visible.
- `85fdff3` — Initialize git in empty target directories before hybrid execution so file tracking and verification work.
- `0e5860b` — Add premium provider fallbacks and exclude providers after runtime authentication or billing failures.
- `350ae04` — Add Cursor and DeepSeek to the file-capable executor billing fallback chain.
- `e5772cc` — Distribute chat providers and executors by role so multi-agent work does not collapse onto Cursor.
- `ebd105c` — Prevent dash-prefixed Cursor SDK callback tokens from breaking bridge startup and retry that specific launch error.
- `52ada0f` — Run downstream chat roles in degraded mode on surviving context instead of cascade-skipping the entire chain.
- `e441807` — Add live run inspection, pre-run skill suggestions, compact skill queries, and longer A2A timeout defaults.
- `2eb32c3` — Enforce a 300-line limit on executor-changed files, allowing up to 500 only with strict architect approval and rationale markers.
- `dbc5bc2` — Require CF_WORKER_SPEND_TOKEN for the Spend Worker (no CLOUDFLARE_API_TOKEN fallback) and surface auth errors in the CF Spend UI.
- `4ec0b53` — Enable plan shadow gates in voly.yaml (file line limits, git-diff and tester-command verification now active) and sync Anthropic model ids with the router.
- `d314eba` — Estimate Cursor executor token usage and cost (char-based, flagged as estimated) instead of reporting $0 for every cursor run.
- `ab8e463` — Restore MemoryStore.list_by_category, fixing the crashed `voly memory list` CLI path.
- `5e4505c` — Pass `voly run --cwd` into the pipeline context so hybrid multi-agent roles actually run as executors instead of downgrading to chat.
- `a015375` — Translate builtin agent system prompts and skill content to English.
- `aa8dd7d` — A2A resilience batch: skip runtime-excluded providers in chat fallback, mark the lead's provider unhealthy on auth errors, halt the chain on spend limit, expire provider exclusions after a TTL, require a successful implement role for `completed`, make the reviewer depend on the developer in the high-complexity branch, report honest federation statuses, capture git deltas on executor exceptions, and translate all role prompts to English.
- `7901f2d` — Wave parallelism for local multi-agent runs: independent roles share a dependency wave and issue their chat calls concurrently (`a2a.parallel_waves`, `a2a.max_parallel_roles`); executor roles stay serial and a spend limit stops scheduling further waves.
- `81dc9bc` — Fail executor roles that report success without touching any files on code-gen tasks (text summary ≠ implementation → run reports partial); enable `plan.executor_require_git_diff`; record per-role `duration_ms` in a2a telemetry.
- `eb1768d` — Relevance-gate skill injection: installed marketplace/org skills need two concrete signals (word-boundary keyword hits or project stack match) before entering prompts; lead respects an explicit empty skills choice; SkillScout suggestions must overlap task keywords.
- `6596c8a` — Surface per-role errors and durations for multi-agent tasks in the UI: RoleStrip chips in TaskHeader plus error lines under failed agent rows in PipelineInspector, so a partial run is explainable at a glance.
- `8a805b3` — Fix tester model tier (cheap→standard, uses paid providers), empty-response false positive in chat roles (ok=False when content empty regardless of gates_on), auto-add .voly/ to target project .gitignore in ensure_git_repo, and show partial multi-agent output on CLI failure instead of bare "Error: ".
- `df916a5` — Prefer .venv/bin/pytest for plan tester_command auto-fill; auto-set requires_review when ≥2 capability flags (code-gen+tests → 3 roles); add deepseek to gateway fallback.chain; tighten AGENTS.md/CLAUDE.md.
- `10b0b13` — 15s provider HTTP stall timeout with fallback; plan command_timeout 60s; allowlist .env.example for greenfield; pipeline SETUP/A2A logging and post-run checklist.
- `150c685` — Soft-fail safety when protected paths roll back but other files remain; treat files_touched as code so multi-agent does not cascade-skip chat roles; demote Anthropic to last in strong/standard provider tiers.
- `cb3a0d2` — Scope bare pytest verify to touched tests; compact prior context with files_touched; cwd executor lock + mtime-filtered git delta; deepseek in _template fallback.chain.
- `11a48e8` — Reviewer/tester get git-diff evidence from prior files_touched; dual HTTP timeouts (stall 15s + total 60s) for slow live providers.
- `c86d39b` — Role-aware skill relevance (drop generic markdown on FastAPI roles); tester hybrid executor on code-gen; architect_max_tokens 4096.
- `b356179` — Devops hybrid executor; shadow verify logs pytest argv; RTK + local trim savings on multi-agent path.
- `5d58716` — Split multiagent helpers (context/waves/chat_fallback); pre-mark VOLY_A2A_EXCLUDE_PROVIDERS; CLI A2A role files/verify summary.

- `7c40c0b` — Include voly.pxpipe in setuptools packages so pip-installed CI environments can import ClaudeCodeExecutor.
- `370a909` — Wire repository intelligence into Pipeline and forward `voly runner --repo` to AgentRunner.

- `b4dbf05` — Detect untracked-file edits via fingerprints for files_touched; non-zero exit on `voly run --json` failure; gate frontend skills off Python backend tasks; skip unhealthy providers in AIGateway after billing; isolate memory tests to local backend.

- `1b95903` — Tighten frontend A2A role signals so backend prompts with architecture design no longer pull visual_reviewer.

- `8884211` — Enable capability worker routing in A2A, filter match by kind, and honor matcher-chosen executors in hybrid runs.

- `9c02171` — Close remaining strategy gaps: model_provider seeds, health-filtered match, routing policies, and voly run --repo / intelligence.auto.

- `dcc6a6c` — Detect Windows npm executor shims and repo-local Wrangler installations instead of requiring a POSIX-style binary on PATH.

- `642ce3f` — Create a stable root task before execution, merge live RunRecords into the normal task list, and replace the separate In progress cards with one continuously updated task and Agent Atlas.
d18639e — Added an offline, read-only `voly quickstart --check` path with deterministic executor discovery, safe configuration creation, JSON output, and no capability-registry startup sync.
f54acdb — Fixed the wheel manifest so clean installs include intelligence, reuse, workflow, and capability seed packages; added a regression check for future package omissions.
fc446a9 — Declared the capability schemas namespace explicitly, removing ambiguous setuptools packaging before PyPI release.
87a8ba6 — Made quickstart executor mocks cross-platform and aligned the setuptools smoke test with the packaged workflow module.
6731956 — Removed the orphaned `agentsview` gitlink that made checkout post-job cleanup fail on every CI runner.

d775ae6 — Added six Workflow topology presets (sequential, concurrent, supervisor_workers, reviewer_loop, council, planner_generator_evaluator) as plain graph factories with hard build-time bounds; documented that reviewer_loop's exit_acceptance only gates the final unrolled round since PlanEngine has no conditional-skip primitive for a true early-exit loop.

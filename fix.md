# Fix Log

Functional fixes are recorded here after commit. Entries use the exact short
commit hash and an English description.

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

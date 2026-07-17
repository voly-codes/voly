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
- `d671637` — Enforce a 300-line limit on executor-changed files, allowing up to 500 only with strict architect approval and rationale markers.
- `759e04c` — Require CF_WORKER_SPEND_TOKEN for the Spend Worker (no CLOUDFLARE_API_TOKEN fallback) and surface auth errors in the CF Spend UI.

# Bug & Issue Checklist

Generated from a full-codebase review on 2026-07-10. Ordered by priority within each section.
Per `CLAUDE.md`'s documentation rule, update the linked doc in the same commit as the fix.

## Critical

- [x] **Billing-error text-match false positives.** `_is_billing_error`/`classify_provider_error` treat a bare substring `"402"` (`voly/ai_gateway/error_classifier.py:322`) and the bare word `"billing"` (`error_classifier.py:74`) as terminal billing signals, with no status-code correlation (executors always call this with `status_code=None`, see `voly/executor/base.py:107`). Any unrelated CLI error text that happens to contain "402" (port, PID, line number) or mentions "billing" (e.g. an FAQ link) gets misclassified as a terminal billing error, causing `AgentRunner` to skip to the next executor in the fallback chain for the wrong reason and masking real bugs.
  Update: `docs/backend/executors.md`, `docs/backend/ai-gateway.md`

- [x] **`hybrid_warning` SSE event is only half-wired.** The backend sets `start_payload["hybrid_warning"] = "hybrid_skipped_no_cwd"` on the `start` SSE event (`voly/web/routes/run.py:331`), but nothing in `ui/src` reads `hybrid_warning` or the `start` event type at all. Users get no visible indication that hybrid execution silently degraded to chat-only.
  Update: `docs/frontend/api-client.md`, `docs/backend/api.md`

- [x] **JWT access token passed as an SSE URL query parameter.** `ui/src/lib/api/client.js:152-157` (`taskStream`) appends `?access_token=...` to the SSE URL because `EventSource` can't set headers. The token ends up in server access logs, browser history, and any intermediary proxy logs.
  Update: `docs/frontend/api-client.md` (add a security note / consider a short-lived one-time stream token instead)

- [x] **Empty `onerror` handler, no polling fallback.** `ui/src/lib/stores/tasksStore.svelte.ts:92-95` has an `es.onerror` handler that only contains a comment claiming a "fallback to polling after 3 failures" — no failure counter or polling fallback is actually implemented. A flaky SSE connection leaves the UI silently stale.
  Update: `docs/frontend/api-client.md`

- [x] **Unbounded upward config/`.env` discovery.** `_find_config_path` and `_load_dotenv` (`voly/config/_loader.py:14-60`) walk up the directory tree with no depth bound, all the way to filesystem root. Since VOLY runs against arbitrary external projects via `--cwd`, an unrelated `voly.yaml`/`.env` in any ancestor directory gets silently loaded — including credentials from an unrelated project.
  Update: `docs/backend/config.md`

## Medium

- [x] **Single global thread pool for all SSE `/api/run` requests, no disconnect handling.** `voly/web/routes/run.py:19` — `ThreadPoolExecutor(max_workers=4)` is shared by every client. A 5th concurrent request queues invisibly (client only sees the initial `start` event, then a silent gap that can trip proxy/browser idle timeouts). There's no `request.is_disconnected()` check, so a client that disconnects doesn't free its worker slot.
  Update: `docs/backend/api.md`

- [x] **DSPy example filename collision.** `_dspy_store_example` (`voly/runner/agent_runner.py:207-209`) names dataset files `f"{int(time.time())}.jsonl"` opened with mode `"w"`. Two examples produced within the same wall-clock second (plausible with the 4-worker pool above) silently overwrite each other.
  Update: `docs/backend/dspy.md`

- [x] **Asymmetric path-escape guard in the patch executor.** `voly/executor/patch.py` protects the write path (`_write`, ~line 168) against `../` escapes but not the diff-apply read path (`_apply_diff_section`, ~line 130-136) — a model-produced diff header with `../` can read a file outside the project sandbox before the (safe) write is rejected.
  Update: `docs/backend/executors.md`

- [ ] **Redundant executor rebuild in the fallback loop.** `voly/runner/agent_runner.py:404` and `:427` call `_build_executor(fallback_name)` twice per fallback iteration — once to check `is_available()`, then again right before `.run()` — re-importing the module and re-reading credential env vars each time. Not incorrect, just wasteful on the hot billing-fallback path.

## Low / Cleanup

- [ ] **Dead code violates Invariant #1.** `Pipeline._get_provider()` (`voly/pipeline/core.py:388-393`) builds a raw provider client via `create_provider(...)`, bypassing `AIGateway.chat()` entirely (no cache/DLP/spend-limit/telemetry). No current callers — but it sits directly on top of the project's core invariant and is a landmine if wired up later without review. Remove it or gate it so it can't be called unreviewed.

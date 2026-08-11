# MCP facade — VOLY as an MCP server

`voly/mcp/` exposes the orchestrator to any MCP host (Cloudflare OS, Claude
Desktop, an IDE) as nine tools. It is the opposite direction from
`voly/tools/mcp.py`, which is the *client* manager for MCP servers VOLY's own
agents consume.

```bash
pip install -e ".[mcp]"
voly mcp serve --port 7799          # or: python -m voly.mcp
# → http://127.0.0.1:7799/mcp
```

Transport is streamable HTTP (POST JSON-RPC, `Accept: application/json,
text/event-stream`, `Mcp-Session-Id` echoed). `--transport stdio` for hosts that
spawn the server as a subprocess.

## Tools

| Tool | Backing service call | Mode |
|---|---|---|
| `voly_list_runs` | `service.list_runs` | read |
| `voly_get_run` | `service.get_run` | read |
| `voly_list_tasks` | `service.list_tasks` | read |
| `voly_get_task` | `service.get_task` | read |
| `voly_get_stats` | `service.task_stats` | read |
| `voly_health` | `routes.cf.providers_health` + executor list | read |
| `voly_start_run` | `service.start_run_background` | **action** |
| `voly_cancel_run` | `service.cancel_run` | **action** |
| `voly_submit_feedback` | `EvidenceStore.add_human_feedback` | **action** |

Deliberately **not** exposed: provider key CRUD (`/api/providers/*`), skill
installation, `/api/repo/analyze`, `/api/tech/preflight`. Keys in particular
stay on VOLY's side of the boundary — the host has its own model credentials and
neither side hands the other raw tokens.

## The annotation contract

Annotations are load-bearing, not documentation. A host classifies each tool
from them alone; this is Cloudflare OS's rule
(`packages/mcp-shared/src/tools.ts`):

```
mode           = (readOnlyHint === true) ? "read" : "action"
autoApprovable = !readOnly && trust === "vetted"
                 && destructiveHint === false && idempotentHint === true
```

A `read` runs immediately and is recorded as an observation. An `action` goes to
the approval queue — asynchronously, so the agent keeps working against a
simulated result and the human approves later, in bulk.

Every check there is an identity test, so an **unannotated tool is treated as an
action that can never be auto-approved**. Adding a tool without annotations is a
policy decision, not an oversight.

`trust: "vetted"` requires an administrator-configured endpoint (an MCP portal
with `MCP_PORTAL_TRUST_ANNOTATIONS=true`). When a user pastes the URL in
themselves the tier is `byo` and no write is ever auto-approved — which is what
we want for a tool that spends money.

`voly_start_run` is annotated `destructiveHint: true, idempotentHint: false`, so
it always prompts even on a vetted endpoint. `tests/test_mcp_facade.py` asserts
this; it is not an accident to be tidied up later.

## Why `voly_start_run` does not stream

`POST /api/run` streams progress over SSE. No `tools/call` can hold that open —
one call gets one response, and a run outlives it. So the facade converts the
execution model:

```
voly_start_run  → dispatch, open the RunRecord, return task_id immediately
voly_get_run    → poll the heartbeat (RunTracker writes every ~10s)
voly_get_task   → read the result once the TaskEvent lands
```

This reuses the run path rather than forking it: `prepare_run()`, `launch_run()`
and `finish_run()` in `voly/web/routes/run.py` are shared by the SSE route and
`service.start_run_background()`, so both make the same smart-dispatch decision
(pipeline → multi-agent or → claude-code) and register the same kind of run.

Background runs are held in `service._BACKGROUND_RUNS`; without a strong
reference the event loop could collect a run mid-flight.

## The service layer

`voly/web/service.py` holds everything the HTTP routes and the MCP tools share.
Nothing at module level imports FastAPI or the MCP SDK, and the events directory
is passed in explicitly — the MCP server has no request object to carry it.

Route handlers in `routes/tasks.py` and `routes/runs.py` are now thin delegates.
Add a transport by writing signatures, not a second copy of the logic.

`VOLY_EVENTS_DIR` overrides directory resolution (default: `.voly/events` in cwd,
then `~/.voly/events`).

## Connecting Cloudflare OS

1. Run CF OS locally (`pnpm run-local`, → `localhost:8787`) or use a deployment.
2. Start `voly mcp serve`. The endpoint must be reachable from the Worker — for
   a hosted CF OS, expose it with `voly tunnel` or `cloudflared` rather than
   binding `0.0.0.0` on a laptop.
3. In CF OS, connect the **MCP** connector and paste the `/mcp` URL. The
   gatekeeper probes unauthenticated first; a 401 is how a server asks for
   OAuth, so an unauthenticated server connects as a public one.
4. Scope a grant to specific tools with a URL fragment:
   `http://host:7799/mcp#tool=voly_list_runs&tool=voly_get_run` — everything else
   is refused.

One VOLY instance, one `.voly` directory: runs started from the MCP facade show
up in `voly ui` and the CLI, and vice versa.

"""MCP facade over the VOLY orchestrator.

Nine tools over the same data the HTTP API serves (`voly.web.service`), so the
two transports can never disagree about a run.

**Annotations here are load-bearing, not documentation.** Cloudflare OS decides
what an agent may do with a tool from its annotations alone
(`packages/mcp-shared/src/tools.ts`):

    mode = (annotations.readOnlyHint === true) ? "read" : "action"

A `read` runs immediately and is recorded as an observation; anything else is
queued for human approval. Every test there is `=== true`/`=== false` rather
than a truthiness check, so an *unannotated* tool is treated as an action that
can never be auto-approved. Adding a tool below without annotations is therefore
a policy decision, not an oversight — annotate it.

Auto-approval additionally requires the deployment to have vouched for this
endpoint (`trust: "vetted"`, i.e. an administrator-configured MCP portal). When
a user pastes this server's URL in themselves, no write is ever auto-approved —
which is the behaviour we want for a tool that spends money.

Run it:

    voly mcp serve --port 7799      # or: python -m voly.mcp

and point the host at http://<host>:<port>/mcp.
"""

from __future__ import annotations

import logging
import os
import pathlib
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from voly.web import service

_log = logging.getLogger("voly.mcp")

DEFAULT_PORT = 7799

# The SDK takes snake_case and serializes camelCase (`readOnlyHint`), which is
# the spelling the Cloudflare OS classifier reads.
#
# Read-only: resolves immediately in the host, recorded as an observation.
_READ = ToolAnnotations(read_only_hint=True)

# Spends money, writes files, cannot be replayed safely.
_WRITE_DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False
)

# Changes state, but re-running it lands in the same place and destroys nothing.
_WRITE_SAFE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True
)


@dataclass
class _Runtime:
    """Where this server reads runs from, resolved once at first use."""

    ev_dir: pathlib.Path
    config: Any


_runtime: _Runtime | None = None


def _rt() -> _Runtime:
    global _runtime
    if _runtime is None:
        override = os.environ.get("VOLY_EVENTS_DIR", "").strip()
        ev_dir = pathlib.Path(override) if override else service.resolve_events_dir()
        try:
            from voly.config import load_config

            config = load_config()
        except Exception as exc:  # noqa: BLE001 — a missing voly.yaml must not stop the server
            _log.warning("[MCP] no config loaded (%s); falling back to defaults", exc)
            config = None
        _runtime = _Runtime(ev_dir=ev_dir, config=config)
        _log.info("[MCP] events dir: %s", ev_dir)
    return _runtime


def _executors_hint() -> str:
    try:
        from voly.runner.executor_factory import EXECUTOR_NAMES

        return ", ".join(sorted(EXECUTOR_NAMES))
    except Exception:  # noqa: BLE001
        return "claude-code, cursor, opencode, zen, wrangler, deepseek"


def build_server() -> MCPServer:
    """Construct the MCP server with all nine tools registered.

    Bind address and port belong to the transport, so they are passed to
    `run()` / `streamable_http_app()`, not here.
    """
    mcp = MCPServer(
        "voly",
        instructions=(
            "VOLY orchestrates AI coding agents. Reads (list/get/stats/health) are "
            "free — use them to see what is already running before starting more. "
            "voly_start_run spends real money and writes files; it returns a "
            "task_id immediately and the run continues in the background."
        ),
    )

    # ── Reads ────────────────────────────────────────────────────────────────

    @mcp.tool(annotations=_READ)
    def voly_list_runs(active: bool = True, limit: int = 20) -> dict[str, Any]:
        """List VOLY runs and their current state.

        Cheap and safe — call it freely, and call it first: it shows whether the
        work you are about to request is already in flight. Runs report progress
        by heartbeat roughly every 10 seconds while an executor is working.

        active=True (default) shows only runs still executing. Finished runs are
        better read through voly_list_tasks, which carries cost and results.
        """
        return service.list_runs(_rt().ev_dir, active=active, limit=limit)

    @mcp.tool(annotations=_READ)
    def voly_get_run(task_id: str) -> dict[str, Any]:
        """Current state of one run: status, elapsed time, roles, agent graph.

        This is how you follow a run started with voly_start_run. Poll it every
        20-30 seconds; a run doing real work takes minutes, not seconds. Once
        status is no longer "running", read the outcome with voly_get_task.
        """
        rec = service.get_run(_rt().ev_dir, task_id)
        if rec is None:
            return {"error": "not_found", "task_id": task_id,
                    "message": "No run record. It may have been reaped, or the id is wrong."}
        return rec

    @mcp.tool(annotations=_READ)
    def voly_list_tasks(limit: int = 20, agent: str = "", status: str = "") -> dict[str, Any]:
        """List finished tasks, newest first, with cost, tokens and status.

        Filter by agent name or by status ("success", "error", ...). This reads
        completed work only; for what is running right now use voly_list_runs.
        """
        return {"tasks": service.list_tasks(
            _rt().ev_dir, limit=limit, agent=agent, status=status
        )}

    @mcp.tool(annotations=_READ)
    def voly_get_task(task_id: str) -> dict[str, Any]:
        """Full result of one finished task: output, cost, tokens, duration, model.

        A task appears here only after its run completes. If this returns
        not_found for a run you just started, it is still working — check
        voly_get_run instead.
        """
        task = service.get_task(_rt().ev_dir, task_id)
        if task is None:
            return {"error": "not_found", "task_id": task_id,
                    "message": "No finished task with this id. Still running? Try voly_get_run."}
        return task

    @mcp.tool(annotations=_READ)
    def voly_get_stats() -> dict[str, Any]:
        """Totals across every finished task: spend, tokens, tokens saved, durations.

        Local telemetry, so it covers this VOLY instance only. Useful for
        answering "what has this cost so far" before starting more work.
        """
        return service.task_stats(_rt().ev_dir)

    @mcp.tool(annotations=_READ)
    def voly_health() -> dict[str, Any]:
        """Which LLM providers and executors are usable right now.

        Worth checking before a long run: a provider with no key configured will
        fail the run at the first model call. Reports provider health plus the
        events directory this server is reading.
        """
        rt = _rt()
        # providers_health() takes no request object, so calling the route
        # function directly keeps one definition of "healthy" for both surfaces.
        from voly.web.routes.cf import providers_health

        try:
            health = providers_health()
        except Exception as exc:  # noqa: BLE001
            health = {"error": str(exc), "providers": {}, "healthy": []}
        return {
            **health,
            "executors": _executors_hint().split(", "),
            "events_dir": str(rt.ev_dir),
            "config_loaded": rt.config is not None,
        }

    # ── Actions (queued for approval by the host) ────────────────────────────

    @mcp.tool(
        annotations=_WRITE_DESTRUCTIVE,
        description=(
            "Start a task on VOLY's coding agents. EXPENSIVE AND IRREVERSIBLE: it "
            "spends LLM credits, runs for minutes, and writes files into `cwd`.\n\n"
            "Returns a task_id immediately — it does not wait for the run. Follow "
            "it with voly_get_run, then read the outcome with voly_get_task.\n\n"
            "Arguments:\n"
            "  task    — what to do, in plain language. Be specific; this is the "
            "whole brief the agent gets.\n"
            "  cwd     — absolute path of the target project. Leave empty to use "
            "the server's configured default. A wrong path means files written in "
            "the wrong repository.\n"
            f"  executor — which agent runs it. Empty or 'pipeline' lets VOLY route "
            f"(recommended). Explicit choices: {_executors_hint()}.\n"
            "  dry_run — run for real, then roll back every file change and return "
            "the diff. Use this to preview an unfamiliar or risky task; it still "
            "costs tokens and time.\n"
            "  workflow — 'review-until-clean' runs a bounded developer/reviewer "
            "loop instead of a single pass. Not compatible with dry_run."
        ),
    )
    async def voly_start_run(
        task: str,
        cwd: str = "",
        executor: str = "pipeline",
        dry_run: bool = False,
        workflow: str = "",
        timeout: int = 300,
    ) -> dict[str, Any]:
        if not task.strip():
            return {"error": "invalid_request", "message": "task must not be empty"}
        if workflow and workflow != "review-until-clean":
            return {"error": "invalid_request",
                    "message": "workflow must be empty or 'review-until-clean'"}
        if workflow and dry_run:
            # Rolling back every developer lap would leave the reviewer nothing
            # to inspect, so the two options are mutually exclusive by design.
            return {"error": "invalid_request",
                    "message": "dry_run is not supported with the review-until-clean workflow"}

        rt = _rt()
        started = await service.start_run_background(
            task=task,
            ev_dir=rt.ev_dir,
            config=rt.config,
            executor=executor or "pipeline",
            cwd=cwd,
            dry_run=dry_run,
            workflow=workflow,
            timeout=timeout,
        )
        return {
            **started,
            "next_step": "Poll voly_get_run(task_id) until status is not 'running'.",
        }

    @mcp.tool(annotations=_WRITE_SAFE)
    def voly_cancel_run(task_id: str) -> dict[str, Any]:
        """Ask a running task to stop at its next safe point.

        Cooperative, not immediate: an executor already inside a subprocess call
        finishes that call first. Safe to call more than once.
        """
        if not service.cancel_run(_rt().ev_dir, task_id):
            return {"error": "not_cancellable", "task_id": task_id,
                    "message": "The run is missing or already finished."}
        return {"task_id": task_id, "cancel_requested": True,
                "interrupts_active_subprocess": False}

    @mcp.tool(annotations=_WRITE_SAFE)
    def voly_submit_feedback(task_id: str, kind: str, comment: str = "") -> dict[str, Any]:
        """Record what a human actually did with a task's output.

        This is the training signal VOLY learns routing from, so it is worth
        sending. kind is one of: accepted, edited, major_rewrite, reverted,
        pr_rejected, manual_fix.
        """
        valid = {"accepted", "edited", "major_rewrite", "reverted", "pr_rejected", "manual_fix"}
        if kind not in valid:
            return {"error": "invalid_request",
                    "message": f"kind must be one of: {', '.join(sorted(valid))}"}
        safe = service.safe_task_id(task_id)
        if safe is None:
            return {"error": "invalid_request", "message": "malformed task_id"}

        from voly.evidence.store import EvidenceStore

        rt = _rt()
        store_dir = rt.config.evidence.store_dir if rt.config else ".voly/evidence"
        try:
            record = EvidenceStore(store_dir).add_human_feedback(
                safe, kind, source="mcp", comment=comment
            )
        except FileNotFoundError:
            return {"error": "not_found", "task_id": safe,
                    "message": "No evidence record for this task."}
        return {"task_id": record.task_id, "kind": kind, "recorded": True}

    return mcp


def main() -> None:
    """Entry point for `voly mcp` and `python -m voly.mcp`."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the VOLY MCP server.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1; use 0.0.0.0 to expose)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port (default {DEFAULT_PORT})")
    parser.add_argument("--transport", default="streamable-http",
                        choices=["streamable-http", "sse", "stdio"],
                        help="MCP transport (default streamable-http)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    serve(build_server(), transport=args.transport, host=args.host, port=args.port)


def serve(
    server: MCPServer,
    transport: str = "streamable-http",
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
) -> None:
    """Run `server` on `transport`. stdio takes no address, HTTP transports do."""
    if transport == "stdio":
        server.run(transport="stdio")
        return
    _log.info("[MCP] VOLY MCP server on http://%s:%d/mcp", host, port)
    server.run(transport=transport, host=host, port=port)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()

"""The MCP facade's contract with its host.

Cloudflare OS (and any other MCP host) decides what an agent may do with a tool
from the annotations on the wire, so these tests read the serialized
`tools/list` payload rather than Python attributes — the camelCase JSON is what
`packages/mcp-shared/src/tools.ts` actually parses.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp", reason="requires the mcp extra: pip install -e '.[mcp]'")

from voly.mcp.server import build_server  # noqa: E402

EXPECTED_READ = {
    "voly_list_runs",
    "voly_get_run",
    "voly_list_tasks",
    "voly_get_task",
    "voly_get_stats",
    "voly_health",
}
EXPECTED_ACTION = {"voly_start_run", "voly_cancel_run", "voly_submit_feedback"}


def _classify(annotations: dict) -> tuple[str, bool]:
    """Port of classifyTool() in packages/mcp-shared/src/tools.ts.

    Every check is an identity test there, not a truthiness test, so a missing
    annotation comes out as an action that can never be auto-approved.
    """
    read_only = annotations.get("readOnlyHint") is True
    auto_if_vetted = (
        not read_only
        and annotations.get("destructiveHint") is False
        and annotations.get("idempotentHint") is True
    )
    return ("read" if read_only else "action"), auto_if_vetted


async def _wire_tools() -> dict[str, dict]:
    """Tools as a host receives them, keyed by name."""
    tools = await build_server().list_tools()
    return {t.name: t.model_dump(by_alias=True, exclude_none=True) for t in tools}


async def test_read_and_action_split_is_stable():
    """A tool changing sides changes whether a human is asked before it runs."""
    wire = await _wire_tools()
    reads = {n for n, t in wire.items() if _classify(t.get("annotations") or {})[0] == "read"}
    actions = set(wire) - reads
    assert reads == EXPECTED_READ
    assert actions == EXPECTED_ACTION


async def test_every_tool_is_annotated_and_described():
    """An unannotated tool is silently treated as an un-auto-approvable write, and
    the description is the only thing the calling agent reads before choosing."""
    for name, tool in (await _wire_tools()).items():
        assert tool.get("annotations"), f"{name} would reach the host unannotated"
        assert tool.get("description"), f"{name} has no description for the agent"


async def test_starting_a_run_always_prompts():
    """voly_start_run spends money and writes files, so no deployment — however
    trusted — may let it through without a human."""
    wire = await _wire_tools()
    assert _classify(wire["voly_start_run"]["annotations"]) == ("action", False)


async def test_cheap_writes_may_be_auto_approved_on_a_vetted_endpoint():
    """Cancelling and recording feedback destroy nothing and are idempotent."""
    wire = await _wire_tools()
    for name in ("voly_cancel_run", "voly_submit_feedback"):
        assert _classify(wire[name]["annotations"]) == ("action", True), name


async def test_start_run_rejects_an_empty_task(tmp_path, monkeypatch):
    """The guard has to fire before dispatch — an empty brief would otherwise
    start a real, billable run."""
    monkeypatch.setenv("VOLY_EVENTS_DIR", str(tmp_path / "events"))
    import voly.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "_runtime", None)
    server = mcp_server.build_server()
    result = await server.call_tool("voly_start_run", {"task": "   "})
    payload = json.loads(result[0].text if isinstance(result, list) else result.content[0].text)
    assert payload["error"] == "invalid_request"


async def test_dry_run_is_refused_with_the_review_workflow(tmp_path, monkeypatch):
    """Rolling back every developer lap leaves the reviewer nothing to inspect."""
    monkeypatch.setenv("VOLY_EVENTS_DIR", str(tmp_path / "events"))
    import voly.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "_runtime", None)
    server = mcp_server.build_server()
    result = await server.call_tool(
        "voly_start_run",
        {"task": "fix the login bug", "workflow": "review-until-clean", "dry_run": True},
    )
    payload = json.loads(result[0].text if isinstance(result, list) else result.content[0].text)
    assert payload["error"] == "invalid_request"
    assert "dry_run" in payload["message"]


async def test_path_like_task_ids_are_refused(tmp_path, monkeypatch):
    """Reads take an id straight from a model, so traversal must not resolve."""
    monkeypatch.setenv("VOLY_EVENTS_DIR", str(tmp_path / "events"))
    import voly.mcp.server as mcp_server

    monkeypatch.setattr(mcp_server, "_runtime", None)
    server = mcp_server.build_server()
    result = await server.call_tool("voly_get_task", {"task_id": "../../secrets"})
    payload = json.loads(result[0].text if isinstance(result, list) else result.content[0].text)
    assert payload["error"] == "not_found"

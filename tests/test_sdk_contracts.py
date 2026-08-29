"""PR0 (docs/proposals/agent-workflow-sdk.md): frozen SDK contracts.

These are frozen snapshots, not ordinary unit tests. If one fails because a
field/import was added, removed or renamed, that is not a reason to update
the snapshot silently: update docs/backend/sdk.md and the proposal first,
then the snapshot — mirroring the convention in test_protocol_contracts.py.
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields
from pathlib import Path

import voly.sdk as sdk_pkg
from voly import (
    Agent,
    AgentError,
    AgentResult,
    NodeResult,
    Workflow,
    WorkflowError,
    WorkflowNode,
    WorkflowResult,
)

_SDK_DIR = Path(sdk_pkg.__file__).resolve().parent

# Banned at import time or call time anywhere under voly/sdk/: a provider
# client constructed directly would bypass AIGateway's DLP/spend/cache/
# fallback policy — the whole point of the facade.
_BANNED_PROVIDER_IMPORTS = frozenset({
    "anthropic", "openai", "google.generativeai", "google.genai",
    "cohere", "mistralai", "httpx", "requests",
})


def _imported_module_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_sdk_source_never_imports_a_provider_client_directly() -> None:
    for path in _SDK_DIR.rglob("*.py"):
        roots = _imported_module_roots(path)
        offending = roots & _BANNED_PROVIDER_IMPORTS
        assert not offending, f"{path} imports provider/HTTP client(s) directly: {offending}"


def test_public_sdk_import_surface() -> None:
    """`from voly import Agent, AgentResult, AgentError` is the frozen Phase 1
    surface, extended in Phase 2 with Workflow/WorkflowNode/WorkflowResult/
    NodeResult. Adding names is fine; removing/renaming one is a breaking
    change that needs the proposal's schema-version policy applied first."""
    assert Agent is sdk_pkg.Agent
    assert AgentResult is sdk_pkg.AgentResult
    assert AgentError is sdk_pkg.AgentError
    assert Workflow is sdk_pkg.Workflow
    assert WorkflowNode is sdk_pkg.WorkflowNode
    assert WorkflowResult is sdk_pkg.WorkflowResult
    assert WorkflowError is sdk_pkg.WorkflowError
    assert NodeResult is sdk_pkg.NodeResult


# Frozen constructor contract — see docs/proposals/agent-workflow-sdk.md
# "Proposed public contracts" > Agent.
_AGENT_CONSTRUCTOR_PARAMS = [
    "name", "instructions", "model", "provider", "tier",
    "tools", "output_schema", "mode", "executor",
]


def test_agent_constructor_contract_is_frozen() -> None:
    sig = inspect.signature(Agent.__init__)
    params = list(sig.parameters)[1:]  # drop self
    for name in _AGENT_CONSTRUCTOR_PARAMS:
        assert name in params, f"Agent.__init__ dropped documented param {name!r}"
    assert params[: len(_AGENT_CONSTRUCTOR_PARAMS)] == _AGENT_CONSTRUCTOR_PARAMS, (
        "Agent.__init__ positional param order changed — this breaks positional "
        "callers of the documented contract"
    )


# Frozen AgentResult field set — see "Result contract" / Agent.run() in the
# proposal ("content, success, provider/model/executor attribution, tokens,
# cost, duration, files touched and evidence/task identifiers").
_AGENT_RESULT_FIELDS = {
    "content", "success", "error", "provider", "model", "executor",
    "input_tokens", "output_tokens", "cost_usd", "duration_ms",
    "files_touched", "task_id", "evidence_id", "raw",
}


def test_agent_result_field_contract_is_frozen() -> None:
    actual = {f.name for f in fields(AgentResult)}
    assert actual == _AGENT_RESULT_FIELDS, (
        f"AgentResult fields changed: added={actual - _AGENT_RESULT_FIELDS} "
        f"removed={_AGENT_RESULT_FIELDS - actual}"
    )


def test_agent_has_sync_and_async_entry_points() -> None:
    assert callable(Agent.run)
    assert inspect.iscoroutinefunction(Agent.arun)


# Frozen Workflow.add() contract — see docs/proposals/agent-workflow-sdk.md
# "Proposed public contracts" > Workflow. node_id is positional; the rest are
# keyword-only.
_WORKFLOW_ADD_PARAMS = {
    "node_id", "agent", "task", "depends_on", "approval", "acceptance", "timeout_seconds",
}


def test_workflow_add_contract_is_frozen() -> None:
    sig = inspect.signature(Workflow.add)
    params = list(sig.parameters)[1:]  # drop self
    assert params[0] == "node_id", "Workflow.add()'s first param must stay positional node_id"
    assert set(params) == _WORKFLOW_ADD_PARAMS, (
        f"Workflow.add() params changed: added={set(params) - _WORKFLOW_ADD_PARAMS} "
        f"removed={_WORKFLOW_ADD_PARAMS - set(params)}"
    )


# Frozen WorkflowResult field set — "Result contract" in the proposal: "the
# final Plan, ordered node results, aggregate cost, duration, status,
# partial/failure details and evidence IDs."
_WORKFLOW_RESULT_FIELDS = {
    "plan", "success", "status", "node_results", "cost_usd", "duration_ms", "error",
}
_NODE_RESULT_FIELDS = {
    "node_id", "status", "success", "output", "error", "cost_usd", "duration_ms", "files_touched",
}


def test_workflow_result_field_contract_is_frozen() -> None:
    actual = {f.name for f in fields(WorkflowResult)}
    assert actual == _WORKFLOW_RESULT_FIELDS, (
        f"WorkflowResult fields changed: added={actual - _WORKFLOW_RESULT_FIELDS} "
        f"removed={_WORKFLOW_RESULT_FIELDS - actual}"
    )


def test_node_result_field_contract_is_frozen() -> None:
    actual = {f.name for f in fields(NodeResult)}
    assert actual == _NODE_RESULT_FIELDS, (
        f"NodeResult fields changed: added={actual - _NODE_RESULT_FIELDS} "
        f"removed={_NODE_RESULT_FIELDS - actual}"
    )


def test_workflow_has_sync_and_async_entry_points() -> None:
    assert callable(Workflow.run)
    assert callable(Workflow.compile)
    assert inspect.iscoroutinefunction(Workflow.arun)


def test_workflow_never_reports_success_when_a_required_node_is_pending_or_failed() -> None:
    """Guards the proposal's explicit result-contract invariant at the type
    level: WorkflowResult.success must be a plain bool derived from Plan
    status, not something a caller could spoof independent of node outcomes.
    This is enforced functionally in test_sdk_workflow.py; here we only
    confirm the field exists with the right type so that contract can't
    silently regress to e.g. an Optional or a str."""
    assert fields(WorkflowResult)[1].name == "success"
    assert fields(WorkflowResult)[1].type in ("bool", bool)

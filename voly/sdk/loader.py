"""Load a Workflow definition from a YAML/JSON file (Phase 5 of
docs/proposals/agent-workflow-sdk.md).

Distinct from ``voly.plan.loader.load_plan_file``: that loads an
already-compiled ``Plan``/``PlanStep`` document (low-level, ``voly plan
run``). This loads a higher-level, ``Agent``-based ``Workflow`` definition —
the same shape ``Workflow.add()`` takes from Python — and builds it through
the ordinary ``Workflow`` builder, so every existing guarantee (``PlanEngine``
validation, ``AcceptanceCheck`` parsing, no second runtime) applies
unchanged. This module never constructs a ``Plan``/``PlanStep`` directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voly.plan.types import AcceptanceCheck
from voly.sdk.agent import Agent
from voly.sdk.workflow import Workflow, WorkflowError


def load_workflow_dict(
    data: dict[str, Any], *, config: Any = None
) -> tuple[Workflow, str, str | None]:
    """Build a ``Workflow`` from a decoded dict.

    Returns ``(workflow, task, cwd)`` — the document's own defaults for
    ``run()``'s ``task``/``cwd``; a caller (CLI/API) may still override
    either at run time.
    """
    if not isinstance(data, dict):
        raise WorkflowError("workflow document must be a mapping")
    name = str(data.get("name") or "workflow")
    task = str(data.get("task") or "")
    cwd_raw = data.get("cwd")
    cwd = str(cwd_raw) if cwd_raw else None
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise WorkflowError("workflow document requires a non-empty 'nodes' list")

    workflow = Workflow(name, config=config)
    for raw in nodes:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise WorkflowError(f"invalid node entry: {raw!r}")
        agent_data = raw.get("agent")
        if not isinstance(agent_data, dict) or not agent_data.get("name"):
            raise WorkflowError(
                f"node {raw['id']!r} requires an 'agent' mapping with a 'name'"
            )
        agent = Agent(
            name=str(agent_data["name"]),
            instructions=str(agent_data.get("instructions") or ""),
            model=agent_data.get("model") or None,
            provider=agent_data.get("provider") or None,
            tier=agent_data.get("tier") or None,
            mode=str(agent_data.get("mode") or "chat"),
            executor=agent_data.get("executor") or None,
            config=config,
        )
        acceptance = [AcceptanceCheck.from_dict(a) for a in (raw.get("acceptance") or [])]
        workflow.add(
            str(raw["id"]),
            agent=agent,
            task=str(raw.get("task") or ""),
            depends_on=[str(d) for d in (raw.get("depends_on") or [])],
            approval=bool(raw.get("approval", False)),
            acceptance=acceptance,
            timeout_seconds=raw.get("timeout_seconds"),
        )
    return workflow, task, cwd


def load_workflow_file(
    path: str | Path, *, config: Any = None
) -> tuple[Workflow, str, str | None]:
    """Load a Workflow definition from ``.yaml``/``.yml``/``.json``."""
    p = Path(path)
    if not p.is_file():
        raise WorkflowError(f"workflow file not found: {p}")
    text = p.read_text(encoding="utf-8")
    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise WorkflowError("PyYAML required to load YAML workflows") from exc
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import yaml

            data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise WorkflowError(f"workflow file root must be a mapping: {p}")
    return load_workflow_dict(data, config=config)

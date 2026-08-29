"""Phase 5 (docs/proposals/agent-workflow-sdk.md): Workflow YAML/JSON loader.

load_workflow_file/load_workflow_dict build an ordinary Workflow via the
public builder API (Workflow.add()) — never a Plan/PlanStep directly — so a
loaded document gets every existing guarantee (PlanEngine validation,
dependency-output handoff, resume/cancel) for free.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from voly.config import VOLYConfig
from voly.sdk.loader import load_workflow_dict, load_workflow_file
from voly.sdk.workflow import Workflow, WorkflowError


def _config(tmp_path) -> VOLYConfig:
    config = VOLYConfig()
    config.telemetry.enabled = False
    config.plan.store_dir = str(tmp_path / "plans")
    return config


_DOC = {
    "name": "research-review",
    "task": "Compare two markets",
    "nodes": [
        {"id": "research", "agent": {"name": "researcher", "instructions": "Find facts"}},
        {
            "id": "review",
            "agent": {"name": "reviewer"},
            "depends_on": ["research"],
        },
    ],
}


def test_load_workflow_dict_builds_a_workflow(tmp_path) -> None:
    workflow, task, cwd = load_workflow_dict(_DOC, config=_config(tmp_path))
    assert isinstance(workflow, Workflow)
    assert workflow.name == "research-review"
    assert task == "Compare two markets"
    assert cwd is None

    plan = workflow.compile(task)
    assert [s.id for s in plan.steps] == ["research", "review"]
    assert plan.get_step("review").depends_on == ["research"]
    assert plan.get_step("research").role == "researcher"


def test_load_workflow_dict_rejects_missing_nodes() -> None:
    with pytest.raises(WorkflowError, match="nodes"):
        load_workflow_dict({"name": "x"})


def test_load_workflow_dict_rejects_node_without_agent() -> None:
    with pytest.raises(WorkflowError, match="agent"):
        load_workflow_dict({"name": "x", "nodes": [{"id": "a"}]})


def test_load_workflow_file_json(tmp_path) -> None:
    path = tmp_path / "wf.json"
    path.write_text(json.dumps(_DOC), encoding="utf-8")
    workflow, task, _cwd = load_workflow_file(path, config=_config(tmp_path))
    assert workflow.name == "research-review"
    assert task == "Compare two markets"


def test_load_workflow_file_yaml(tmp_path) -> None:
    yaml = pytest.importorskip("yaml")
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump(_DOC), encoding="utf-8")
    workflow, _task, _cwd = load_workflow_file(path, config=_config(tmp_path))
    assert workflow.name == "research-review"


def test_load_workflow_file_missing_raises() -> None:
    with pytest.raises(WorkflowError, match="not found"):
        load_workflow_file("/no/such/file.json")


def test_loaded_workflow_runs_end_to_end(tmp_path) -> None:
    config = _config(tmp_path)
    workflow, task, _cwd = load_workflow_dict(_DOC, config=config)

    def chat(self, **kwargs):
        return {"content": f"ok:{kwargs.get('agent')}", "model": "x", "usage": {}}

    with patch("voly.ai_gateway.gateway.AIGateway.chat", chat):
        result = workflow.run(task)

    assert result.success is True
    assert [n.node_id for n in result.node_results] == ["research", "review"]


def test_load_workflow_dict_carries_approval_and_acceptance(tmp_path) -> None:
    doc = {
        "name": "gated",
        "nodes": [
            {
                "id": "decide",
                "agent": {"name": "manager"},
                "approval": True,
            },
        ],
    }
    workflow, _task, _cwd = load_workflow_dict(doc, config=_config(tmp_path))
    plan = workflow.compile("task")
    types = [a.type for a in plan.get_step("decide").acceptance]
    assert "human_review" in types

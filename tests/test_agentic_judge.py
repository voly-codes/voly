from __future__ import annotations

import json

import pytest

from voly.a2a.agentic_judge import AgenticJudgeAgent, ReadOnlyJudgeWorkspace
from voly.a2a.environments import AgentRequest


def test_read_only_workspace_confines_paths(tmp_path) -> None:
    (tmp_path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    workspace = ReadOnlyJudgeWorkspace(tmp_path)

    assert "app.py" in workspace.list_files()
    assert workspace.read_file("app.py") == "answer = 42\n"
    assert "app.py:1" in workspace.search_text("answer")
    with pytest.raises(ValueError, match="escapes"):
        workspace.read_file("../secret.txt")
    with pytest.raises(ValueError, match="not read-only"):
        workspace.call("write_file", {"path": "x", "content": "x"})


@pytest.mark.asyncio
async def test_agentic_judge_uses_tool_then_returns_role_metrics(tmp_path) -> None:
    (tmp_path / "app.py").write_text("answer = 42\n", encoding="utf-8")
    responses = [
        {"content": "", "tool_calls": [{"id": "1", "name": "read_file", "arguments": {"path": "app.py"}}]},
        {
            "content": json.dumps({
                "verdict": "pass",
                "summary": "Implementation matches the criterion.",
                "metrics": {
                    "architecture_usefulness": 0.8,
                    "implementation_correctness": 1.0,
                    "test_coverage": 0.6,
                    "reviewer_precision": 0.9,
                    "cost_adjusted_contribution": 0.7,
                },
            }),
            "usage": {"input_tokens": 20, "output_tokens": 10},
        },
    ]

    def chat(**kwargs):
        assert all(tool["function"]["name"] != "write_file" for tool in kwargs["tools"])
        return responses.pop(0)

    judge = AgenticJudgeAgent(chat=chat, cwd=tmp_path, model="judge-model", provider="anthropic")
    trace = await judge.run(
        AgentRequest(
            task="Judge",
            acceptance_criteria=("answer is 42",),
            context={"original_task": "Implement answer", "solver_trace": {"role": "developer"}},
            read_only=True,
            allowed_tools=("read_file",),
        )
    )

    assert trace.status == "completed"
    assert trace.metadata["verdict"] == "pass"
    assert trace.tool_calls[0].result == "answer = 42\n"
    assert trace.input_tokens == 20
    assert trace.output_tokens == 10
    assert {metric.name for metric in trace.metrics} == {
        "architecture_usefulness",
        "implementation_correctness",
        "test_coverage",
        "reviewer_precision",
        "cost_adjusted_contribution",
    }

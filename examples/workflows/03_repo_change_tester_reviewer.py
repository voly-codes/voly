"""Example 3: Repository change with tester and reviewer.

What it does: a manually-built Workflow (not a preset — this catalog
deliberately mixes builder styles) with a `mode="executor"` developer node
that writes files via AgentRunner, followed by two chat-only nodes (tester,
reviewer) that see the developer's output as context. Demonstrates the mixed
chat/executor graph the proposal's Phase 2 test suite covers
(tests/test_sdk_workflow.py::test_mixed_chat_executor_graph_honors_cwd).

Expected output (--offline): developer node reports files_touched=["app.py"];
tester and reviewer nodes verified with canned sign-off text.

Credentials: --offline patches both AgentRunner.run (developer) and
AIGateway.chat (tester/reviewer) — no credentials or network. A live run
needs a real `cwd` (a git repo) and whatever the configured executor
(claude-code by default) requires — see docs/backend/executors.md.

Cost/safety notes: this is the only example that can write files. `cwd` is
required (Agent(mode="executor") raises AgentError without one); the
executor's own safety policy (dry-run, safe-path checks) applies unchanged —
this example adds no additional sandboxing of its own.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent, Workflow
from voly.executor.base import ExecutorResult, WorkReport
from voly.runner.agent_runner import RunnerResult
from voly.sdk.workflow import WorkflowResult


def build_workflow(config=None):
    developer = Agent("developer", mode="executor", executor="claude-code", config=config)
    tester = Agent("tester", instructions="Assess test coverage for the change above.", config=config)
    reviewer = Agent("reviewer", instructions="Give a final go/no-go on the change above.", config=config)

    workflow = Workflow("repo-change", config=config)
    workflow.add("develop", agent=developer, task="Add input validation to the login handler.")
    workflow.add("test", agent=tester, depends_on=["develop"])
    workflow.add("review", agent=reviewer, depends_on=["test"])
    return workflow


def _offline_runner_result() -> RunnerResult:
    report = WorkReport(summary="Added input validation", files_changed=["app.py"])
    er = ExecutorResult(success=True, output="Added validation in app.py", report=report)
    return RunnerResult(success=True, executor="claude-code", agent="developer", task_id="offline-tid", result=er)


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    content = "Coverage looks sufficient." if agent == "tester" else "Approved: safe, well-scoped change."
    return {"content": content, "model": "offline-fake", "usage": {"input_tokens": 8, "output_tokens": 8}}


def main(offline: bool = False, cwd: str | None = None) -> WorkflowResult:
    workflow = build_workflow()
    task = "Harden the login handler against malformed input."
    if offline:
        with patch("voly.runner.agent_runner.AgentRunner.run", return_value=_offline_runner_result()), \
             patch("voly.ai_gateway.gateway.AIGateway.chat", _offline_chat):
            return workflow.run(task, cwd=cwd or "/tmp/offline-example-repo")
    if not cwd:
        raise SystemExit("--cwd is required for a live run (a git repository)")
    return workflow.run(task, cwd=cwd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cwd", default=None, help="Target git repo (required unless --offline)")
    args = parser.parse_args()
    result = main(offline=args.offline, cwd=args.cwd)
    print(f"success={result.success}  status={result.status}  cost=${result.cost_usd:.6f}")
    for node in result.node_results:
        print(f"  [{node.status}] {node.node_id}: files={node.files_touched} {node.output[:120]}")

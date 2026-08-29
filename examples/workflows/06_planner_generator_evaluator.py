"""Example 6: Planner -> Generator -> Evaluator.

What it does: voly.sdk.presets.planner_generator_evaluator() — a fixed
3-role chain with a structured contract between roles (each role's default
task states what it consumes/produces; see docs/backend/sdk.md).

Expected output (--offline): plan -> generate -> evaluate, all verified, in
that exact order (NodeResult ordering follows declaration order, not
completion order — this graph is fully sequential anyway).

Credentials: none in --offline mode.

Cost/safety notes: 3 chat calls, no file writes, no external action.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent
from voly.sdk.presets import planner_generator_evaluator
from voly.sdk.workflow import WorkflowResult


def build_workflow(config=None):
    planner = Agent("planner", instructions="Break the feature into concrete steps.", config=config)
    generator = Agent("coder", instructions="Implement the plan as pseudocode.", config=config)
    evaluator = Agent("qa", instructions="Check the implementation against the plan.", config=config)
    return planner_generator_evaluator(planner, generator, evaluator, name="feature-pipeline", config=config)


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    content = {
        "planner": "1) Validate input 2) Persist record 3) Return confirmation.",
        "coder": "def submit(data): validate(data); save(data); return confirm()",
        "qa": "Matches the plan; all 3 steps present. Approved.",
    }[agent]
    return {"content": content, "model": "offline-fake", "usage": {"input_tokens": 8, "output_tokens": 8}}


def main(offline: bool = False) -> WorkflowResult:
    workflow = build_workflow()
    task = "Implement a form-submission feature."
    if offline:
        with patch("voly.ai_gateway.gateway.AIGateway.chat", _offline_chat):
            return workflow.run(task)
    return workflow.run(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    result = main(offline=args.offline)
    print(f"success={result.success}  status={result.status}  cost=${result.cost_usd:.6f}")
    for node in result.node_results:
        print(f"  [{node.status}] {node.node_id}: {node.output[:160]}")

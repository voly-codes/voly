"""Example 1: Sequential research + review.

What it does: two chat-only Agents run in a strict A -> B chain built with
voly.sdk.presets.sequential(). The reviewer's prompt automatically includes
the researcher's output (PlanRunner's dependency-output handoff — see
docs/backend/plan.md) without any manual templating.

Expected output (--offline): both nodes verified, WorkflowResult.success is
True, and the reviewer's canned output references the researcher's figures.

Credentials: none in --offline mode (AIGateway.chat is replaced with a
canned function, no network call is made). For a live run, whatever
AIGateway provider credentials voly.yaml/.env already configure for `voly
run` (see docs/backend/ai-gateway.md) — nothing extra.

Cost/safety notes: two chat calls, no file writes, no external action — the
cheapest and safest example in this catalog.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent
from voly.sdk.presets import sequential
from voly.sdk.workflow import WorkflowResult


def build_workflow(config=None):
    researcher = Agent(
        "researcher", instructions="Find verifiable market facts.", config=config
    )
    reviewer = Agent(
        "reviewer", instructions="Check claims and sources for consistency.", config=config
    )
    return sequential([researcher, reviewer], name="research-review", config=config)


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    if agent == "researcher":
        content = "Market A grew 5% YoY; Market B grew 2% YoY (synthetic --offline data)."
    else:
        content = "Reviewed: both figures are internally consistent; no red flags."
    return {
        "content": content,
        "model": "offline-fake",
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def main(offline: bool = False) -> WorkflowResult:
    workflow = build_workflow()
    task = "Compare two markets and summarize the growth trend."
    if offline:
        with patch("voly.ai_gateway.gateway.AIGateway.chat", _offline_chat):
            return workflow.run(task)
    return workflow.run(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Use canned responses, no credentials/network"
    )
    args = parser.parse_args()
    result = main(offline=args.offline)
    print(f"success={result.success}  status={result.status}  cost=${result.cost_usd:.6f}")
    for node in result.node_results:
        print(f"  [{node.status}] {node.node_id}: {node.output[:160]}")

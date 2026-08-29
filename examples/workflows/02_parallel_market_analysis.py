"""Example 2: Parallel market analysis with synthesis.

What it does: voly.sdk.presets.supervisor_workers() dispatches from a lead
analyst, runs three regional analysts concurrently (bounded by
workflow_sdk.max_parallel_nodes), then the *same* lead role synthesizes all
three outputs into one result. This is the S -> workers -> S2 shape, not a
bare voly.sdk.presets.concurrent() (which has no synthesis step).

Expected output (--offline): 5 nodes total (supervise, us/eu/apac workers,
synthesize) all verified; the synthesize node's canned output references all
three regional figures, proving the dependency-output handoff reached it.

Credentials: none in --offline mode. Live run: same AIGateway credentials as
any other chat call.

Cost/safety notes: 5 chat calls (1 dispatch + 3 workers + 1 synthesis), no
file writes. Concurrency does not change total cost, only wall time.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent
from voly.sdk.presets import supervisor_workers
from voly.sdk.workflow import WorkflowResult

_REGION_FIGURES = {"us-analyst": "US demand +4%", "eu-analyst": "EU demand +1%", "apac-analyst": "APAC demand +9%"}


def build_workflow(config=None):
    lead = Agent("lead-analyst", instructions="Coordinate a regional demand study.", config=config)
    workers = [
        Agent(name, instructions=f"Analyze {name.split('-')[0].upper()} demand.", config=config)
        for name in _REGION_FIGURES
    ]
    return supervisor_workers(
        lead, workers, name="market-analysis",
        synthesis_task="Synthesize the three regional figures above into one demand outlook.",
        config=config,
    )


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    prompt = kwargs["messages"][0]["content"]
    if agent in _REGION_FIGURES:
        content = _REGION_FIGURES[agent]
    elif "Synthesize" in prompt:
        # The synthesis node's prompt is dependency context (worker outputs)
        # prepended to its own task text, which ends with "Synthesize ...".
        content = "Global outlook: APAC leads growth (+9%), US steady (+4%), EU soft (+1%)."
    else:
        content = "Dispatching regional analysts: US, EU, APAC."
    return {"content": content, "model": "offline-fake", "usage": {"input_tokens": 8, "output_tokens": 8}}


def main(offline: bool = False) -> WorkflowResult:
    workflow = build_workflow()
    task = "Assess global demand this quarter."
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

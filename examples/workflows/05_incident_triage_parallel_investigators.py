"""Example 5: Incident triage with read-only parallel investigators.

What it does: a manually-built Workflow (diversifying from presets in this
catalog) runs three chat-only "investigator" agents concurrently — chat
mode is inherently read-only (no executor, no file/network access) — then a
triage lead synthesizes all three findings into one severity call. Same
S-workers-S2 shape as example 2's supervisor_workers() preset, built by hand
here to show the raw builder API for a case with no initial dispatch step
(the investigators need no shared briefing before starting).

Expected output (--offline): 4 nodes verified; the triage node's canned
output references all three investigators' findings.

Credentials: none in --offline mode.

Cost/safety notes: 4 chat calls, no file writes, no external action —
"read-only" here is a property of chat mode itself, not a configured
parameter.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent, Workflow
from voly.sdk.workflow import WorkflowResult

_INVESTIGATORS = {
    "logs-investigator": "Error rate spiked 400% at 14:02 UTC, correlates with a deploy.",
    "metrics-investigator": "p99 latency up 3x on the checkout service since 14:00 UTC.",
    "customer-investigator": "12 support tickets filed in the last 20 minutes, all checkout failures.",
}


def build_workflow(config=None):
    workflow = Workflow("incident-triage", config=config)
    for name in _INVESTIGATORS:
        workflow.add(name, agent=Agent(name, instructions="Investigate read-only; report findings only.", config=config))
    workflow.add(
        "triage",
        agent=Agent("triage-lead", instructions="Assign a severity and root-cause hypothesis.", config=config),
        depends_on=list(_INVESTIGATORS),
    )
    return workflow


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    if agent in _INVESTIGATORS:
        content = _INVESTIGATORS[agent]
    else:
        content = "SEV-2: checkout regression, root cause the 14:02 UTC deploy — recommend rollback."
    return {"content": content, "model": "offline-fake", "usage": {"input_tokens": 8, "output_tokens": 8}}


def main(offline: bool = False) -> WorkflowResult:
    workflow = build_workflow()
    task = "Triage the ongoing checkout incident."
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

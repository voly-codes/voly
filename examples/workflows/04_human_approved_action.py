"""Example 4: Human-approved action gate.

What it does: a manager Agent drafts a proposed action, the node is marked
`approval=True` (compiles to an AcceptanceCheck(type="human_review")), the
run pauses until voly.plan.approval.decide() resolves it, then
Workflow.resume(plan_id) continues to a notifier node.

IMPORTANT — honest scope note: this demonstrates the generic Workflow
approval *gate* (pause/approve/resume), not a literal governed HTTP dispatch.
voly.executor.http_action.HttpActionExecutor (the SSRF-hardened executor that
actually sends the approved request) is currently wired only into
voly.decisions.DecisionService for `metadata.kind == "business_decision"`
Plans (see docs/backend/decisions.md) — it is not reachable through
Agent(mode="executor", executor=...) / Workflow today (not in
voly.runner.executor_factory.EXECUTOR_NAMES). The "notify" node below is a
chat call describing the action, not a real network request. A true
human-approved *HTTP* action still means using DecisionService directly, or
extending EXECUTOR_NAMES to expose HttpActionExecutor generically — future
work, not something faked here.

Expected output (--offline): "decide" node runs and pauses in `verifying`
(WorkflowResult.success is False, status "running"); after approve() +
resume(), "notify" runs and the final result succeeds.

Credentials: none in --offline mode.

Cost/safety notes: one chat call before the gate, one after. No file writes,
no external network call — see the scope note above.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from voly import Agent, Workflow
from voly.plan.approval import decide as decide_human_review
from voly.plan.store import PlanStore
from voly.sdk.workflow import WorkflowResult


def build_workflow(config=None):
    manager = Agent("manager", instructions="Propose one specific account action.", config=config)
    notifier = Agent("notifier", instructions="Describe the approved action as if notifying the customer.", config=config)

    workflow = Workflow("account-action", config=config)
    workflow.add("decide", agent=manager, approval=True)
    workflow.add("notify", agent=notifier, depends_on=["decide"])
    return workflow


def _offline_chat(self, **kwargs):
    agent = kwargs.get("agent", "")
    content = "Proposed: refund $12.00 for the duplicate charge." if agent == "manager" else "Notified customer of the approved $12.00 refund."
    return {"content": content, "model": "offline-fake", "usage": {"input_tokens": 6, "output_tokens": 6}}


def main(offline: bool = False, config=None) -> tuple[WorkflowResult, WorkflowResult]:
    """Returns (paused_result, resumed_result)."""
    from voly.config import VOLYConfig

    cfg = config or VOLYConfig()
    workflow = build_workflow(config=cfg)
    task = "A customer reports a duplicate charge."

    chat_patch = patch("voly.ai_gateway.gateway.AIGateway.chat", _offline_chat)
    if offline:
        chat_patch.start()
    try:
        paused = workflow.run(task)
        decide_human_review(PlanStore(cfg.plan.store_dir), paused.plan.plan_id, "decide", "approve")
        resumed = workflow.resume(paused.plan.plan_id)
        return paused, resumed
    finally:
        if offline:
            chat_patch.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    paused_result, resumed_result = main(offline=args.offline)
    print(f"paused:  success={paused_result.success} status={paused_result.status}")
    print(f"resumed: success={resumed_result.success} status={resumed_result.status}")
    for node in resumed_result.node_results:
        print(f"  [{node.status}] {node.node_id}: {node.output[:160]}")

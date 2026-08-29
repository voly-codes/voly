"""Example 7: Resumable long-running workflow.

What it does: a 3-node sequential chain run with a workflow-level
`timeout_seconds` short enough to expire mid-run (simulated with a slow
--offline chat function). The expired run is left resumable — status
"running", not "failed"/"aborted" — and Workflow.resume(plan_id) continues
it to completion without re-running the already-verified first node. Mirrors
tests/test_sdk_workflow.py::test_workflow_resume_continues_a_prior_run_by_plan_id.

Expected output (--offline): first call times out after node "a" completes;
resume() finishes "b" and "c" and reports success.

Credentials: none in --offline mode.

Cost/safety notes: 3 chat calls total, split across two process-level calls
to run()/resume() — demonstrating that a crash or a deliberate deadline
between the two costs nothing extra (no step is ever re-run once verified).
"""

from __future__ import annotations

import argparse
import time
from unittest.mock import patch

from voly import Agent, Workflow
from voly.sdk.workflow import WorkflowResult


def build_workflow(config=None):
    workflow = Workflow("long-running", config=config)
    workflow.add("a", agent=Agent("stage-a", config=config))
    workflow.add("b", agent=Agent("stage-b", config=config), depends_on=["a"])
    workflow.add("c", agent=Agent("stage-c", config=config), depends_on=["b"])
    return workflow


def _slow_offline_chat(self, **kwargs):
    time.sleep(0.15)
    return {"content": "ok", "model": "offline-fake", "usage": {"input_tokens": 4, "output_tokens": 4}}


def _fast_offline_chat(self, **kwargs):
    return {"content": "ok", "model": "offline-fake", "usage": {"input_tokens": 4, "output_tokens": 4}}


def main(offline: bool = False, config=None) -> tuple[WorkflowResult, WorkflowResult]:
    """Returns (timed_out_result, resumed_result)."""
    from voly.config import VOLYConfig

    cfg = config or VOLYConfig()
    if offline:
        cfg.workflow_sdk.max_parallel_nodes = 1
    workflow = build_workflow(config=cfg)
    task = "Run the long pipeline."

    if offline:
        with patch("voly.ai_gateway.gateway.AIGateway.chat", _slow_offline_chat):
            timed_out = workflow.run(task, timeout_seconds=0.25)
        with patch("voly.ai_gateway.gateway.AIGateway.chat", _fast_offline_chat):
            resumed = workflow.resume(timed_out.plan.plan_id)
        return timed_out, resumed

    timed_out = workflow.run(task, timeout_seconds=0.25)
    resumed = workflow.resume(timed_out.plan.plan_id)
    return timed_out, resumed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    timed_out_result, resumed_result = main(offline=args.offline)
    print(f"timed out:  success={timed_out_result.success} status={timed_out_result.status}")
    print(f"resumed:    success={resumed_result.success} status={resumed_result.status}")
    for node in resumed_result.node_results:
        print(f"  [{node.status}] {node.node_id}: {node.output[:120]}")

"""Public Agent and Workflow SDK (docs/proposals/agent-workflow-sdk.md).

A facade over existing runtime contracts (AIGateway, AgentRunner, Plan/PlanRunner)
— never a second orchestration stack. See ``docs/backend/sdk.md``.
"""

from voly.sdk.agent import Agent, AgentError, AgentResult
from voly.sdk.presets import (
    concurrent,
    council,
    planner_generator_evaluator,
    reviewer_loop,
    sequential,
    supervisor_workers,
)
from voly.sdk.workflow import (
    NodeResult,
    Workflow,
    WorkflowError,
    WorkflowNode,
    WorkflowResult,
)

__all__ = [
    "Agent", "AgentError", "AgentResult",
    "NodeResult", "Workflow", "WorkflowError", "WorkflowNode", "WorkflowResult",
    "sequential", "concurrent", "supervisor_workers", "reviewer_loop",
    "council", "planner_generator_evaluator",
]

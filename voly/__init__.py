"""
VOLY — Control Plane for AI Engineering Agents.

Архитектура:
    Developer / UI
        ↓
    VOLY
        ↓
    AG-UI Gateway (Agent↔UI)
        ↓
    A2A Orchestrator (Agent↔Agent)
        ↓
    Agent Router
        ↓
    Specialized Agents
        ↓
    RTK → Headroom → Memory → Model
        ↓
    Claude Sonnet / GPT / Gemini
        ↓
    MCP Tools / GitHub / Terminal / Docs / CI/CD / Cloud

Принципы:
    1. Model Agnostic
    2. Agent Agnostic
    3. MCP First
    4. Context Efficient
    5. Self Hosted First
    6. Enterprise Ready
    7. Observability by Default
"""

__version__ = "0.1.0"

from voly.config import VOLYConfig
from voly.pipeline import Pipeline
from voly.router import AgentRouter
from voly.sdk import (
    Agent,
    AgentError,
    AgentResult,
    NodeResult,
    Workflow,
    WorkflowError,
    WorkflowNode,
    WorkflowResult,
    concurrent,
    council,
    planner_generator_evaluator,
    reviewer_loop,
    sequential,
    supervisor_workers,
)

__all__ = [
    "VOLYConfig", "Pipeline", "AgentRouter",
    "Agent", "AgentError", "AgentResult",
    "NodeResult", "Workflow", "WorkflowError", "WorkflowNode", "WorkflowResult",
    "sequential", "concurrent", "supervisor_workers", "reviewer_loop",
    "council", "planner_generator_evaluator",
]

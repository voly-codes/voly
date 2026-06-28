"""
CodeOps — Control Plane for AI Engineering Agents.

Архитектура:
    Developer / UI
        ↓
    CodeOps
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

from codeops.config import CodeOpsConfig
from codeops.pipeline import Pipeline
from codeops.router import AgentRouter

__all__ = ["CodeOpsConfig", "Pipeline", "AgentRouter"]

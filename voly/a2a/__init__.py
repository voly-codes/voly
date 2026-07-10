"""
A2A Orchestrator — меж-агентная коммуникация по протоколу Agent2Agent (Google).

Позволяет:
    - Агентам находить друг друга через Agent Card
    - Делегировать подзадачи между агентами
    - Передавать результаты между агентами
    - Строить распределённые multi-agent workflows

Архитектура A2A:
    Orchestrator (A2A Client)
        ↓ обнаруживает через AgentCard
    Agent A (A2A Server)  Agent B (A2A Server)
        ↓                     ↓
    Специализированные задачи

Протокол: JSON-RPC 2.0 over HTTP + SSE streaming.
"""

from voly.a2a.protocol import (
    A2AAgent,
    A2AEventType,
    A2ATask,
    AgentCard,
    AgentSkill,
    TaskState,
)
from voly.a2a.orchestrator import (
    A2AClient,
    A2AOrchestrator,
    create_a2a_orchestrator,
)

__all__ = [
    "A2AAgent",
    "A2AClient",
    "A2AEventType",
    "A2AOrchestrator",
    "A2ATask",
    "AgentCard",
    "AgentSkill",
    "TaskState",
    "create_a2a_orchestrator",
]

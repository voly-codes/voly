"""
Federation backend — sync A2A orchestrator with remote Worker + D1 + Queue.
"""

from __future__ import annotations

from typing import Any

from voly.a2a import AgentCard, A2ATask, TaskState
from voly.a2a.federation import FederationClient


def task_from_remote(data: dict[str, Any]) -> A2ATask:
    try:
        state = TaskState(str(data.get("state", "submitted")))
    except ValueError:
        state = TaskState.SUBMITTED

    metadata = dict(data.get("metadata") or {})
    if data.get("agent_name"):
        metadata["routed_to"] = data["agent_name"]

    return A2ATask(
        id=str(data["id"]),
        state=state,
        title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        agent_url=str(metadata.get("agent_url", "")),
        result=str(data.get("result", "")),
        error=str(data.get("error", "")),
        metadata=metadata,
        created_at=float(data.get("created_at", 0)) / 1000.0 if data.get("created_at") else 0.0,
        updated_at=float(data.get("updated_at", 0)) / 1000.0 if data.get("updated_at") else 0.0,
    )


class FederationBackend:
    def __init__(self, client: FederationClient):
        self.client = client

    def sync_agents(self) -> list[AgentCard]:
        cards: list[AgentCard] = []
        for row in self.client.list_agents():
            cards.append(AgentCard.from_dict(row))
        return cards

    def register_agent_card(self, card: AgentCard) -> None:
        self.client.register_agent(card.to_dict())

    def create_remote_task(
        self,
        title: str,
        description: str,
        agent_name: str = "",
        *,
        async_dispatch: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> A2ATask:
        task_id = self.client.create_task(
            title,
            description,
            agent_name=agent_name,
            async_dispatch=async_dispatch,
            metadata=metadata,
        )
        data = self.client.get_task(task_id)
        return task_from_remote(data)

    def load_task(self, task_id: str) -> A2ATask | None:
        try:
            data = self.client.get_task(task_id)
        except Exception:
            return None
        return task_from_remote(data)

    def complete_task(self, task_id: str, result: str) -> A2ATask | None:
        self.client.complete_task(task_id, result)
        return self.load_task(task_id)

    def fail_task(self, task_id: str, error: str) -> A2ATask | None:
        self.client.fail_task(task_id, error)
        return self.load_task(task_id)

    def list_tasks(self, state: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self.client.list_tasks(state=state, limit=limit)

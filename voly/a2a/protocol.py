"""Протокольные типы A2A: состояния задач, Agent Card, skills."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class TaskState(Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class A2AEventType(Enum):
    TASK = "task"
    STATUS_UPDATE = "status-update"
    MESSAGE = "message"
    ARTIFACT_UPDATE = "artifact-update"


@dataclass
class AgentSkill:
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["text"])
    output_modes: list[str] = field(default_factory=lambda: ["text"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "examples": self.examples,
            "inputModes": self.input_modes,
            "outputModes": self.output_modes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentSkill:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            examples=data.get("examples", []),
            input_modes=data.get("inputModes", ["text"]),
            output_modes=data.get("outputModes", ["text"]),
        )


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    skills: list[AgentSkill] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    provider: str = ""
    authentication: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "skills": [s.to_dict() for s in self.skills],
            "capabilities": self.capabilities,
            "provider": self.provider,
        }
        if self.authentication:
            result["authentication"] = self.authentication
        return result

    @classmethod
    def from_dict(cls, data: dict) -> AgentCard:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            url=data.get("url", ""),
            version=data.get("version", "1.0.0"),
            skills=[AgentSkill.from_dict(s) for s in data.get("skills", [])],
            capabilities=data.get("capabilities", {}),
            provider=data.get("provider", ""),
            authentication=data.get("authentication"),
        )

    def match_task(self, task: str) -> list[tuple[AgentSkill, float]]:
        scored: list[tuple[AgentSkill, float]] = []
        tl = task.lower()
        for skill in self.skills:
            score = 0.0
            for tag in skill.tags:
                if tag.lower() in tl:
                    score += 0.4
            for example in skill.examples:
                if example.lower() in tl:
                    score += 0.3
            words = set(tl.split())
            desc_words = set(skill.description.lower().split())
            overlap = words & desc_words
            score += len(overlap) * 0.1
            if score > 0.1:
                scored.append((skill, min(score, 1.0)))
        return sorted(scored, key=lambda x: x[1], reverse=True)


@dataclass
class A2ATask:
    id: str
    state: TaskState = TaskState.SUBMITTED
    title: str = ""
    description: str = ""
    agent_url: str = ""
    result: str = ""
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.updated_at == 0.0:
            self.updated_at = time.time()


class A2AAgent:
    def __init__(self, card: AgentCard, executor: Callable | None = None):
        self.card = card
        self._executor = executor

    async def execute(self, task: A2ATask) -> str:
        if self._executor:
            import asyncio
            if asyncio.iscoroutinefunction(self._executor):
                return await self._executor(task)
            return self._executor(task)
        raise NotImplementedError(f"Agent {self.card.name} has no executor")

"""Catalog types — agents, models, mission plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CatalogModel:
    id: str
    name: str = ""
    provider: str = ""
    tier: str = "standard"  # free | cheap | standard | premium | stealth
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    executor_compat: list[str] = field(default_factory=lambda: ["zen"])
    strengths: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name or self.id,
            "provider": self.provider,
            "tier": self.tier,
            "input_cost_per_1m": self.input_cost_per_1m,
            "output_cost_per_1m": self.output_cost_per_1m,
            "executor_compat": self.executor_compat,
            "strengths": self.strengths,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogModel:
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            provider=data.get("provider", ""),
            tier=data.get("tier", "standard"),
            input_cost_per_1m=float(data.get("input_cost_per_1m") or 0),
            output_cost_per_1m=float(data.get("output_cost_per_1m") or 0),
            executor_compat=list(data.get("executor_compat") or ["zen"]),
            strengths=list(data.get("strengths") or []),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class MissionStepSpec:
    executor: str
    model: str
    agent_role: str = "developer"
    skills: list[str] = field(default_factory=list)
    readonly: bool = False
    free_fallback_model: str | None = None


@dataclass
class MissionPlan:
    mission_id: str
    supervisor_model: str = "claude-opus-4-8"
    steps: list[MissionStepSpec] = field(default_factory=list)

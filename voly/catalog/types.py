"""Catalog types — agents, models, mission plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _optional_bool(value: Any) -> bool | None:
    """Parse optional booleans without treating arbitrary strings as truthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


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
    # v2 metadata fields — backward-compatible; all have safe defaults
    base_url: str = ""
    context_window: int = 0  # tokens; 0 = unknown
    modalities: list[str] = field(default_factory=list)
    rate_limit: dict[str, Any] = field(default_factory=dict)  # rpm/rpd/tpm keys or "raw"
    auth_requirement: str = ""  # none | email | phone | credit_card | registration
    api_key_url: str = ""
    supports_tools: bool | None = None  # None = unknown — do not treat as True
    source_url: str = ""  # canonical URL of the model's info page
    upstream_model_id: str = ""  # provider-specific ID sent to the upstream API
    source_updated_at: str = ""  # ISO date string from source
    verified: bool = False  # must be explicitly set; False = not verified
    last_verified_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
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
        # Only write v2 fields when non-default so old consumers can ignore them
        if self.base_url:
            d["base_url"] = self.base_url
        if self.context_window:
            d["context_window"] = self.context_window
        if self.modalities:
            d["modalities"] = self.modalities
        if self.rate_limit:
            d["rate_limit"] = self.rate_limit
        if self.auth_requirement:
            d["auth_requirement"] = self.auth_requirement
        if self.api_key_url:
            d["api_key_url"] = self.api_key_url
        if self.supports_tools is not None:
            d["supports_tools"] = self.supports_tools
        if self.source_url:
            d["source_url"] = self.source_url
        if self.upstream_model_id:
            d["upstream_model_id"] = self.upstream_model_id
        if self.source_updated_at:
            d["source_updated_at"] = self.source_updated_at
        if self.verified:
            d["verified"] = self.verified
        if self.last_verified_at:
            d["last_verified_at"] = self.last_verified_at
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogModel:
        supports_tools = _optional_bool(data.get("supports_tools"))
        verified = _optional_bool(data.get("verified")) is True
        executor_compat = (
            list(data.get("executor_compat") or [])
            if "executor_compat" in data
            else ["zen"]
        )
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            provider=data.get("provider", ""),
            tier=data.get("tier", "standard"),
            input_cost_per_1m=float(data.get("input_cost_per_1m") or 0),
            output_cost_per_1m=float(data.get("output_cost_per_1m") or 0),
            executor_compat=executor_compat,
            strengths=list(data.get("strengths") or []),
            enabled=bool(data.get("enabled", True)),
            base_url=str(data.get("base_url") or ""),
            context_window=int(data.get("context_window") or 0),
            modalities=list(data.get("modalities") or []),
            rate_limit=dict(data.get("rate_limit") or {}),
            auth_requirement=str(data.get("auth_requirement") or ""),
            api_key_url=str(data.get("api_key_url") or ""),
            supports_tools=supports_tools,
            source_url=str(data.get("source_url") or ""),
            upstream_model_id=str(data.get("upstream_model_id") or ""),
            source_updated_at=str(data.get("source_updated_at") or ""),
            verified=verified,
            last_verified_at=str(data.get("last_verified_at") or ""),
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

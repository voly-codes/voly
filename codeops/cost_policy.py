"""
Cost Policy — выбор дешёвой модели и контроль бюджета на задачу.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from voly.config import VOLYConfig
from voly.router import RouteDecision

TASK_TYPE_PATTERNS: dict[str, list[str]] = {
    "docs": [
        r"document",
        r"readme",
        r"wiki",
        r"документ",
        r"описани",
        r"changelog",
    ],
    "tests": [
        r"\btest\b",
        r"pytest",
        r"unittest",
        r"vitest",
        r"тест",
        r"spec\b",
    ],
    "summarization": [
        r"summar",
        r"summary",
        r"кратк",
        r"сводк",
        r"обзор",
        r"audit report",
    ],
}


@dataclass
class CostPolicyResult:
    task_type: str | None = None
    model_override: str | None = None
    provider_override: str | None = None
    budget_exceeded: bool = False
    reason: str = ""


def detect_task_type(task: str) -> str | None:
    text = task.lower()
    for task_type, patterns in TASK_TYPE_PATTERNS.items():
        if any(re.search(pat, text) for pat in patterns):
            return task_type
    return None


def apply_cost_policy(
    route: RouteDecision,
    task: str,
    config: VOLYConfig,
) -> CostPolicyResult:
    """Подбирает более дешёвую модель для подходящих типов задач."""
    policy = config.cost_policy
    if not policy.enabled:
        return CostPolicyResult()

    task_type = detect_task_type(task)
    if not task_type or task_type not in policy.prefer_cheaper_model_for:
        return CostPolicyResult(task_type=task_type)

    cheaper = policy.cheaper_model_map.get(task_type, policy.cheaper_model)
    if cheaper == route.model:
        return CostPolicyResult(task_type=task_type)

    model_cfg = config.get_model_config(cheaper)
    return CostPolicyResult(
        task_type=task_type,
        model_override=cheaper,
        provider_override=model_cfg.provider,
        reason=f"prefer_cheaper_model_for:{task_type}",
    )


def is_budget_exceeded(cost_usd: float, config: VOLYConfig) -> bool:
    policy = config.cost_policy
    if not policy.enabled or not policy.stop_on_budget_exceeded:
        return False
    return cost_usd > policy.max_task_cost_usd


def budget_status(cost_usd: float, config: VOLYConfig) -> str:
    """Return TaskEvent status — completed or budget_exceeded."""
    if is_budget_exceeded(cost_usd, config):
        return "budget_exceeded"
    return "completed"

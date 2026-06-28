"""Spend tracking integration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codeops.config import CodeOpsConfig
    from codeops.telemetry import TaskEvent


def record_task_spend(event: TaskEvent, config: CodeOpsConfig) -> None:
    spend_cfg = getattr(config, "spend", None)
    if spend_cfg is None or not spend_cfg.enabled or not spend_cfg.remote_url:
        return
    if event.cost_usd <= 0:
        return

    from codeops.spend.client import create_spend_client

    client = create_spend_client(spend_cfg.remote_url)
    if not client:
        return
    try:
        client.record(
            event.agent,
            event.cost_usd,
            task_id=event.task_id,
            model=event.model,
            provider=event.provider,
        )
    except Exception:
        pass


def check_agent_spend_limit(agent: str, config: CodeOpsConfig) -> dict[str, Any] | None:
    spend_cfg = getattr(config, "spend", None)
    if spend_cfg is None or not spend_cfg.enabled or not spend_cfg.remote_url:
        return None

    from codeops.spend.client import create_spend_client

    client = create_spend_client(spend_cfg.remote_url)
    if not client:
        return None

    limit = spend_cfg.daily_budget_usd
    per_agent = config.ai_gateway.spend_per_agent_budget.get(agent)
    if per_agent is not None:
        limit = per_agent

    try:
        return client.check(agent, limit)
    except Exception:
        return None

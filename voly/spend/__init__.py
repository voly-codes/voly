"""Spend tracking integration helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from voly.config import VOLYConfig
    from voly.telemetry import TaskEvent


def record_task_spend(event: TaskEvent, config: VOLYConfig) -> None:
    spend_cfg = getattr(config, "spend", None)
    if spend_cfg is None or not spend_cfg.enabled or not spend_cfg.remote_url:
        return
    if event.cost_usd <= 0:
        return

    from voly.spend.client import create_spend_client

    client = create_spend_client(spend_cfg.remote_url)
    if not client:
        return
    product = getattr(spend_cfg, "product", "voly") or "voly"
    try:
        # Each call is one logical spend event, so it gets its own event_id.
        client.record(
            event.agent,
            event.cost_usd,
            task_id=event.task_id,
            model=event.model,
            provider=event.provider,
            product=product,
        )
    except Exception:
        # Spend reporting must never break a run. An unknown product raises
        # ValueError here and is dropped; config validation should catch it.
        pass


def check_agent_spend_limit(agent: str, config: VOLYConfig) -> dict[str, Any] | None:
    spend_cfg = getattr(config, "spend", None)
    if spend_cfg is None or not spend_cfg.enabled or not spend_cfg.remote_url:
        return None

    from voly.spend.client import create_spend_client

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

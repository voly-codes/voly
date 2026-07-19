"""Executor name resolution, billing chain, and factory for AgentRunner."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from voly.config import VOLYConfig
from voly.executor.base import Executor, ExecutorResult, classify_failure, executor_failure_details

EXECUTOR_NAMES = frozenset({
    "cursor", "claude-code", "mimo", "opencode", "deepseek", "zen", "wrangler",
    "cf-containers",
})

# When a paid executor fails with a billing error, try the next one in order.
# Only file-writing executors are listed — text-only providers (deepseek, workers-ai)
# cannot apply code changes and must not appear here.
#
# Chain:
#   claude-code  — Anthropic (billed to Anthropic account)
#   cursor       — Cursor API (CURSOR_API_KEY)
#   deepseek     — DeepSeek API file-writing executor
#   wrangler     — CF Workers AI via wrangler dev (billed to CF account, separate billing)
#   opencode     — OpenCode Go (opencode.ai/zen/go); starts with mimo-v2.5-free
#   zen          — OpenCode Zen (opencode.ai/zen); tries all free models in sequence
BILLING_FALLBACK_CHAIN: list[str] = ["claude-code", "cursor", "deepseek", "wrangler", "opencode", "zen"]

EXECUTOR_ALIASES: dict[str, str] = {
    "claude": "claude-code",
    "codex": "claude-code",
}

DEFAULT_AGENT_EXECUTOR: dict[str, str] = {
    "cursor": "cursor",
    "developer": "cursor",
    "architect": "cursor",
    "bugfixer": "cursor",
    "tester": "mimo",
    "reviewer": "zen",
    "documenter": "deepseek",
    "security": "zen",
    "devops": "opencode",
    "product-analyst": "zen",
    "claude": "claude-code",
}


def resolve_executor(agent: str, config: VOLYConfig) -> tuple[str, str]:
    """
    Разрешает имя агента/executor в (executor_name, agent_role).

    agent_role — роль для телеметрии; executor_name — фактический backend.
    """
    key = agent.lower().strip()
    key = EXECUTOR_ALIASES.get(key, key)

    if key in EXECUTOR_NAMES:
        return key, agent

    agent_cfg = config.agents.get(key)
    if agent_cfg and agent_cfg.executor:
        return agent_cfg.executor, key

    try:
        from voly.registry.agents import AgentRegistry

        reg = AgentRegistry()
        definition = reg.get(key)
        if definition and definition.metadata.get("executor"):
            return str(definition.metadata["executor"]), key
    except Exception:
        pass

    if key in DEFAULT_AGENT_EXECUTOR:
        return DEFAULT_AGENT_EXECUTOR[key], key

    default = config.default_agent
    if default in EXECUTOR_NAMES:
        return default, key
    if default in DEFAULT_AGENT_EXECUTOR:
        return DEFAULT_AGENT_EXECUTOR[default], key
    if default in config.agents and config.agents[default].executor:
        return config.agents[default].executor, key

    return "cursor", key


def _chain_timelog_entry(
    executor_name: str,
    result: ExecutorResult,
    *,
    status: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """One billing-fallback chain row for UI/API/telemetry."""
    if status is None:
        if result.success:
            status = "success"
        elif result.billing_error:
            status = "billing_error"
        elif result.not_available:
            status = "not_available"
        else:
            status = "failed"

    entry: dict[str, Any] = {
        "executor": executor_name,
        "model": result.metadata.get("model", "") if result.metadata else "",
        "status": status,
        "duration_ms": round(result.duration_ms),
        "cost_usd": round(result.cost_usd, 6),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "error": (result.error or "")[:200],
        "error_class": classify_failure(result),
    }
    if not result.success and status != "skipped":
        details = executor_failure_details(result, executor_name=executor_name)
        if details.get("error_message"):
            entry["error_message"] = details["error_message"][:200]
        if details.get("error_hint"):
            entry["error_hint"] = details["error_hint"]
    entry.update(extra)
    return entry


def _build_executor(executor_name: str, model: str | None = None) -> Executor:
    kwargs = {}
    if model:
        kwargs["model"] = model
    factories: dict[str, Callable[[], Executor]] = {
        "cursor": lambda: __import__(
            "voly.executor.cursor", fromlist=["CursorExecutor"]
        ).CursorExecutor(**kwargs),
        "claude-code": lambda: __import__(
            "voly.executor.claude_code", fromlist=["ClaudeCodeExecutor"]
        ).ClaudeCodeExecutor(),
        "mimo": lambda: __import__(
            "voly.executor.mimo", fromlist=["MiMoExecutor"]
        ).MiMoExecutor(),
        "opencode": lambda: __import__(
            "voly.executor.opencode", fromlist=["OpenCodeExecutor"]
        ).OpenCodeExecutor(**kwargs),
        "deepseek": lambda: __import__(
            "voly.executor.deepseek", fromlist=["DeepSeekExecutor"]
        ).DeepSeekExecutor(**kwargs),
        "zen": lambda: __import__(
            "voly.executor.zen", fromlist=["ZenExecutor"]
        ).ZenExecutor(**kwargs),
        "wrangler": lambda: __import__(
            "voly.executor.wrangler", fromlist=["WranglerExecutor"]
        ).WranglerExecutor(),
        "cf-containers": lambda: __import__(
            "voly.executor.cf_containers", fromlist=["CfContainersExecutor"]
        ).CfContainersExecutor(),
    }
    if executor_name not in factories:
        valid = ", ".join(sorted(factories))
        raise ValueError(f"Unknown executor: {executor_name}. Available: {valid}")
    return factories[executor_name]()

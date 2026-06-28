"""
Agent Runner — запуск IDE-агентов как подпроцессов с RTK, бюджетом и телеметрией.

    codeops runner cursor "implement auth"
    codeops runner developer "fix login bug"
    codeops runner claude-code "refactor api.ts"
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from codeops.automation import compute_automation_metrics
from codeops.config import CodeOpsConfig
from codeops.cost_policy import budget_status, detect_task_type
from codeops.executor.base import Executor, ExecutorResult
from codeops.telemetry import TaskEvent, TokenMetrics, emit_event_from_config, new_task_id

EXECUTOR_NAMES = frozenset({
    "cursor", "claude-code", "mimo", "opencode", "deepseek", "zen",
})

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


def resolve_executor(agent: str, config: CodeOpsConfig) -> tuple[str, str]:
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
        from codeops.registry.agents import AgentRegistry

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


def _build_executor(executor_name: str) -> Executor:
    factories: dict[str, Callable[[], Executor]] = {
        "cursor": lambda: __import__(
            "codeops.executor.cursor", fromlist=["CursorExecutor"]
        ).CursorExecutor(),
        "claude-code": lambda: __import__(
            "codeops.executor.claude_code", fromlist=["ClaudeCodeExecutor"]
        ).ClaudeCodeExecutor(),
        "mimo": lambda: __import__(
            "codeops.executor.mimo", fromlist=["MiMoExecutor"]
        ).MiMoExecutor(),
        "opencode": lambda: __import__(
            "codeops.executor.opencode", fromlist=["OpenCodeExecutor"]
        ).OpenCodeExecutor(),
        "deepseek": lambda: __import__(
            "codeops.executor.deepseek", fromlist=["DeepSeekExecutor"]
        ).DeepSeekExecutor(),
        "zen": lambda: __import__(
            "codeops.executor.zen", fromlist=["ZenExecutor"]
        ).ZenExecutor(),
    }
    if executor_name not in factories:
        valid = ", ".join(sorted(factories))
        raise ValueError(f"Unknown executor: {executor_name}. Available: {valid}")
    return factories[executor_name]()


@dataclass
class RunnerResult:
    success: bool
    executor: str
    agent: str
    task_id: str
    result: ExecutorResult
    automation_score: float = 0.0
    manual_steps_removed: int = 0
    task_type: str | None = None
    budget_exceeded: bool = False


class AgentRunner:
    def __init__(self, config: CodeOpsConfig):
        self.config = config

    def setup_rtk(self) -> None:
        if not self.config.rtk.enabled:
            return
        from codeops.rtk.installer import RTKManager

        rtk = RTKManager(self.config.rtk.binary_path)
        if not rtk.is_installed() and self.config.rtk.auto_install:
            try:
                rtk.install()
            except Exception:
                pass

    def run(
        self,
        task: str,
        agent: str,
        *,
        cwd: str,
        max_turns: int = 30,
        timeout: int = 300,
    ) -> RunnerResult:
        self.setup_rtk()

        executor_name, agent_role = resolve_executor(agent, self.config)
        task_type = detect_task_type(task)
        task_id = new_task_id()

        executor = _build_executor(executor_name)
        t0 = time.monotonic()
        result = executor.run(
            task,
            cwd=cwd,
            max_turns=max_turns,
            timeout=timeout,
        )
        if result.duration_ms <= 0:
            result.duration_ms = (time.monotonic() - t0) * 1000

        automation_score, manual_steps = compute_automation_metrics(
            executor_name, result, task_type=task_type
        )

        status = "failed"
        budget_exceeded = False
        if result.success:
            status = budget_status(result.cost_usd, self.config)
            budget_exceeded = status == "budget_exceeded"

        emit_event_from_config(TaskEvent(
            task_id=task_id,
            agent=agent_role,
            executor=executor_name,
            status=status,
            tokens=TokenMetrics(
                input=result.input_tokens,
                output=result.output_tokens,
            ),
            cost_usd=result.cost_usd,
            duration_ms=result.duration_ms,
            model=executor_name,
            provider=executor_name,
            task_type=task_type,
            automation_score=automation_score,
            manual_steps_removed=manual_steps,
            error=result.error if not result.success else (
                f"Budget exceeded: ${result.cost_usd:.4f} > "
                f"${self.config.cost_policy.max_task_cost_usd:.2f}"
                if budget_exceeded else None
            ),
        ), self.config)

        return RunnerResult(
            success=result.success and not budget_exceeded,
            executor=executor_name,
            agent=agent_role,
            task_id=task_id,
            result=result,
            automation_score=automation_score,
            manual_steps_removed=manual_steps,
            task_type=task_type,
            budget_exceeded=budget_exceeded,
        )

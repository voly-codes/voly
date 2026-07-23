"""
MultiAgentOrchestrator — параллельный запуск задач на нескольких агентах/провайдерах.

Распределяет задачи по провайдерам на основе типа задачи:

  cursor       → реальные изменения файлов (Cursor Agent API, local runtime)
  claude-code  → реальные изменения файлов (Read/Write/Bash)
  opencode     → agentic code execution (альтернатива claude-code)
  deepseek     → генерация кода (TypeScript, React, CSS)
  zen          → анализ, планирование, review
  mimo         → дешёвый батч (конфиги, скелеты, типы)

Использование:
  orchestrator = MultiAgentOrchestrator()
  results = orchestrator.run_parallel([
      AgentTask("deepseek", "Сгенерируй Contact TypeScript типы"),
      AgentTask("mimo", "Создай CSS переменные для дашборда"),
      AgentTask("claude-code", "Примени типы в src/types/", cwd="/project"),
  ])
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from voly.executor.base import Executor, ExecutorResult

AgentName = Literal["cursor", "claude-code", "opencode", "deepseek", "zen", "mimo"]


@dataclass
class AgentTask:
    agent: AgentName
    task: str
    cwd: str | None = None
    system: str | None = None
    max_turns: int = 30
    timeout: int = 300
    label: str = ""
    model: str | None = None
    agent_role: str = ""
    skills: list[str] = field(default_factory=list)
    readonly: bool = False
    mission_id: str = ""
    step_index: int = 0

    def __post_init__(self):
        if not self.label:
            self.label = f"{self.agent}: {self.task[:60]}"
        if not self.agent_role:
            self.agent_role = self.agent


@dataclass
class AgentTaskResult:
    task: AgentTask
    result: ExecutorResult
    agent_name: str
    started_at: str = ""
    finished_at: str = ""


@dataclass
class OrchestrationReport:
    tasks: list[AgentTaskResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    success_count: int = 0
    failure_count: int = 0

    def to_markdown(self, title: str = "Agent Report") -> str:
        lines = [
            f"# {title}",
            f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total duration:** {self.total_duration_ms/1000:.1f}s",
            f"**Tasks:** {self.success_count} succeeded, {self.failure_count} failed",
            f"**Tokens:** {self.total_input_tokens:,} in / {self.total_output_tokens:,} out",
            f"**Cost:** ${self.total_cost_usd:.4f}",
            "\n---\n",
        ]

        for tr in self.tasks:
            status = "OK" if tr.result.success else "FAILED"
            lines.append(f"## {status} [{tr.agent_name}] {tr.task.label}")
            lines.append(f"*{tr.started_at} → {tr.finished_at}*")
            lines.append(f"Tokens: {tr.result.input_tokens:,}↑ {tr.result.output_tokens:,}↓ | {tr.result.duration_ms:.0f}ms")
            lines.append("")
            if tr.result.success:
                output_preview = tr.result.output[:800]
                if len(tr.result.output) > 800:
                    output_preview += f"\n... [{len(tr.result.output) - 800} more chars]"
                lines.append(f"```\n{output_preview}\n```")
            else:
                lines.append(f"**Error:** {tr.result.error}")
            lines.append("")

        return "\n".join(lines)


def _build_executor(agent: AgentName, model: str | None = None) -> Executor:
    if agent == "cursor":
        from voly.executor.cursor import CursorExecutor
        return CursorExecutor(model=model) if model else CursorExecutor()
    if agent == "claude-code":
        from voly.executor.claude_code import ClaudeCodeExecutor
        return ClaudeCodeExecutor()
    if agent == "opencode":
        from voly.executor.opencode import OpenCodeExecutor
        return OpenCodeExecutor(model=model) if model else OpenCodeExecutor()
    if agent == "deepseek":
        from voly.executor.deepseek import DeepSeekExecutor
        return DeepSeekExecutor(model=model) if model else DeepSeekExecutor()
    if agent == "zen":
        from voly.executor.zen import ZenExecutor
        return ZenExecutor(model=model) if model else ZenExecutor()
    if agent == "mimo":
        from voly.executor.mimo import MiMoExecutor
        return MiMoExecutor()
    raise ValueError(f"Unknown agent: {agent}")


def _emit_combat_telemetry(agent_task: AgentTask, result: ExecutorResult) -> None:
    try:
        from voly.automation import compute_automation_metrics
        from voly.config import load_config
        from voly.cost_policy import budget_status, detect_task_type
        from voly.telemetry import (
            TaskEvent,
            TokenMetrics,
            _estimate_cost,
            emit_event_from_config,
            new_task_id,
        )

        config = load_config()
        task_type = detect_task_type(agent_task.task)
        automation_score, manual_steps = compute_automation_metrics(
            agent_task.agent,
            result,
            task_type=task_type,
        )
        status = "failed"
        if result.success:
            status = budget_status(result.cost_usd, config)

        meta = result.metadata or {}
        model_name = meta.get("model") or agent_task.model or agent_task.agent
        cost = result.cost_usd
        if cost <= 0 and (result.input_tokens or result.output_tokens):
            cost = _estimate_cost(model_name, result.input_tokens, result.output_tokens)

        emit_event_from_config(
            TaskEvent(
                task_id=new_task_id(),
                agent=agent_task.agent_role or agent_task.agent,
                executor=agent_task.agent,
                status=status,
                tokens=TokenMetrics(
                    input=result.input_tokens,
                    output=result.output_tokens,
                ),
                cost_usd=cost,
                duration_ms=result.duration_ms,
                model=model_name,
                provider=meta.get("provider") or agent_task.agent,
                task_type=task_type,
                automation_score=automation_score,
                manual_steps_removed=manual_steps,
                skill_ids=list(agent_task.skills),
                workflow=agent_task.mission_id or None,
                error=result.error if not result.success else None,
            ),
            config,
        )
    except Exception:
        pass


def _run_task(agent_task: AgentTask, *, emit_telemetry: bool = True) -> AgentTaskResult:
    started_at = datetime.now().strftime("%H:%M:%S")
    executor = _build_executor(agent_task.agent, agent_task.model)

    kwargs: dict = {
        "task": agent_task.task,
        "cwd": agent_task.cwd,
        "max_turns": agent_task.max_turns,
        "timeout": agent_task.timeout,
    }
    if agent_task.system and hasattr(executor, "run"):
        import inspect
        sig = inspect.signature(executor.run)
        if "system" in sig.parameters:
            kwargs["system"] = agent_task.system

    result = executor.run(**kwargs)
    finished_at = datetime.now().strftime("%H:%M:%S")

    if emit_telemetry:
        _emit_combat_telemetry(agent_task, result)

    return AgentTaskResult(
        task=agent_task,
        result=result,
        agent_name=agent_task.agent,
        started_at=started_at,
        finished_at=finished_at,
    )


class MultiAgentOrchestrator:
    """Run tasks across multiple AI providers in parallel."""

    def __init__(self, reports_dir: str | Path | None = None):
        self.reports_dir = Path(reports_dir) if reports_dir else None

    def run_parallel(
        self,
        tasks: list[AgentTask],
        max_workers: int = 4,
        report_title: str = "Multi-Agent Report",
        save_report: bool = True,
    ) -> OrchestrationReport:
        """Run tasks in parallel across agents, return consolidated report."""
        wall_start = time.monotonic()
        task_results: list[AgentTaskResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_task, t): t for t in tasks}
            for future in concurrent.futures.as_completed(futures):
                try:
                    tr = future.result()
                except Exception as e:
                    task = futures[future]
                    tr = AgentTaskResult(
                        task=task,
                        result=ExecutorResult(success=False, error=str(e)),
                        agent_name=task.agent,
                        started_at="",
                        finished_at=datetime.now().strftime("%H:%M:%S"),
                    )
                task_results.append(tr)

        wall_ms = (time.monotonic() - wall_start) * 1000

        report = OrchestrationReport(
            tasks=task_results,
            total_duration_ms=wall_ms,
            total_input_tokens=sum(tr.result.input_tokens for tr in task_results),
            total_output_tokens=sum(tr.result.output_tokens for tr in task_results),
            total_cost_usd=sum(tr.result.cost_usd for tr in task_results),
            success_count=sum(1 for tr in task_results if tr.result.success),
            failure_count=sum(1 for tr in task_results if not tr.result.success),
        )

        if save_report and self.reports_dir:
            self._save_report(report, report_title)

        return report

    def run_sequential(
        self,
        tasks: list[AgentTask],
        report_title: str = "Multi-Agent Report",
        save_report: bool = True,
        stop_on_failure: bool = False,
        emit_telemetry: bool = True,
    ) -> OrchestrationReport:
        """Run tasks sequentially (useful when tasks depend on each other)."""
        wall_start = time.monotonic()
        task_results: list[AgentTaskResult] = []
        for t in tasks:
            tr = _run_task(t, emit_telemetry=emit_telemetry)
            task_results.append(tr)
            if stop_on_failure and not tr.result.success:
                break
        wall_ms = (time.monotonic() - wall_start) * 1000

        report = OrchestrationReport(
            tasks=task_results,
            total_duration_ms=wall_ms,
            total_input_tokens=sum(tr.result.input_tokens for tr in task_results),
            total_output_tokens=sum(tr.result.output_tokens for tr in task_results),
            total_cost_usd=sum(tr.result.cost_usd for tr in task_results),
            success_count=sum(1 for tr in task_results if tr.result.success),
            failure_count=sum(1 for tr in task_results if not tr.result.success),
        )

        if save_report and self.reports_dir:
            self._save_report(report, report_title)

        return report

    def _save_report(self, report: OrchestrationReport, title: str) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = title.lower().replace(" ", "-").replace("/", "-")[:40]
        filename = f"{timestamp}_{slug}.md"
        path = self.reports_dir / filename
        path.write_text(report.to_markdown(title=title), encoding="utf-8")
        return path

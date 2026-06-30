"""
Agent Runner — запуск IDE-агентов как подпроцессов с RTK, бюджетом и телеметрией.

    codeops runner cursor "implement auth"
    codeops runner developer "fix login bug"
    codeops runner claude-code "refactor api.ts"
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

from codeops.automation import compute_automation_metrics
from codeops.config import CodeOpsConfig
from codeops.cost_policy import budget_status, detect_task_type
from codeops.executor.base import Executor, ExecutorResult, WorkReport
from codeops.telemetry import TaskEvent, TokenMetrics, emit_event_from_config, new_task_id


# ── Git helpers ───────────────────────────────────────────────────────────────

def _git_porcelain(cwd: str) -> dict[str, str]:
    """Return {path: status_code} from `git status --porcelain`."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        ).stdout
        result: dict[str, str] = {}
        for line in out.splitlines():
            if len(line) < 4:
                continue
            xy, path = line[:2], line[3:].strip()
            # Handle renames: "old -> new"
            if " -> " in path:
                path = path.split(" -> ")[-1]
            result[path] = xy.strip() or "?"
        return result
    except Exception:
        return {}


def _extract_summary(output: str) -> str:
    """Pull a short summary out of the agent's text output."""
    if not output:
        return ""
    # Split into paragraphs; prefer the last non-trivial one
    paragraphs = [p.strip() for p in output.split("\n\n") if p.strip()]
    if not paragraphs:
        return output[:600]
    # Look for a paragraph that reads like a summary
    summary_keywords = ("итого", "в итоге", "выполнено", "сделано", "изменено",
                        "summary", "in summary", "done", "completed", "changes made")
    for p in reversed(paragraphs):
        if any(kw in p.lower() for kw in summary_keywords):
            return p[:800]
    # Fall back to last paragraph
    return paragraphs[-1][:800]


def _build_work_report(output: str, before: dict[str, str], after: dict[str, str]) -> WorkReport:
    changed, created, deleted, actions = [], [], [], []
    all_paths = set(before) | set(after)
    for path in sorted(all_paths):
        b, a = before.get(path), after.get(path)
        if b is None and a is not None:
            (deleted if "D" in (a or "") else created).append(path)
        elif a is None and b is not None:
            deleted.append(path)
        elif a != b:
            changed.append(path)

    # Extract action lines: look for "- ", "•", numbered items in output
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "• ", "* ")) and len(stripped) > 10:
            actions.append(stripped[2:].strip())
        elif len(stripped) > 5 and stripped[0].isdigit() and stripped[1] in ".):":
            actions.append(stripped[2:].strip())
    actions = actions[:20]  # cap

    return WorkReport(
        summary=_extract_summary(output),
        files_changed=changed,
        files_created=created,
        files_deleted=deleted,
        actions=actions,
    )

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
        git_before = _git_porcelain(cwd)
        t0 = time.monotonic()
        result = executor.run(
            task,
            cwd=cwd,
            max_turns=max_turns,
            timeout=timeout,
        )
        if result.duration_ms <= 0:
            result.duration_ms = (time.monotonic() - t0) * 1000

        git_after = _git_porcelain(cwd)
        work_report = _build_work_report(result.output or "", git_before, git_after)
        result.report = work_report

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
            task_prompt=task[:2000] if task else None,
            result=result.output[:8000] if result.output else None,
            report=work_report.to_dict() if work_report else None,
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

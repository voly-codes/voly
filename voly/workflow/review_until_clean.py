"""Bounded developer/reviewer repair loop.

This is deliberately one concrete workflow, not a general workflow engine.
File changes go through ``AgentRunner`` and reviews go through ``AIGateway``.
Every transition is recorded as a lap and every exit has an explicit reason.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from voly.a2a.assignment import resolve_role_model
from voly.a2a.context import git_diff_evidence


class ReviewVerdict(str, Enum):
    CLEAN = "clean"
    BLOCKING = "blocking"


class ReviewStopReason(str, Enum):
    CLEAN = "clean"
    MAX_ROUNDS = "max_rounds"
    DEADLINE = "deadline"
    EXECUTOR_FAILED = "executor_failed"
    REVIEW_FAILED = "review_failed"
    SPEND_LIMIT = "spend_limit"


@dataclass
class ReviewLap:
    number: int
    developer_task_id: str = ""
    developer_executor: str = ""
    developer_output: str = ""
    files_touched: list[str] = field(default_factory=list)
    reviewer_provider: str = ""
    reviewer_model: str = ""
    reviewer_output: str = ""
    verdict: ReviewVerdict | None = None
    findings: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class ReviewLoopResult:
    success: bool
    stop_reason: ReviewStopReason
    laps: list[ReviewLap] = field(default_factory=list)
    error: str = ""

    @property
    def total_cost_usd(self) -> float:
        return round(sum(lap.cost_usd for lap in self.laps), 6)

    @property
    def duration_ms(self) -> float:
        return round(sum(lap.duration_ms for lap in self.laps), 1)


class ReviewUntilClean:
    """Run a developer, review its diff, and repair blocking findings."""

    def __init__(
        self,
        *,
        runner: Any,
        gateway: Any,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.runner = runner
        self.gateway = gateway
        self.clock = clock

    def run(
        self,
        task: str,
        *,
        cwd: str,
        executor: str = "claude-code",
        max_rounds: int = 3,
        deadline_seconds: float = 900.0,
        executor_timeout: int = 300,
        max_turns: int = 30,
        reviewer_model: str = "",
        reviewer_provider: str = "",
    ) -> ReviewLoopResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        if not cwd.strip():
            raise ValueError("cwd must not be empty")
        if not 1 <= max_rounds <= 20:
            raise ValueError("max_rounds must be between 1 and 20")
        if deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")

        model, provider = self._reviewer_route(reviewer_model, reviewer_provider)
        started = self.clock()
        laps: list[ReviewLap] = []
        findings: list[str] = []

        for number in range(1, max_rounds + 1):
            remaining = deadline_seconds - (self.clock() - started)
            if remaining <= 0:
                return ReviewLoopResult(False, ReviewStopReason.DEADLINE, laps)

            lap_started = self.clock()
            developer_task = self._developer_task(task, number, findings)
            timeout = max(1, min(executor_timeout, math.ceil(remaining)))
            run = self.runner.run(
                developer_task,
                executor,
                cwd=cwd,
                max_turns=max_turns,
                timeout=timeout,
                emit_event=False,
                collect_evidence=False,
            )
            lap = self._lap_from_run(number, run)
            laps.append(lap)

            if not run.success:
                lap.error = run.result.error or "developer executor failed"
                lap.duration_ms = self._elapsed_ms(lap_started)
                reason = (
                    ReviewStopReason.SPEND_LIMIT
                    if getattr(run, "budget_exceeded", False)
                    else ReviewStopReason.EXECUTOR_FAILED
                )
                return ReviewLoopResult(False, reason, laps, lap.error)

            remaining = deadline_seconds - (self.clock() - started)
            if remaining <= 0:
                lap.duration_ms = self._elapsed_ms(lap_started)
                return ReviewLoopResult(False, ReviewStopReason.DEADLINE, laps)

            review = self.gateway.chat(
                [{"role": "user", "content": self._review_prompt(task, lap, cwd)}],
                model=model,
                provider_name=provider,
                max_tokens=4096,
                temperature=0.0,
                system=self._review_system_prompt(),
                agent="reviewer",
            )
            lap.reviewer_provider = str(review.get("provider") or provider)
            lap.reviewer_model = str(review.get("model") or model)
            lap.reviewer_output = str(review.get("content") or "")
            lap.cost_usd += self._review_cost(review)
            lap.duration_ms = self._elapsed_ms(lap_started)

            if review.get("error"):
                lap.error = str(review["error"])
                reason = (
                    ReviewStopReason.SPEND_LIMIT
                    if review.get("spend_limited")
                    else ReviewStopReason.REVIEW_FAILED
                )
                return ReviewLoopResult(False, reason, laps, lap.error)

            try:
                lap.verdict, lap.findings = parse_review_verdict(lap.reviewer_output)
            except ValueError as exc:
                lap.error = str(exc)
                return ReviewLoopResult(
                    False, ReviewStopReason.REVIEW_FAILED, laps, lap.error,
                )

            if lap.verdict is ReviewVerdict.CLEAN:
                return ReviewLoopResult(True, ReviewStopReason.CLEAN, laps)
            findings = lap.findings

        return ReviewLoopResult(False, ReviewStopReason.MAX_ROUNDS, laps)

    def _reviewer_route(self, model: str, provider: str) -> tuple[str, str]:
        if model and provider:
            return model, provider
        resolved_model, resolved_provider = resolve_role_model("reviewer", "standard")
        return model or resolved_model, provider or resolved_provider

    def _lap_from_run(self, number: int, run: Any) -> ReviewLap:
        result = run.result
        report = result.report
        files: list[str] = []
        if report is not None:
            files = list(dict.fromkeys([
                *(report.files_changed or []),
                *(report.files_created or []),
                *(report.files_deleted or []),
            ]))
        return ReviewLap(
            number=number,
            developer_task_id=str(run.task_id or ""),
            developer_executor=str(run.executor or ""),
            developer_output=str(result.output or ""),
            files_touched=files,
            cost_usd=float(result.cost_usd or 0.0),
        )

    def _elapsed_ms(self, started: float) -> float:
        return max(0.0, (self.clock() - started) * 1000.0)

    @staticmethod
    def _developer_task(task: str, number: int, findings: list[str]) -> str:
        if number == 1:
            return task
        bullets = "\n".join(f"- {finding}" for finding in findings)
        return (
            "Continue the original task and repair every blocking review finding.\n\n"
            f"## Original task\n{task}\n\n"
            f"## Blocking findings from the previous review\n{bullets}\n\n"
            "Inspect the current working tree, make the fixes, and run focused checks. "
            "Do not revert unrelated user changes."
        )

    @staticmethod
    def _review_system_prompt() -> str:
        return (
            "You are an independent code reviewer. Review only correctness, security, "
            "regressions, and missing verification that can block completion. Return "
            "strict JSON only: {\"verdict\":\"clean|blocking\","
            "\"findings\":[\"specific actionable finding\"],\"summary\":\"short\"}. "
            "Use verdict clean only when there are no blocking findings."
        )

    @staticmethod
    def _review_prompt(task: str, lap: ReviewLap, cwd: str) -> str:
        evidence = git_diff_evidence(cwd, lap.files_touched, max_chars=8000)
        return (
            f"## Original task\n{task}\n\n"
            f"## Developer report\n{lap.developer_output[:4000]}\n\n"
            f"## Files touched\n{json.dumps(lap.files_touched, ensure_ascii=False)}\n\n"
            f"{evidence or 'No git diff evidence was available.'}"
        )

    @staticmethod
    def _review_cost(review: dict[str, Any]) -> float:
        raw = review.get("cost_usd", review.get("cost", 0.0))
        try:
            return float(raw or 0.0)
        except (TypeError, ValueError):
            return 0.0


def parse_review_verdict(content: str) -> tuple[ReviewVerdict, list[str]]:
    """Parse and validate the reviewer's fail-closed JSON verdict."""
    raw = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("reviewer returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("reviewer verdict must be a JSON object")
    try:
        verdict = ReviewVerdict(str(data.get("verdict") or "").lower())
    except ValueError as exc:
        raise ValueError("reviewer verdict must be clean or blocking") from exc
    raw_findings = data.get("findings") or []
    if not isinstance(raw_findings, list):
        raise ValueError("reviewer findings must be a list")
    findings = [str(item).strip() for item in raw_findings if str(item).strip()]
    if verdict is ReviewVerdict.BLOCKING and not findings:
        raise ValueError("blocking verdict requires at least one finding")
    if verdict is ReviewVerdict.CLEAN and findings:
        raise ValueError("clean verdict cannot include blocking findings")
    return verdict, findings

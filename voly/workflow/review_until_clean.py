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
    CANCELLED = "cancelled"


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
    developer_cost_usd: float = 0.0
    reviewer_cost_usd: float = 0.0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class ReviewLoopResult:
    success: bool
    stop_reason: ReviewStopReason
    laps: list[ReviewLap] = field(default_factory=list)
    error: str = ""
    workflow_id: str = ""

    @property
    def total_cost_usd(self) -> float:
        return round(sum(lap.cost_usd for lap in self.laps), 6)

    @property
    def duration_ms(self) -> float:
        return round(sum(lap.duration_ms for lap in self.laps), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "workflow": "review-until-clean",
            "task_id": self.workflow_id,
            "stop_reason": self.stop_reason.value,
            "error": self.error,
            "total_cost_usd": self.total_cost_usd,
            "duration_ms": self.duration_ms,
            "laps": [
                {
                    "number": lap.number,
                    "developer_task_id": lap.developer_task_id,
                    "developer_executor": lap.developer_executor,
                    "files_touched": list(lap.files_touched),
                    "reviewer_provider": lap.reviewer_provider,
                    "reviewer_model": lap.reviewer_model,
                    "verdict": lap.verdict.value if lap.verdict else None,
                    "findings": list(lap.findings),
                    "developer_cost_usd": round(lap.developer_cost_usd, 6),
                    "reviewer_cost_usd": round(lap.reviewer_cost_usd, 6),
                    "cost_usd": round(lap.cost_usd, 6),
                    "duration_ms": round(lap.duration_ms, 1),
                    "error": lap.error,
                }
                for lap in self.laps
            ],
        }


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
        tracker: Any = None,
        workflow_id: str = "",
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

        if tracker is not None and workflow_id:
            tracker.start(workflow_id, task, ["developer", "reviewer"])
            tracker.workflow_update(
                workflow_id,
                workflow="review-until-clean",
                max_laps=max_rounds,
                active_role="developer",
            )

        for number in range(1, max_rounds + 1):
            if self._cancelled(tracker, workflow_id):
                return self._finish(
                    ReviewLoopResult(False, ReviewStopReason.CANCELLED, laps),
                    tracker, workflow_id,
                )
            remaining = deadline_seconds - (self.clock() - started)
            if remaining <= 0:
                return self._finish(
                    ReviewLoopResult(False, ReviewStopReason.DEADLINE, laps),
                    tracker, workflow_id,
                )

            self._transition(
                tracker, workflow_id, number, "reviewer" if number > 1 else "start",
                "developer", "initial_task" if number == 1 else "blocking_findings",
            )

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
                return self._finish(
                    ReviewLoopResult(False, reason, laps, lap.error), tracker, workflow_id,
                )

            remaining = deadline_seconds - (self.clock() - started)
            if remaining <= 0:
                lap.duration_ms = self._elapsed_ms(lap_started)
                return self._finish(
                    ReviewLoopResult(False, ReviewStopReason.DEADLINE, laps),
                    tracker, workflow_id,
                )

            if self._cancelled(tracker, workflow_id):
                return self._finish(
                    ReviewLoopResult(False, ReviewStopReason.CANCELLED, laps),
                    tracker, workflow_id,
                )
            self._transition(
                tracker, workflow_id, number, "developer", "reviewer", "implementation_ready",
            )

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
            lap.reviewer_cost_usd = self._review_cost(review)
            lap.cost_usd += lap.reviewer_cost_usd
            lap.duration_ms = self._elapsed_ms(lap_started)

            if review.get("error"):
                lap.error = str(review["error"])
                reason = (
                    ReviewStopReason.SPEND_LIMIT
                    if review.get("spend_limited")
                    else ReviewStopReason.REVIEW_FAILED
                )
                return self._finish(
                    ReviewLoopResult(False, reason, laps, lap.error), tracker, workflow_id,
                )

            try:
                lap.verdict, lap.findings = parse_review_verdict(lap.reviewer_output)
            except ValueError as exc:
                lap.error = str(exc)
                return self._finish(
                    ReviewLoopResult(
                        False, ReviewStopReason.REVIEW_FAILED, laps, lap.error,
                    ),
                    tracker, workflow_id,
                )

            if tracker is not None and workflow_id:
                tracker.workflow_update(
                    workflow_id,
                    lap=number,
                    latest_verdict=lap.verdict.value,
                )
            if lap.verdict is ReviewVerdict.CLEAN:
                return self._finish(
                    ReviewLoopResult(True, ReviewStopReason.CLEAN, laps),
                    tracker, workflow_id,
                )
            findings = lap.findings

        return self._finish(
            ReviewLoopResult(False, ReviewStopReason.MAX_ROUNDS, laps),
            tracker, workflow_id,
        )

    @staticmethod
    def _cancelled(tracker: Any, workflow_id: str) -> bool:
        return bool(
            tracker is not None
            and workflow_id
            and tracker.cancellation_requested(workflow_id)
        )

    def _transition(
        self,
        tracker: Any,
        workflow_id: str,
        lap: int,
        source: str,
        target: str,
        reason: str,
    ) -> None:
        if tracker is None or not workflow_id:
            return
        tracker.workflow_update(
            workflow_id,
            lap=lap,
            active_role=target,
            transition={
                "lap": lap,
                "from": source,
                "to": target,
                "reason": reason,
                "at": time.time(),
            },
        )

    @staticmethod
    def _finish(
        result: ReviewLoopResult,
        tracker: Any,
        workflow_id: str,
    ) -> ReviewLoopResult:
        if tracker is not None and workflow_id:
            tracker.workflow_update(
                workflow_id,
                active_role="",
                stop_reason=result.stop_reason.value,
            )
            tracker.finish(
                workflow_id,
                status="completed" if result.success else "failed",
                error=result.error,
            )
        result.workflow_id = workflow_id
        return result

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
        developer_cost = float(result.cost_usd or 0.0)
        return ReviewLap(
            number=number,
            developer_task_id=str(run.task_id or ""),
            developer_executor=str(run.executor or ""),
            developer_output=str(result.output or ""),
            files_touched=files,
            developer_cost_usd=developer_cost,
            cost_usd=developer_cost,
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

"""
Agent Runner — запуск IDE-агентов как подпроцессов с RTK, бюджетом и телеметрией.

    voly runner cursor "implement auth"
    voly runner developer "fix login bug"
    voly runner claude-code "refactor api.ts"

Helpers live in focused modules (stable re-exports kept for tests/monkeypatch):

- ``work_report.py``       — git porcelain + WorkReport
- ``executor_factory.py``  — names, billing chain, ``_build_executor``
- ``dspy_hooks.py``        — optional TaskPlanner plan/store
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

_chain_log = logging.getLogger("voly.chain")

from voly.automation import compute_automation_metrics
from voly.config import VOLYConfig
from voly.cost_policy import budget_status, detect_task_type
from voly.executor.base import ExecutorResult, classify_failure, executor_failure_details
from voly.pxpipe.artifacts import capture_pxpipe_artifacts, collect_pxpipe_artifacts
from voly.runner.dspy_hooks import _dspy_plan_task, _dspy_store_example
from voly.runner.executor_factory import (
    BILLING_FALLBACK_CHAIN,
    DEFAULT_AGENT_EXECUTOR,
    EXECUTOR_ALIASES,
    EXECUTOR_NAMES,
    _build_executor,
    _chain_timelog_entry,
    resolve_executor,
)
from voly.runner.work_report import _build_work_report, _extract_summary, _git_porcelain
from voly.telemetry import TaskEvent, TokenMetrics, emit_event_from_config, new_task_id

__all__ = [
    "BILLING_FALLBACK_CHAIN",
    "DEFAULT_AGENT_EXECUTOR",
    "EXECUTOR_ALIASES",
    "EXECUTOR_NAMES",
    "AgentRunner",
    "RunnerResult",
    "resolve_executor",
    "_build_executor",
    "_build_work_report",
    "_dspy_plan_task",
    "_dspy_store_example",
    "_extract_summary",
    "_git_porcelain",
]


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
    def __init__(self, config: VOLYConfig):
        self.config = config

    def setup_rtk(self) -> None:
        if not self.config.rtk.enabled:
            return
        from voly.rtk.installer import RTKManager

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
        model: str = "",
        emit_event: bool = True,
        dry_run: bool = False,
        correlation_id: str = "",
        collect_evidence: bool = True,
    ) -> RunnerResult:
        from voly.correlation import ensure_correlation_id, get_correlation_id

        self.setup_rtk()

        cid = ensure_correlation_id(correlation_id or None)
        executor_name, agent_role = resolve_executor(agent, self.config)
        task_type = detect_task_type(task)
        task_id = new_task_id()

        executor = _build_executor(executor_name, model or None)
        _chain_log.info(
            "[CHAIN:START] correlation_id=%s task=%r executor=%s cwd=%r",
            cid, task[:80], executor_name, cwd or "(empty)",
        )

        # In-flight visibility (Rung A): a RunRecord with a background heartbeat
        # so CLI/web can see the run while the blocking executor subprocess works.
        # Best-effort — tracker failures must never break the run.
        tracker = None
        hb_stop = None
        hb_state = {"executor": executor_name}
        if getattr(getattr(self.config, "telemetry", None), "enabled", True):
            try:
                import threading

                from voly.runtime.runs import RunTracker

                tracker = RunTracker(self.config.telemetry.runs_dir)
                tracker.start(task_id, task, [executor_name])
                hb_stop = threading.Event()

                def _hb_loop() -> None:
                    while not hb_stop.wait(10.0):
                        try:
                            tracker.heartbeat(task_id, hb_state["executor"], 0)
                        except Exception:  # noqa: BLE001
                            pass

                threading.Thread(target=_hb_loop, daemon=True).start()
            except Exception:  # noqa: BLE001
                tracker = None

        # DSPy task planning stage: refine the task before handing to executor.
        # Active only when dspy.enabled and the task_planner program exists in registry.
        effective_task = task
        dspy_plan_result: dict[str, Any] | None = None
        dspy_cfg = getattr(self.config, "dspy", None)
        if dspy_cfg and getattr(dspy_cfg, "enabled", False) and getattr(dspy_cfg, "mode", "off") != "off":
            try:
                effective_task, dspy_plan_result = _dspy_plan_task(task, self.config)
            except Exception as exc:
                logging.getLogger("voly.chain").debug("[CHAIN:DSPY_PLAN] error=%s", exc)

        git_before = _git_porcelain(cwd)
        # Pre-run snapshot for the safety policy: lets rollback restore the
        # exact pre-run content even of files that were already dirty.
        from voly.executor.safety import apply_safety_policy, git_snapshot
        safety_cfg = getattr(self.config, "executor_safety", None)
        safety_snapshot = ""
        if cwd and safety_cfg is not None and getattr(safety_cfg, "enabled", True):
            safety_snapshot = git_snapshot(cwd)
        t0 = time.monotonic()
        with capture_pxpipe_artifacts(self.config, task_id):
            result = executor.run(
                effective_task,
                cwd=cwd,
                max_turns=max_turns,
                timeout=timeout,
            )
        pxpipe_artifacts = collect_pxpipe_artifacts(self.config, task_id)
        if result.duration_ms <= 0:
            result.duration_ms = (time.monotonic() - t0) * 1000
        if pxpipe_artifacts:
            result.metadata["artifacts"] = pxpipe_artifacts

        _chain_log.info(
            "[CHAIN:RESULT] executor=%s success=%s billing_error=%s duration_ms=%.0f error=%r",
            executor_name, result.success, result.billing_error,
            result.duration_ms, (result.error or "")[:120],
        )

        # Chain timelog: records each executor attempt for UI display.
        def _chain_status(r: ExecutorResult) -> str:
            if r.success:
                return "success"
            if r.billing_error:
                return "billing_error"
            if r.not_available:
                return "not_available"
            return "failed"

        chain_timelog: list[dict[str, Any]] = [
            _chain_timelog_entry(executor_name, result, status=_chain_status(result))
        ]

        # Spend of abandoned chain attempts. Folded into the TaskEvent totals so
        # a task's cost stays truthful across retries (этап 1: retry-aware cost).
        retry_count = 0
        retry_cost_usd = 0.0
        retry_tokens_in = 0
        retry_tokens_out = 0

        # Billing/availability fallback: walk the chain when current executor can't run the task.
        # Triggers on billing_error (no credits) OR not_available (service not running).
        _should_fallback = (result.billing_error or result.not_available) and executor_name in BILLING_FALLBACK_CHAIN
        if _should_fallback:
            chain = BILLING_FALLBACK_CHAIN
            start_idx = chain.index(executor_name) + 1
            first_fallback_from = executor_name
            for fallback_name in chain[start_idx:]:
                fallback_executor = _build_executor(fallback_name)

                # Pre-check: skip executors that are already known to be unavailable
                if hasattr(fallback_executor, "is_available") and not fallback_executor.is_available():
                    _chain_log.warning(
                        "[CHAIN:SKIP] %s not available — trying next in chain",
                        fallback_name,
                    )
                    chain_timelog.append({
                        "executor": fallback_name,
                        "model": "",
                        "status": "skipped",
                        "duration_ms": 0,
                        "error": "service not running",
                        "error_class": "not_available",
                        "error_message": "Executor service unavailable: service not running",
                        "error_hint": (
                            "Start the required service before retrying "
                            "(e.g. `wrangler dev` for wrangler)."
                        ),
                    })
                    continue

                reason = "billing" if result.billing_error else "not_available"
                _chain_log.warning(
                    "[CHAIN:BILLING_FALLBACK] %s → %s  reason=%s  detail=%r",
                    executor_name, fallback_name, reason, (result.error or "")[:120],
                )
                fb_t0 = time.monotonic()
                fb_result = fallback_executor.run(effective_task, cwd=cwd, max_turns=max_turns, timeout=timeout)
                if fb_result.duration_ms <= 0:
                    fb_result.duration_ms = (time.monotonic() - fb_t0) * 1000
                fb_result.metadata["billing_fallback_from"] = first_fallback_from
                fb_result.metadata["billing_fallback_to"] = fallback_name
                # The current result is being abandoned — bank its spend before replacing.
                retry_count += 1
                retry_cost_usd += result.cost_usd
                retry_tokens_in += result.input_tokens
                retry_tokens_out += result.output_tokens
                executor_name = fallback_name
                hb_state["executor"] = fallback_name
                result = fb_result
                chain_timelog.append(
                    _chain_timelog_entry(fallback_name, result, status=_chain_status(result))
                )
                _chain_log.info(
                    "[CHAIN:FALLBACK_RESULT] executor=%s success=%s billing_error=%s not_available=%s duration_ms=%.0f",
                    executor_name, result.success, result.billing_error,
                    result.not_available, result.duration_ms,
                )
                if not result.billing_error and not result.not_available:
                    break

        # Store chain timelog only if fallback actually happened (>1 entry)
        if len(chain_timelog) > 1:
            result.metadata["chain_timelog"] = chain_timelog
        if pxpipe_artifacts:
            result.metadata["artifacts"] = pxpipe_artifacts

        # DSPy example collection: store (task, result) for later optimization.
        if dspy_plan_result is not None and result.output:
            try:
                _dspy_store_example(task, effective_task, result, self.config)
            except Exception as exc:
                logging.getLogger("voly.chain").debug("[CHAIN:DSPY_STORE] error=%s", exc)

        git_after = _git_porcelain(cwd)
        work_report = _build_work_report(result.output or "", git_before, git_after)
        result.report = work_report

        # Safety policy: dry-run rollback / protected paths / max files touched.
        safety = apply_safety_policy(
            cwd=cwd,
            policy=safety_cfg,
            snapshot=safety_snapshot,
            before=git_before,
            after=git_after,
            dry_run=dry_run,
        )
        if safety.dry_run:
            result.metadata["dry_run"] = True
            if safety.diff_preview:
                result.metadata["dry_run_diff"] = safety.diff_preview
        if safety.violations:
            result.metadata["safety_violation"] = "; ".join(safety.violations)
            if safety.rolled_back:
                result.metadata["safety_rolled_back"] = list(safety.rolled_back)
            # Soft vs hard: max_files / full rollback → fail. Protected-path-only
            # rollback that leaves other files → keep success so multi-agent does
            # not cascade-skip tester/reviewer after a useful greenfield write.
            report_files = set()
            if work_report is not None:
                report_files = set(work_report.files_changed or []) | set(
                    work_report.files_created or []
                )
            remaining = sorted(report_files - set(safety.rolled_back or []))
            hard = any("max_files_touched" in v for v in safety.violations) or not remaining
            msg = "safety: " + "; ".join(safety.violations) + (
                f" (rolled back: {', '.join(safety.rolled_back[:10])})"
                if safety.rolled_back else ""
            )
            if hard:
                result.success = False
                result.error = msg
                _chain_log.warning("[CHAIN:SAFETY] hard fail: %s", msg[:200])
            else:
                result.metadata["safety_soft"] = True
                result.metadata["safety_remaining_files"] = remaining[:40]
                note = (
                    f"\n\n[safety] protected paths rolled back "
                    f"({', '.join(safety.rolled_back[:8])}); "
                    f"{len(remaining)} other file(s) kept — run continues."
                )
                result.output = ((result.output or "").rstrip() + note).strip()
                _chain_log.warning("[CHAIN:SAFETY] soft: %s kept=%d", msg[:160], len(remaining))
        elif safety.rolled_back:
            result.metadata["safety_rolled_back"] = list(safety.rolled_back)

        automation_score, manual_steps = compute_automation_metrics(
            executor_name, result, task_type=task_type
        )

        # Task totals include abandoned chain attempts — a retried task costs the
        # sum of everything it burned, not just the final executor's attempt.
        total_cost_usd = round(result.cost_usd + retry_cost_usd, 6)

        status = "failed"
        budget_exceeded = False
        if result.success:
            status = budget_status(total_cost_usd, self.config)
            budget_exceeded = status == "budget_exceeded"

        if hb_stop is not None:
            hb_stop.set()
        if tracker is not None:
            try:
                tracker.finish(
                    task_id,
                    status="completed" if result.success else "failed",
                    error=(result.error or "")[:500] if not result.success else "",
                )
            except Exception:  # noqa: BLE001
                pass

        if emit_event:
            failure_details = (
                executor_failure_details(result, executor_name=executor_name)
                if not result.success else {}
            )
            emit_event_from_config(TaskEvent(
                task_id=task_id,
                agent=agent_role,
                executor=executor_name,
                status=status,
                correlation_id=get_correlation_id() or cid,
                tokens=TokenMetrics(
                    input=result.input_tokens + retry_tokens_in,
                    output=result.output_tokens + retry_tokens_out,
                ),
                cost_usd=total_cost_usd,
                retry_count=retry_count,
                retry_cost_usd=round(retry_cost_usd, 6),
                error_class=classify_failure(result),
                duration_ms=result.duration_ms,
                model=result.metadata.get("model") if result.metadata else (model or executor_name),
                provider=result.metadata.get("provider") if result.metadata else executor_name,
                task_type=task_type,
                automation_score=automation_score,
                manual_steps_removed=manual_steps,
                error=(
                    failure_details.get("error_message")
                    or result.error
                    if not result.success else (
                        f"Budget exceeded: ${total_cost_usd:.4f} > "
                        f"${self.config.cost_policy.max_task_cost_usd:.2f}"
                        if budget_exceeded else None
                    )
                ),
                task_prompt=task[:2000] if task else None,
                result=result.output[:8000] if result.output else None,
                report=work_report.to_dict() if work_report else None,
                chain_timelog=chain_timelog if len(chain_timelog) > 1 else [],
                artifacts=pxpipe_artifacts,
            ), self.config)

        if collect_evidence:
            try:
                from voly.capability.evidence import fire_executor_evidence

                cap_cfg = getattr(self.config, "capability", None)
                worker_url = str(getattr(cap_cfg, "worker_url", "") or "")
                profiles_dir = str(
                    getattr(self.config, "capability_profiles_dir", None)
                    or ".voly/capability/profiles"
                )
                fire_executor_evidence(
                    executor_id=executor_name,
                    task=task,
                    result=result,
                    retry_count=retry_count,
                    agent_role=agent_role,
                    worker_url=worker_url,
                    profiles_dir=profiles_dir,
                )
            except Exception:  # noqa: BLE001
                pass

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

"""
Agent Runner — запуск IDE-агентов как подпроцессов с RTK, бюджетом и телеметрией.

    voly runner cursor "implement auth"
    voly runner developer "fix login bug"
    voly runner claude-code "refactor api.ts"
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

_chain_log = logging.getLogger("voly.chain")

from voly.automation import compute_automation_metrics
from voly.config import VOLYConfig
from voly.cost_policy import budget_status, detect_task_type
from voly.executor.base import Executor, ExecutorResult, WorkReport, classify_failure, executor_failure_details
from voly.pxpipe.artifacts import capture_pxpipe_artifacts, collect_pxpipe_artifacts
from voly.telemetry import TaskEvent, TokenMetrics, emit_event_from_config, new_task_id


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
            # Absent from the *before* porcelain = the file was clean-tracked
            # or did not exist. Only untracked (??) / staged-add (A) entries
            # are genuinely new; an "M" here is a tracked file modified during
            # the run — that's a change, not a creation.
            if "D" in a:
                deleted.append(path)
            elif a.startswith("?") or "A" in a:
                created.append(path)
            else:
                changed.append(path)
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


def _dspy_plan_task(
    task: str,
    config: "VOLYConfig",
) -> "tuple[str, dict]":
    """
    Use DSPy TaskPlannerProgram to refine the task before sending to executor.

    Returns (refined_task, plan_dict). On any failure returns original task unchanged.
    The plan_dict contains: refined_task, success_criteria, estimated_complexity.
    """
    from voly.dspy.programs.registry import get_registry
    from voly.dspy.adapter import VOLYDSPyLM
    from voly.ai_gateway import AIGateway

    registry = get_registry()
    program_def = registry.get("task_planner")
    if program_def is None:
        return task, {}

    import dspy

    gateway = AIGateway(config)
    lm = VOLYDSPyLM(
        gateway=gateway,
        model=getattr(config.dspy, "model", "") or "",
        provider="",
        agent="developer",
        max_tokens=1024,
        temperature=0.3,
    )
    dspy.configure(lm=lm)

    module = program_def.factory()
    prediction = module(task=task, project_context="VOLY project")

    refined  = getattr(prediction, "refined_task", "") or task
    criteria = getattr(prediction, "success_criteria", "") or ""
    complexity = getattr(prediction, "estimated_complexity", "") or ""

    if refined and refined.strip() and refined.strip() != task.strip():
        plan = {"refined_task": refined, "success_criteria": criteria, "estimated_complexity": complexity}
        _chain_log.info(
            "[CHAIN:DSPY_PLAN] complexity=%s criteria_lines=%d refined=%r",
            complexity, criteria.count("\n") + 1, refined[:80],
        )
        return refined, plan

    return task, {}


def _dspy_store_example(
    original_task: str,
    refined_task: str,
    result: "ExecutorResult",
    config: "VOLYConfig",
) -> None:
    """Persist a (task, result) example for DSPy teleprompter optimization."""
    import json
    import os

    datasets_dir = os.path.join(
        config.dspy.datasets_dir,
        "task_planner",
    )
    os.makedirs(datasets_dir, exist_ok=True)

    example = {
        "task": original_task,
        "refined_task": refined_task,
        "success": result.success,
        "output_len": len(result.output or ""),
        "cost_usd": result.cost_usd,
    }

    # One file per example. Unix-second timestamp alone collides when two
    # examples are produced within the same second (plausible with the
    # concurrent /api/run thread pool) and mode "w" silently overwrites the
    # earlier one — add a random suffix to guarantee uniqueness while keeping
    # the timestamp prefix for chronological sorting.
    import time as _time
    import uuid as _uuid
    fname = os.path.join(datasets_dir, f"{int(_time.time())}-{_uuid.uuid4().hex[:8]}.jsonl")
    with open(fname, "w") as f:
        f.write(json.dumps(example) + "\n")

    _chain_log.debug("[CHAIN:DSPY_STORE] saved example to %s", fname)


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
        if safety.rolled_back:
            result.metadata["safety_rolled_back"] = safety.rolled_back
        if safety.violations:
            result.metadata["safety_violation"] = "; ".join(safety.violations)
            result.success = False
            result.error = "safety: " + "; ".join(safety.violations) + (
                f" (rolled back: {', '.join(safety.rolled_back[:10])})"
                if safety.rolled_back else ""
            )
            _chain_log.warning("[CHAIN:SAFETY] %s", result.error[:200])

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

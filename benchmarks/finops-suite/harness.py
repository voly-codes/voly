"""Phase 2 harness — baseline vs VOLY chain using real AgentRunner + mock executors.

Cost numbers come from TaskEvent (retry-aware totals), not a parallel spreadsheet.
Layer A providers are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult
import voly.runner.agent_runner as runner_mod
from voly.runner.agent_runner import BILLING_FALLBACK_CHAIN, AgentRunner

from suite import BenchSuite, BenchTask


class _FakeExec:
    def __init__(self, name: str, result: ExecutorResult, available: bool = True):
        self._name = name
        self._result = result
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
        return self._result

    def is_available(self) -> bool:
        return self._available


def _billing(cost: float) -> ExecutorResult:
    return ExecutorResult(
        success=False,
        error="credit balance is too low",
        billing_error=True,
        cost_usd=cost,
        input_tokens=100,
        output_tokens=50,
        duration_ms=5,
    )


def _success(cost: float, output: str = "done") -> ExecutorResult:
    return ExecutorResult(
        success=True,
        output=output,
        cost_usd=cost,
        input_tokens=10,
        output_tokens=5,
        duration_ms=5,
    )


def _claude_rate(task: BenchTask) -> float:
    costs = task.mock.costs_usd
    if "claude-code" in costs:
        return float(costs["claude-code"])
    if task.mock.succeed_executor == "claude-code":
        return float(costs[task.mock.succeed_executor])
    raise ValueError(f"task {task.id}: costs_usd must include claude-code for baseline")


def _voly_fakes(task: BenchTask, chain: list[str]) -> dict[str, _FakeExec]:
    """Build fakes so the chain walks billing failures until succeed_executor."""
    succeed = task.mock.succeed_executor
    fail_set = set(task.mock.billing_fail_executors)
    costs = task.mock.costs_usd
    fakes: dict[str, _FakeExec] = {}

    if succeed not in chain:
        raise ValueError(
            f"task {task.id}: succeed_executor {succeed!r} not in chain {chain}"
        )

    for name in chain:
        cost = float(costs.get(name, 0.0))
        if name == succeed:
            fakes[name] = _FakeExec(name, _success(cost, output=f"ok:{task.id}"))
        elif name in fail_set or chain.index(name) < chain.index(succeed):
            # Intermediates before succeed must not stop the chain (billing_error).
            fakes[name] = _FakeExec(name, _billing(cost if name in fail_set or name in costs else 0.0))
        else:
            fakes[name] = _FakeExec(name, _billing(0.0), available=False)

    return fakes


@dataclass
class ArmResult:
    success: bool
    executor: str
    cost_usd: float
    retry_count: int = 0
    retry_cost_usd: float = 0.0
    executors_used: list[str] = field(default_factory=list)
    chain_timelog: list[dict[str, Any]] = field(default_factory=list)
    fallback: bool = False


def _run_agent(
    *,
    task: BenchTask,
    cwd: str,
    fakes: dict[str, _FakeExec],
    chain: list[str],
) -> ArmResult:
    events: list = []

    def _build(name: str, model: str | None = None) -> _FakeExec:
        if name not in fakes:
            raise KeyError(f"no fake for executor {name!r}")
        return fakes[name]

    with (
        patch.object(runner_mod, "_build_executor", _build),
        patch.object(runner_mod, "BILLING_FALLBACK_CHAIN", list(chain)),
        patch.object(
            runner_mod,
            "emit_event_from_config",
            lambda ev, cfg: events.append(ev),
        ),
    ):
        runner = AgentRunner(VOLYConfig())
        out = runner.run(task.prompt, "claude-code", cwd=cwd, emit_event=True, timeout=30)

    if not events:
        # Fallback: derive from RunnerResult if emit was skipped
        log = list(out.result.metadata.get("chain_timelog") or [])
        cost = float(out.result.cost_usd)
        used = [e["executor"] for e in log] if log else [out.executor]
        return ArmResult(
            success=bool(out.success),
            executor=out.executor,
            cost_usd=cost,
            executors_used=used,
            chain_timelog=log,
            fallback=len(used) > 1,
        )

    ev = events[0]
    log = list(ev.chain_timelog or [])
    if not log and out.result.metadata.get("chain_timelog"):
        log = list(out.result.metadata["chain_timelog"])
    used = [e["executor"] for e in log] if log else [ev.executor]
    return ArmResult(
        success=bool(out.success),
        executor=ev.executor,
        cost_usd=float(ev.cost_usd),
        retry_count=int(ev.retry_count or 0),
        retry_cost_usd=float(ev.retry_cost_usd or 0.0),
        executors_used=used,
        chain_timelog=log,
        fallback=len(used) > 1 or bool(ev.retry_count),
    )


def run_baseline(task: BenchTask, cwd: str) -> ArmResult:
    """Primary-only path: no cross-vendor fallback.

    Happy path: claude-code succeeds once.
    Billing-fallback tasks: counterfactual = failed primary attempt + top-up
    success on claude-code (what a single-vendor user pays to finish).
    """
    rate = _claude_rate(task)
    chain = ["claude-code"]

    if "billing_fallback" in task.scenarios and task.mock.billing_fail_executors:
        fail_arm = _run_agent(
            task=task,
            cwd=cwd,
            fakes={"claude-code": _FakeExec("claude-code", _billing(rate))},
            chain=chain,
        )
        ok_arm = _run_agent(
            task=task,
            cwd=cwd,
            fakes={"claude-code": _FakeExec("claude-code", _success(rate))},
            chain=chain,
        )
        return ArmResult(
            success=ok_arm.success,
            executor="claude-code",
            cost_usd=round(fail_arm.cost_usd + ok_arm.cost_usd, 6),
            retry_count=1,
            retry_cost_usd=fail_arm.cost_usd,
            executors_used=["claude-code", "claude-code"],
            chain_timelog=fail_arm.chain_timelog + ok_arm.chain_timelog,
            fallback=False,
        )

    return _run_agent(
        task=task,
        cwd=cwd,
        fakes={"claude-code": _FakeExec("claude-code", _success(rate))},
        chain=chain,
    )


def run_voly_chain(task: BenchTask, cwd: str, chain: list[str] | None = None) -> ArmResult:
    """Full billing fallback chain (Layer B)."""
    use_chain = list(chain or BILLING_FALLBACK_CHAIN)
    fakes = _voly_fakes(task, use_chain)
    return _run_agent(task=task, cwd=cwd, fakes=fakes, chain=use_chain)


@dataclass
class Row:
    task_id: str
    baseline_usd: float
    voly_usd: float
    saved_usd: float
    saved_pct: float
    executors_used: list[str]
    fallback: bool
    baseline_success: bool
    voly_success: bool
    category: str
    scenarios: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "baseline_usd": self.baseline_usd,
            "voly_usd": self.voly_usd,
            "saved_usd": self.saved_usd,
            "saved_pct": self.saved_pct,
            "executors_used": self.executors_used,
            "fallback": self.fallback,
            "baseline_success": self.baseline_success,
            "voly_success": self.voly_success,
            "category": self.category,
            "scenarios": self.scenarios,
        }


def run_task_comparison(
    task: BenchTask,
    cwd: str,
    *,
    chain: list[str] | None = None,
) -> Row:
    base = run_baseline(task, cwd)
    voly = run_voly_chain(task, cwd, chain=chain)
    saved = round(base.cost_usd - voly.cost_usd, 6)
    pct = round((saved / base.cost_usd) * 100.0, 2) if base.cost_usd > 0 else 0.0
    return Row(
        task_id=task.id,
        baseline_usd=base.cost_usd,
        voly_usd=voly.cost_usd,
        saved_usd=saved,
        saved_pct=pct,
        executors_used=voly.executors_used,
        fallback=voly.fallback,
        baseline_success=base.success,
        voly_success=voly.success,
        category=task.category,
        scenarios=list(task.scenarios),
    )


def run_suite_comparison(
    suite: BenchSuite,
    cwd: str,
    *,
    task_ids: list[str] | None = None,
) -> list[Row]:
    tasks = suite.tasks
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in suite.tasks if t.id in wanted]
    rows: list[Row] = []
    for task in tasks:
        rows.append(
            run_task_comparison(task, cwd, chain=suite.billing_fallback_chain)
        )
    return rows


def render_results_md(rows: list[Row], *, suite_id: str, generated_at: str) -> str:
    lines = [
        f"# FinOps benchmark results — `{suite_id}`",
        "",
        f"Generated: {generated_at}",
        "",
        "Baseline = primary-only `claude-code` (on billing_fallback tasks: failed "
        "attempt + top-up success). VOLY = full Layer B billing fallback chain.",
        "",
        "| task_id | baseline_usd | voly_usd | saved_usd | saved_pct | executors_used | fallback |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in rows:
        used = ", ".join(r.executors_used) if r.executors_used else "—"
        lines.append(
            f"| {r.task_id} | {r.baseline_usd:.4f} | {r.voly_usd:.4f} | "
            f"{r.saved_usd:.4f} | {r.saved_pct:.1f}% | {used} | {r.fallback} |"
        )
    total_base = round(sum(r.baseline_usd for r in rows), 6)
    total_voly = round(sum(r.voly_usd for r in rows), 6)
    total_saved = round(total_base - total_voly, 6)
    pct = round((total_saved / total_base) * 100.0, 2) if total_base else 0.0
    lines.extend(
        [
            "",
            f"**Totals:** baseline `${total_base:.4f}` · voly `${total_voly:.4f}` · "
            f"saved `${total_saved:.4f}` ({pct}%)",
            "",
            "Anti-claim: this is not a LiteLLM/OpenRouter provider-width benchmark.",
            "",
        ]
    )
    return "\n".join(lines)


def summarize(rows: list[Row]) -> dict[str, Any]:
    total_base = round(sum(r.baseline_usd for r in rows), 6)
    total_voly = round(sum(r.voly_usd for r in rows), 6)
    total_saved = round(total_base - total_voly, 6)
    fb_rows = [r for r in rows if "billing_fallback" in r.scenarios]
    return {
        "task_count": len(rows),
        "baseline_usd_total": total_base,
        "voly_usd_total": total_voly,
        "saved_usd_total": total_saved,
        "saved_pct_total": round((total_saved / total_base) * 100.0, 2) if total_base else 0.0,
        "billing_fallback_rows": len(fb_rows),
        "billing_fallback_saved_usd": round(sum(r.saved_usd for r in fb_rows), 6),
        "cross_vendor_rows": sum(1 for r in rows if len(set(r.executors_used)) >= 2),
    }

"""Retry-aware cost (этап 1): перезапуски не искажают FinOps-цифры.

Two folding levels, no double counting:
  1. Executor-level: zen/opencode model loops fold abandoned attempts' spend
     into the returned ExecutorResult (metadata.retry_cost_usd isolates it).
  2. Chain-level: AgentRunner folds abandoned chain attempts into the TaskEvent
     totals (retry_count / retry_cost_usd fields).
"""

from __future__ import annotations

from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult, _fold_retry_costs
from voly.executor.zen import ZenExecutor
import voly.executor.zen as zen_mod
import voly.runner.agent_runner as runner_mod


# ─── _fold_retry_costs unit ──────────────────────────────────────────────────
def test_fold_retry_costs_sums_and_isolates_retry_share():
    final = ExecutorResult(success=True, cost_usd=0.05, input_tokens=10, output_tokens=5)
    abandoned = [
        ExecutorResult(success=False, cost_usd=0.1, input_tokens=100, output_tokens=50),
        ExecutorResult(success=False, cost_usd=0.2, input_tokens=200, output_tokens=80),
    ]
    out = _fold_retry_costs(final, abandoned)
    assert out.cost_usd == 0.35
    assert out.input_tokens == 310
    assert out.output_tokens == 135
    assert out.metadata["retry_count"] == 2
    assert out.metadata["retry_cost_usd"] == 0.3


def test_fold_retry_costs_noop_without_retries():
    final = ExecutorResult(success=True, cost_usd=0.05)
    assert _fold_retry_costs(final, []).cost_usd == 0.05
    assert "retry_count" not in final.metadata


# ─── zen: model-loop retries folded into the returned result ─────────────────
def test_zen_folds_abandoned_attempt_spend(monkeypatch):
    ex = ZenExecutor()
    attempts = [
        ExecutorResult(success=False, error="insufficient credits", billing_error=True,
                       cost_usd=0.1, input_tokens=100, output_tokens=40),
        ExecutorResult(success=False, error="insufficient credits", billing_error=True,
                       cost_usd=0.2, input_tokens=150, output_tokens=60),
        ExecutorResult(success=True, output="done", cost_usd=0.05, input_tokens=10, output_tokens=5),
    ]
    it = iter(attempts)
    monkeypatch.setattr(ex, "_run_cli_one", lambda *a, **k: next(it))

    result = ex._run_cli("do it", timeout=600)
    assert result.success is True
    assert result.cost_usd == 0.35
    assert result.input_tokens == 260
    assert result.metadata["retry_count"] == 2
    assert result.metadata["retry_cost_usd"] == 0.3


def test_zen_all_models_exhausted_still_folds(monkeypatch):
    ex = ZenExecutor()
    monkeypatch.setattr(
        ex, "_run_cli_one",
        lambda *a, **k: ExecutorResult(
            success=False, error="insufficient credits", billing_error=True, cost_usd=0.01,
        ),
    )
    result = ex._run_cli("do it", timeout=600)
    n_models = len(ex._models_to_try())
    assert result.billing_error is True  # chain can continue past zen
    assert result.metadata["retry_count"] == n_models - 1
    assert round(result.cost_usd, 6) == round(0.01 * n_models, 6)


# ─── AgentRunner: chain retries land in TaskEvent totals ─────────────────────
class _FakeExec:
    def __init__(self, name: str, result: ExecutorResult, available: bool = True):
        self._name, self._result, self._available = name, result, available

    @property
    def name(self) -> str:
        return self._name

    def run(self, task, cwd=None, allowed_tools=None, max_turns=30, timeout=300, **kw):
        return self._result

    def is_available(self) -> bool:
        return self._available


def test_agent_runner_event_includes_retry_spend(monkeypatch, tmp_path):
    fakes = {
        "claude-code": _FakeExec("claude-code", ExecutorResult(
            success=False, error="credit balance is too low", billing_error=True,
            cost_usd=0.005, input_tokens=100, output_tokens=50, duration_ms=10,
        )),
        "wrangler": _FakeExec("wrangler", ExecutorResult(success=False, error="down"), available=False),
        "opencode": _FakeExec("opencode", ExecutorResult(
            success=True, output="done", cost_usd=0.002, input_tokens=10, output_tokens=5, duration_ms=10,
        )),
    }
    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: fakes[name])

    events: list = []
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda ev, cfg: events.append(ev))

    runner = runner_mod.AgentRunner(VOLYConfig())
    out = runner.run("fix the bug", "claude-code", cwd=str(tmp_path))

    assert out.success is True
    assert out.executor == "opencode"
    assert len(events) == 1
    ev = events[0]
    # Totals = final attempt + abandoned claude-code attempt (wrangler skipped, spent nothing).
    assert ev.cost_usd == 0.007
    assert ev.retry_count == 1
    assert ev.retry_cost_usd == 0.005
    assert ev.tokens.input == 110
    assert ev.tokens.output == 55
    # Per-attempt spend is visible in the chain timelog.
    log = out.result.metadata["chain_timelog"]
    assert log[0]["cost_usd"] == 0.005
    assert log[-1]["cost_usd"] == 0.002


def test_agent_runner_no_retry_keeps_plain_numbers(monkeypatch, tmp_path):
    fakes = {
        "claude-code": _FakeExec("claude-code", ExecutorResult(
            success=True, output="done", cost_usd=0.003, input_tokens=30, output_tokens=15, duration_ms=10,
        )),
    }
    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: fakes[name])
    events: list = []
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda ev, cfg: events.append(ev))

    runner = runner_mod.AgentRunner(VOLYConfig())
    out = runner.run("fix the bug", "claude-code", cwd=str(tmp_path))

    assert out.success is True
    ev = events[0]
    assert ev.cost_usd == 0.003
    assert ev.retry_count == 0
    assert ev.retry_cost_usd == 0.0

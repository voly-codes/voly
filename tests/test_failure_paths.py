"""Этап 6 — интеграционные тесты путей отказа (риск R2, assessment).

Три P0-пути, все mock-based (без реальных API):
  1. Billing fallback проходит всю цепочку claude-code → wrangler → opencode → zen;
     retry_count / retry_cost_usd корректны, стоимость не задваивается —
     ни на chain-уровне (AgentRunner), ни при наложении executor-уровня
     (внутренний model-loop zen).
  2. Spend limit AIGateway останавливает мульти-агентную цепочку посередине:
     агенты после лимита не вызывают провайдера и не тратят деньги.
  3. Recursion guard: nested A2A-запуск не входит в auto-dispatch повторно
     (оба сигнала — context и env), не-nested сложный запуск — входит.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from voly.a2a.multiagent import Assignment, run_local
from voly.ai_gateway import AIGateway
from voly.config import VOLYConfig
from voly.executor.base import ExecutorResult
from voly.executor.zen import ZenExecutor
from voly.pipeline import Pipeline
from voly.pipeline.types import PipelineResult, PipelineStage
from voly.router import RouteDecision
import voly.runner.agent_runner as runner_mod
from voly.runner.agent_runner import BILLING_FALLBACK_CHAIN


# ─── helpers ──────────────────────────────────────────────────────────────────

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


def _billing(cost: float, tin: int, tout: int) -> ExecutorResult:
    return ExecutorResult(
        success=False, error="credit balance is too low", billing_error=True,
        cost_usd=cost, input_tokens=tin, output_tokens=tout, duration_ms=5,
    )


def _run_chain(monkeypatch, tmp_path, fakes: dict):
    monkeypatch.setattr(runner_mod, "_build_executor", lambda name, model=None: fakes[name])
    events: list = []
    monkeypatch.setattr(runner_mod, "emit_event_from_config", lambda ev, cfg: events.append(ev))
    runner = runner_mod.AgentRunner(VOLYConfig())
    out = runner.run("fix the bug", "claude-code", cwd=str(tmp_path))
    return out, events


# ─── 1. Billing fallback: полный проход цепочки до zen ────────────────────────

def test_billing_chain_walks_all_four_to_zen(monkeypatch, tmp_path):
    """claude-code, wrangler, opencode отдают billing_error → задача доходит до zen."""
    fakes = {
        "claude-code": _FakeExec("claude-code", _billing(0.01, 100, 50)),
        "wrangler": _FakeExec("wrangler", _billing(0.02, 200, 80)),
        "opencode": _FakeExec("opencode", _billing(0.03, 300, 120)),
        "zen": _FakeExec("zen", ExecutorResult(
            success=True, output="done", cost_usd=0.04,
            input_tokens=10, output_tokens=5, duration_ms=5,
        )),
    }
    out, events = _run_chain(monkeypatch, tmp_path, fakes)

    assert out.success is True
    assert out.executor == "zen"

    # Chain timelog: все 4 executor-а в порядке цепочки, статусы честные.
    log = out.result.metadata["chain_timelog"]
    assert [e["executor"] for e in log] == BILLING_FALLBACK_CHAIN
    assert [e["status"] for e in log] == [
        "billing_error", "billing_error", "billing_error", "success",
    ]

    # Retry-аккаунтинг: 3 брошенные попытки, их спенд изолирован в retry_cost_usd.
    ev = events[0]
    assert ev.retry_count == 3
    assert ev.retry_cost_usd == 0.06
    # Тотал = финальная попытка + все брошенные, каждая учтена ровно один раз.
    assert ev.cost_usd == 0.1
    assert ev.tokens.input == 610
    assert ev.tokens.output == 255
    # Тотал события == сумме per-attempt стоимостей из timelog (нет задвоения).
    assert round(sum(e["cost_usd"] for e in log), 6) == ev.cost_usd


def test_billing_chain_zen_also_exhausted(monkeypatch, tmp_path):
    """Даже zen в billing_error → задача falls, но спенд всей цепочки учтён."""
    fakes = {
        "claude-code": _FakeExec("claude-code", _billing(0.01, 100, 50)),
        "wrangler": _FakeExec("wrangler", _billing(0.02, 200, 80)),
        "opencode": _FakeExec("opencode", _billing(0.03, 300, 120)),
        "zen": _FakeExec("zen", _billing(0.005, 10, 5)),
    }
    out, events = _run_chain(monkeypatch, tmp_path, fakes)

    assert out.success is False
    assert out.executor == "zen"
    log = out.result.metadata["chain_timelog"]
    assert [e["status"] for e in log] == ["billing_error"] * 4

    ev = events[0]
    assert ev.status == "failed"
    # zen — финальная (не брошенная) попытка: в retry_* только первые три.
    assert ev.retry_count == 3
    assert ev.retry_cost_usd == 0.06
    assert ev.cost_usd == 0.065
    assert round(sum(e["cost_usd"] for e in log), 6) == ev.cost_usd


def test_billing_chain_skips_unavailable_without_charging(monkeypatch, tmp_path):
    """Недоступный executor помечается skipped и не попадает в retry-спенд."""
    fakes = {
        "claude-code": _FakeExec("claude-code", _billing(0.01, 100, 50)),
        "wrangler": _FakeExec("wrangler", ExecutorResult(success=False, error="down"),
                              available=False),
        "opencode": _FakeExec("opencode", _billing(0.03, 300, 120)),
        "zen": _FakeExec("zen", ExecutorResult(
            success=True, output="done", cost_usd=0.002,
            input_tokens=10, output_tokens=5, duration_ms=5,
        )),
    }
    out, events = _run_chain(monkeypatch, tmp_path, fakes)

    assert out.success is True and out.executor == "zen"
    log = out.result.metadata["chain_timelog"]
    assert [(e["executor"], e["status"]) for e in log] == [
        ("claude-code", "billing_error"),
        ("wrangler", "skipped"),
        ("opencode", "billing_error"),
        ("zen", "success"),
    ]
    ev = events[0]
    # Skipped wrangler ничего не потратил и не считается retry-попыткой.
    assert ev.retry_count == 2
    assert ev.retry_cost_usd == 0.04
    assert ev.cost_usd == 0.042


def test_billing_chain_and_zen_internal_retries_no_double_count(monkeypatch, tmp_path):
    """Два уровня фолдинга вместе: chain-retries (AgentRunner) + model-loop zen.

    Реальный ZenExecutor с мокнутым _run_cli_one: первая модель billing,
    вторая успешна. Его внутренний retry уже сфолжен в cost_usd результата
    (metadata.retry_cost_usd), chain-уровень добавляет только брошенные
    попытки цепочки — каждая трата учтена ровно один раз.
    """
    zen = ZenExecutor()
    zen._use_cli = True
    zen_attempts = iter([
        ExecutorResult(success=False, error="insufficient credits", billing_error=True,
                       cost_usd=0.001, input_tokens=10, output_tokens=4),
        ExecutorResult(success=True, output="done", cost_usd=0.002,
                       input_tokens=20, output_tokens=8),
    ])
    monkeypatch.setattr(zen, "_run_cli_one", lambda *a, **k: next(zen_attempts))

    fakes = {
        "claude-code": _FakeExec("claude-code", _billing(0.05, 100, 40)),
        "wrangler": _FakeExec("wrangler", ExecutorResult(success=False, error="down"),
                              available=False),
        "opencode": _FakeExec("opencode", _billing(0.007, 30, 12)),
        "zen": zen,
    }
    out, events = _run_chain(monkeypatch, tmp_path, fakes)

    assert out.success is True and out.executor == "zen"

    # Executor-уровень: zen сфолдил свой внутренний retry в свой результат.
    assert out.result.cost_usd == 0.003
    assert out.result.metadata["retry_count"] == 1
    assert out.result.metadata["retry_cost_usd"] == 0.001

    # Chain-уровень: retry_* — только брошенные попытки цепочки (не внутренние zen).
    ev = events[0]
    assert ev.retry_count == 2
    assert ev.retry_cost_usd == 0.057
    # Тотал = 0.05 (claude-code) + 0.007 (opencode) + 0.003 (zen с внутренним retry).
    assert ev.cost_usd == 0.06
    assert ev.tokens.input == 100 + 30 + 30
    assert ev.tokens.output == 40 + 12 + 12
    # И тотал равен сумме per-attempt стоимостей timelog — нет задвоения
    # (у skipped-записи нет cost_usd: она ничего не потратила).
    log = out.result.metadata["chain_timelog"]
    assert round(sum(e.get("cost_usd", 0.0) for e in log), 6) == ev.cost_usd


# ─── 2. Spend limit останавливает мульти-агентную цепочку ─────────────────────

def _assignments() -> list[Assignment]:
    roles = ["architect", "developer", "tester", "reviewer", "devops"]
    return [
        Assignment(
            idx=i, role=role, description=f"{role} work",
            depends_on=[i - 1] if i else [], tier="standard",
            model="claude-sonnet-4-6", provider="anthropic",
        )
        for i, role in enumerate(roles)
    ]


def test_spend_limit_halts_multiagent_chain_midway(monkeypatch):
    """Бюджет на 2 вызова из 5: агенты 3-5 получают spend_limited без трат."""
    gw = AIGateway()
    gw.cache.enabled = False
    gw.spend_limit.daily_budget_usd = 2.5
    # Charge $1 per successful call (estimate pre-check + actual post-charge)
    monkeypatch.setattr(gw, "_estimate_cost", lambda *a, **k: 1.0)
    monkeypatch.setattr(gw, "_calculate_cost", lambda *a, **k: 1.0)

    provider_calls: list[str] = []

    def fake_direct(messages, model, provider_name, max_tokens, temperature, system, tools=None):
        provider_calls.append(provider_name)
        return {
            "content": "ok", "model": model,
            "usage": {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50},
        }

    monkeypatch.setattr(gw, "_direct_call", fake_direct)

    assignments = _assignments()
    run_local("build a service", assignments, gw, skill_matcher=None)

    # Первые два агента прошли, лимит сработал ровно посередине цепочки.
    assert [a.ok for a in assignments] == [True, True, False, False, False]
    for a in assignments[2:]:
        assert a.error == "Spend limit exceeded"
        assert a.cost_usd == 0.0
        assert a.input_tokens == 0 and a.output_tokens == 0

    # Провайдер реально вызывался только до лимита; спенд не растёт после него.
    assert len(provider_calls) == 2
    assert gw.spend_limit.spent_today == 2.0


def test_spend_limit_zero_budget_blocks_whole_chain(monkeypatch):
    """Исчерпанный дневной бюджет: ни один суб-агент не доходит до провайдера."""
    gw = AIGateway()
    gw.cache.enabled = False
    gw.spend_limit.daily_budget_usd = 0.5
    gw.spend_limit.spent_today = 0.5
    gw.spend_limit.reset_at = __import__("time").time()
    monkeypatch.setattr(gw, "_estimate_cost", lambda *a, **k: 1.0)
    monkeypatch.setattr(
        gw, "_direct_call",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )

    assignments = _assignments()
    run_local("build a service", assignments, gw, skill_matcher=None)

    assert all(a.ok is False for a in assignments)
    assert all(a.error == "Spend limit exceeded" for a in assignments)
    assert gw.spend_limit.spent_today == 0.5


# ─── 3. Recursion guard в Pipeline.run ─────────────────────────────────────────

_HIGH_ANALYSIS = MagicMock(
    requires_code_gen=True,
    requires_review=True,
    requires_testing=True,
    requires_deployment=False,
    complexity="high",
)


def _guarded_pipeline(monkeypatch):
    """Pipeline с включённым auto-dispatch и стабами вокруг guard-а.

    _stage_a2a_auto — рекордер (вернёт a2a_result), _stage_spend_check —
    барьер сразу после guard-а, чтобы остальной pipeline не выполнялся.
    """
    pipeline = Pipeline()
    pipeline.config.a2a.enabled = True
    pipeline.config.a2a.auto_dispatch = True

    route = RouteDecision(agent="developer", model="claude-sonnet-4-6", provider="anthropic")
    monkeypatch.setattr(pipeline, "_stage_route", lambda *a, **k: (route, _HIGH_ANALYSIS, "code"))

    dispatched: list[bool] = []
    a2a_result = PipelineResult(success=True, stage=PipelineStage.DONE)

    def record_dispatch(*a, **k):
        dispatched.append(True)
        return a2a_result

    monkeypatch.setattr(pipeline, "_stage_a2a_auto", record_dispatch)

    barrier = PipelineResult(success=False, stage=PipelineStage.ERROR, error="stop-at-barrier")
    monkeypatch.setattr(pipeline, "_stage_spend_check", lambda *a, **k: barrier)
    return pipeline, dispatched, a2a_result, barrier


def test_run_complex_task_enters_auto_dispatch(monkeypatch):
    monkeypatch.delenv("VOLY_A2A_NESTED", raising=False)
    pipeline, dispatched, a2a_result, _ = _guarded_pipeline(monkeypatch)
    result = pipeline.run("build a service")
    assert result is a2a_result
    assert dispatched == [True]


def test_run_nested_by_context_skips_auto_dispatch(monkeypatch):
    monkeypatch.delenv("VOLY_A2A_NESTED", raising=False)
    pipeline, dispatched, _, barrier = _guarded_pipeline(monkeypatch)
    result = pipeline.run("build a service", context={"a2a_parent_task_id": "parent-1"})
    assert result is barrier
    assert dispatched == []


def test_run_nested_by_env_skips_auto_dispatch(monkeypatch):
    monkeypatch.setenv("VOLY_A2A_NESTED", "1")
    pipeline, dispatched, _, barrier = _guarded_pipeline(monkeypatch)
    result = pipeline.run("build a service")
    assert result is barrier
    assert dispatched == []

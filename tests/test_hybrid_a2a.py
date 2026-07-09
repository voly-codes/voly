"""PR1 hybrid multi-agent: role→mode map + run_local executor branch (mocked)."""

from __future__ import annotations

from voly.a2a.decomposer import TaskDecomposer
from voly.a2a.hybrid import (
    DEFAULT_EXECUTOR_ROLES,
    hybrid_active,
    resolve_role_mode,
)
from voly.a2a.multiagent import Assignment, LeadOrchestrator, run_local
from voly.config import A2AConfig, VOLYConfig, load_config


class _FakeAnalysis:
    complexity = "high"
    requires_code_gen = True
    requires_review = True
    requires_testing = True
    requires_deployment = True


class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat(self, messages, model, provider_name="anthropic", system=None, agent=None, **kw):
        self.calls.append(agent or "")
        if agent == "lead":
            return {
                "content": "[]",
                "model": model,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return {
            "content": f"chat:{agent}",
            "model": model,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }


def test_resolve_role_mode_map() -> None:
    assert resolve_role_mode("architect", hybrid_enabled=True)[0] == "chat"
    assert resolve_role_mode("developer", hybrid_enabled=True)[0] == "executor"
    assert resolve_role_mode("bugfixer", hybrid_enabled=True)[0] == "executor"
    assert resolve_role_mode("tester", hybrid_enabled=True, requires_code_gen=True)[0] == "executor"
    assert resolve_role_mode("tester", hybrid_enabled=True, requires_code_gen=False)[0] == "chat"
    assert resolve_role_mode("reviewer", hybrid_enabled=True)[0] == "chat"
    assert resolve_role_mode("developer", hybrid_enabled=False)[0] == "chat"


def test_resolve_role_mode_lead_override() -> None:
    mode, reason = resolve_role_mode(
        "architect", hybrid_enabled=True, lead_execution="executor",
    )
    assert mode == "executor"
    assert reason == "lead_override"
    mode2, _ = resolve_role_mode(
        "developer", hybrid_enabled=True, lead_execution="chat",
    )
    assert mode2 == "chat"


def test_hybrid_active_requires_cwd() -> None:
    assert hybrid_active(hybrid_code_gen=True, has_cwd=True) is True
    assert hybrid_active(hybrid_code_gen=True, has_cwd=False) is False
    assert hybrid_active(hybrid_code_gen=True, has_cwd=False, hybrid_require_cwd=False) is True
    assert hybrid_active(hybrid_code_gen=False, has_cwd=True) is False


def test_a2a_config_hybrid_defaults() -> None:
    cfg = A2AConfig()
    assert cfg.hybrid_code_gen is True
    assert cfg.hybrid_require_cwd is True
    assert cfg.executor_default == "claude-code"
    assert cfg.executor_roles == []


def test_a2a_config_from_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("VOLY_A2A_HYBRID", raising=False)
    p = tmp_path / "voly.yaml"
    p.write_text(
        """
a2a:
  hybrid_code_gen: false
  hybrid_require_cwd: false
  executor_default: zen
  executor_roles:
    - developer
  execution_mode: local
  lead_model: claude-sonnet-4-6
""",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.a2a.hybrid_code_gen is False
    assert cfg.a2a.hybrid_require_cwd is False
    assert cfg.a2a.executor_default == "zen"
    assert cfg.a2a.executor_roles == ["developer"]
    assert cfg.a2a.execution_mode == "local"
    assert cfg.a2a.lead_model == "claude-sonnet-4-6"


def test_a2a_hybrid_env_override(tmp_path, monkeypatch) -> None:
    p = tmp_path / "voly.yaml"
    p.write_text("a2a:\n  hybrid_code_gen: false\n", encoding="utf-8")
    monkeypatch.setenv("VOLY_A2A_HYBRID", "true")
    cfg = load_config(p)
    assert cfg.a2a.hybrid_code_gen is True


def test_run_local_no_cwd_all_chat() -> None:
    """Without cwd, hybrid does not activate — same chat path as before."""
    subs = TaskDecomposer().decompose("build a service", _FakeAnalysis())
    gw = _FakeGateway()
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)
    run_local("build", assignments, gw, cwd="", hybrid_code_gen=True, hybrid_require_cwd=True)
    for a in assignments:
        assert a.mode == "chat"
        assert a.ok is True
        assert a.content == f"chat:{a.role}"
    # All five roles hit gateway (plus lead during assign)
    assert set(a.role for a in assignments) <= set(gw.calls)


def test_run_local_executor_runner_mock() -> None:
    """With cwd + mock runner, implement roles use executor branch."""
    subs = TaskDecomposer().decompose("build a service", _FakeAnalysis())
    gw = _FakeGateway()
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)

    executed: list[str] = []

    def runner(*, role, task, cwd, executor, system, assignment):
        executed.append(role)
        return {
            "ok": True,
            "content": f"wrote via {executor} for {role}",
            "cost_usd": 0.01,
            "files_touched": [f"src/{role}.py"],
            "executor": executor,
        }

    chat_before = len([c for c in gw.calls if c and c != "lead"])
    run_local(
        "build",
        assignments,
        gw,
        cwd="/tmp/proj",
        hybrid_code_gen=True,
        requires_code_gen=True,
        executor_default="claude-code",
        executor_runner=runner,
    )

    by_role = {a.role: a for a in assignments}
    assert by_role["architect"].mode == "chat"
    assert by_role["developer"].mode == "executor"
    assert by_role["tester"].mode == "executor"
    assert by_role["reviewer"].mode == "chat"
    assert by_role["developer"].ok
    assert by_role["developer"].files_touched == ["src/developer.py"]
    assert by_role["developer"].executor == "claude-code"
    assert "developer" in executed and "tester" in executed
    assert "architect" not in executed
    # Chat roles still call gateway; implement roles do not
    chat_roles = [c for c in gw.calls if c in ("architect", "reviewer", "devops")]
    assert "architect" in chat_roles
    assert "developer" not in gw.calls or gw.calls.count("developer") == 0
    _ = chat_before  # lead assign may have called already


def test_run_local_skip_dependents_on_failure() -> None:
    subs = TaskDecomposer().decompose("build a service", _FakeAnalysis())
    gw = _FakeGateway()
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)

    def runner(*, role, task, cwd, executor, system, assignment):
        if role == "developer":
            return {"ok": False, "error": "boom", "content": ""}
        return {"ok": True, "content": f"ok {role}", "files_touched": []}

    run_local(
        "build",
        assignments,
        gw,
        cwd="/tmp/proj",
        hybrid_code_gen=True,
        executor_runner=runner,
        skip_dependents_on_failure=True,
    )
    by_role = {a.role: a for a in assignments}
    assert by_role["developer"].ok is False
    # tester depends on developer → skipped
    assert by_role["tester"].ok is False
    assert "prior role" in by_role["tester"].error


def test_run_local_executor_without_runner_falls_back_to_chat() -> None:
    subs = TaskDecomposer().decompose("build a service", _FakeAnalysis())
    gw = _FakeGateway()
    assignments = LeadOrchestrator(gateway=gw, skill_matcher=None).assign("build", subs)
    run_local(
        "build",
        assignments,
        gw,
        cwd="/tmp/proj",
        hybrid_code_gen=True,
        executor_runner=None,
    )
    dev = next(a for a in assignments if a.role == "developer")
    assert dev.mode == "executor"
    assert "chat_fallback" in dev.mode_reason
    assert dev.ok is True
    assert dev.content == "chat:developer"


def test_default_executor_roles_constant() -> None:
    assert "developer" in DEFAULT_EXECUTOR_ROLES
    assert "architect" not in DEFAULT_EXECUTOR_ROLES


def test_voly_config_has_hybrid() -> None:
    cfg = VOLYConfig()
    assert cfg.a2a.hybrid_code_gen is True

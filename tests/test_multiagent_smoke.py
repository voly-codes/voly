"""Smoke tests for local multi-agent execution (a2a/multiagent.py).

Uses a fake gateway so no real provider calls are made.
"""
from __future__ import annotations

from codeops.a2a.decomposer import TaskDecomposer
from codeops.a2a.multiagent import (
    Assignment,
    LeadOrchestrator,
    merge_report,
    resolve_tier_model,
    run_local,
)


class _FakeAnalysis:
    complexity = "high"
    requires_code_gen = True
    requires_review = True
    requires_testing = True
    requires_deployment = True


class _FakeGateway:
    """Records calls and returns canned content; lead call returns a JSON plan."""

    def __init__(self):
        self.calls = []

    def chat(self, messages, model, provider_name="anthropic", system=None, agent=None, **kw):
        self.calls.append({"agent": agent, "model": model, "provider": provider_name})
        if agent == "lead":
            return {"content": '[{"idx":0,"tier":"premium","skills":[]}]', "model": model,
                    "usage": {"input_tokens": 10, "output_tokens": 5}}
        return {"content": f"output from {agent}", "model": model,
                "usage": {"input_tokens": 20, "output_tokens": 30}}


def _subtasks():
    return TaskDecomposer().decompose("build a service", _FakeAnalysis())


def test_decompose_full_five_roles():
    subs = _subtasks()
    assert [s.agent for s in subs] == ["architect", "developer", "tester", "reviewer", "devops"]


def test_resolve_tier_model_returns_pair():
    model, provider = resolve_tier_model("cheap")
    assert isinstance(model, str) and isinstance(provider, str) and model and provider


def test_lead_assign_and_run_local():
    subs = _subtasks()
    gw = _FakeGateway()
    lead = LeadOrchestrator(gateway=gw, skill_matcher=None)
    assignments = lead.assign("build a service", subs)

    assert len(assignments) == 5
    assert [a.role for a in assignments] == ["architect", "developer", "tester", "reviewer", "devops"]
    for a in assignments:
        assert a.model and a.provider
        assert a.tier in ("premium", "standard", "cheap")

    run_local("build a service", assignments, gw, skill_matcher=None)
    for a in assignments:
        assert a.ok is True
        assert a.content == f"output from {a.role}"
        assert a.output_tokens == 30

    ran = [c["agent"] for c in gw.calls if c["agent"] != "lead"]
    assert ran.index("developer") < ran.index("tester")
    assert ran.index("tester") < ran.index("reviewer")


def test_lead_fallback_on_non_json():
    """Non-JSON lead reply → deterministic tier fallback, still 5 assignments."""
    subs = _subtasks()

    class _BadLeadGateway(_FakeGateway):
        def chat(self, messages, model, provider_name="anthropic", system=None, agent=None, **kw):
            if agent == "lead":
                return {"content": "sorry, no json here", "model": model, "usage": {}}
            return super().chat(messages, model, provider_name, system, agent, **kw)

    assignments = LeadOrchestrator(gateway=_BadLeadGateway(), skill_matcher=None).assign("x", subs)
    assert len(assignments) == 5
    tiers = {a.role: a.tier for a in assignments}
    assert tiers["architect"] == "premium"
    assert tiers["tester"] == "cheap"


def test_run_local_cache_and_memory():
    """Cache-hit → 0 cost; memory search injected as mem_hits."""
    subs = _subtasks()

    class _CachedGateway(_FakeGateway):
        def chat(self, messages, model, provider_name="anthropic", system=None, agent=None, **kw):
            r = super().chat(messages, model, provider_name, system, agent, **kw)
            if agent != "lead":
                r["cache_hit"] = True
            return r

    class _Mem:
        def __init__(self):
            self.added = 0
        def search(self, q, limit=3):
            class E:
                category, title, content = "history", "prior", "prior result"
            return [E()]
        def add(self, **kw):
            self.added += 1

    assignments = LeadOrchestrator(gateway=_CachedGateway(), skill_matcher=None).assign("x", subs)
    mem = _Mem()
    run_local("x", assignments, _CachedGateway(), skill_matcher=None, memory=mem)
    for a in assignments:
        assert a.cache_hit is True
        assert a.cost_usd == 0.0
        assert a.mem_hits == 1


def test_merge_report_contains_roles_and_models():
    a = Assignment(idx=0, role="architect", description="d", depends_on=[], tier="premium",
                   model="claude-sonnet-4-6", provider="anthropic", content="design", ok=True)
    report = merge_report("task", [a])
    assert "architect" in report and "claude-sonnet-4-6" in report and "design" in report
